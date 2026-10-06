# Fields API

REST API для керування сільськогосподарськими полями зі швидким пошуком полів, що містять задану точку.
Уся геометрія рахується й перевіряється в PostGIS, а пошук за точкою спирається на GIST-індекс:
на 100 000 полів запит займає ~1 мс (без індексу — ~120 мс).

**Стек:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), GeoAlchemy2, Alembic,
PostgreSQL 16 + PostGIS 3.4, Docker Compose, uv, pytest + testcontainers.

## Зміст

- [Швидкий старт](#швидкий-старт)
- [API](#api)
- [Архітектура](#архітектура)
- [Схема БД і SQL-запити](#схема-бд-і-sql-запити)
- [Геопросторові рішення](#геопросторові-рішення)
- [Продуктивність](#продуктивність)
- [Масштабування](#масштабування)
- [Trade-offs](#trade-offs)
- [Припущення](#припущення)
- [Сиди](#сиди)
- [Що б я покращив](#що-б-я-покращив)
- [Розробка](#розробка)

## Швидкий старт

Потрібен Docker з **Docker Compose v2** (команда `docker compose`; зі старим `docker-compose` v1, який
знято з підтримки, проєкт не перевірявся). `.env` і ручні кроки не потрібні.

```bash
git clone <repo> && cd test_fields_app
docker compose up -d --build    # db, міграції, сиди (2000 полів), api, pgAdmin

# дочекатися, поки api стане healthy (перший запуск довший — збирається образ)
docker compose ps
```

Що відбувається під час старту: `db` (PostGIS) → `migrate` (чекає базу, `alembic upgrade head`) →
`seed` (заповнює порожню таблицю) і `api` (стартує лише після успішної міграції).

```bash
# пошук за точкою — запит з ТЗ (поверне 3 демо-поля)
curl -s "localhost:8000/api/fields/find-by-point?lon=30.5250&lat=50.4550"

# створення поля — тіло з ТЗ (після цього пошук вище поверне 4 поля)
curl -s -X POST localhost:8000/api/fields \
  -H 'Content-Type: application/json' \
  -d '{"name":"Поле №1 - Пшениця","geometry":{"type":"Polygon","coordinates":[[[30.5234,50.4501],[30.5334,50.4501],[30.5334,50.4601],[30.5234,50.4601],[30.5234,50.4501]]]},"crop":"Пшениця","owner":"Іванов І.І."}'

# список з фільтрами (кирилицю в query передаємо через --data-urlencode)
curl -sG localhost:8000/api/fields --data-urlencode "crop=Пшениця" -d min_area=50 -d limit=5

# деталі поля з геометрією
curl -s localhost:8000/api/fields/<id>
```

| Що | Де |
| --- | --- |
| Swagger UI (усі сценарії демо — кнопкою *Try it out*) | http://localhost:8000/docs |
| Postman | *Import* → `http://localhost:8000/openapi.json` (колекція імпортується цілком) |
| pgAdmin (Geometry Viewer малює полігони на карті) | http://localhost:5050 — підключення вже налаштоване, пароль бази `fields` |
| PostgreSQL з хоста | `localhost:5433`, база/користувач/пароль `fields` |

Порт бази на хості — **5433**, щоб не конфліктувати з локальним Postgres.

> На Mac з Apple Silicon образ `postgis/postgis` (лише amd64) працює через емуляцію Rosetta:
> усе запускається, але Postgres повільніший.

### Команди

`Makefile` — лише зручність; кожна команда має еквівалент без `make` (наприклад, на Windows).

| make | Без make | Що робить |
| --- | --- | --- |
| `make up` | `docker compose up -d --build` | підняти все |
| `make down` | `docker compose down` | зупинити |
| `make reset` | `docker compose down -v` | зупинити й видалити дані БД |
| `make logs` | `docker compose logs -f api` | логи API |
| `make reseed` | `docker compose run --rm seed python -m scripts.seed --truncate` | перестворити 2000 полів |
| `make seed-large` | `docker compose run --rm seed python -m scripts.seed --truncate --count 100000` | 100 000 полів для демо продуктивності |
| `make test` | `uv run pytest` | тести (потрібен запущений Docker) |
| `make bench` | `uv run python -m scripts.benchmark` | бенчмарк пошуку (p50/p95) |
| `make lint` | `uv run ruff check . && uv run ruff format --check .` | лінтер |

## API

Шляхи, параметри й тіла відповідей — рівно як у ТЗ. Плюс службовий `/health`.

| Метод | Шлях | Успіх | Помилки |
| --- | --- | --- | --- |
| POST | `/api/fields` | 201 | 400, 422 |
| GET | `/api/fields` | 200 | 422 |
| GET | `/api/fields/find-by-point?lon=…&lat=…` | 200 | 422 |
| GET | `/api/fields/{id}` | 200 | 404, 422 |
| GET | `/health` | 200 | 503 |

**POST /api/fields** — створення поля. Перевірки:

| Випадок | Хто ловить | Відповідь |
| --- | --- | --- |
| кільце не замкнене, < 4 точок, тип не `Polygon`, координата поза діапазоном, 3D, > 10 000 вершин, ребро ≥ 180° довготи | Pydantic | 422 |
| самоперетин («метелик»), петля біля кута, дірка поза полем тощо | `ST_IsValid` (PostGIS) | 400 `INVALID_GEOMETRY` + причина з координатою: `Self-intersection[30.01 50.01]` |
| площа ≤ 0.1 га | `ST_Area(geography)` | 400 `FIELD_AREA_TOO_SMALL` |

Невалідний полігон **відхиляємо, а не виправляємо**: ТЗ вимагає валідації, а автоматичне виправлення
(`ST_MakeValid`) мовчки змінює форму поля і з «метелика» робить MultiPolygon.

**GET /api/fields** — `crop`, `owner` (точний збіг), `min_area`, `max_area` (га, включно),
`limit` (типово 20, максимум 100), `offset`. Відповідь `{total, fields}`, без геометрії, нові поля зверху.

**GET /api/fields/find-by-point** — поля, що містять точку; кілька, якщо поля перекриваються.
Сортування — за відстанню до центроїда поля. Без збігів — 200 з порожнім `fields`.
`query_time_ms` — час лише SQL-запиту пошуку.

**Єдиний формат помилок** (усі 4xx/5xx):

```json
{
  "error": {
    "code": "INVALID_GEOMETRY",
    "message": "Polygon is not valid",
    "details": {"reason": "Self-intersection[30.51 50.41]"},
    "request_id": "3f2a9c1e-7d4b-4c1a-9a0e-2b5f6c7d8e9f"
  }
}
```

Коди: `VALIDATION_ERROR` (422), `INVALID_GEOMETRY` / `FIELD_AREA_TOO_SMALL` (400), `FIELD_NOT_FOUND` /
`NOT_FOUND` (404), `METHOD_NOT_ALLOWED` (405), `DATABASE_UNAVAILABLE` (503), `INTERNAL_ERROR` (500).

**Трасування:** кожен запит отримує `X-Request-ID` (з заголовка клієнта або новий UUID). Він є
у відповіді, у тілі помилки і в кожному рядку логу:

```text
2026-10-06 10:04:06 INFO    [req=0e783716-…] app.middleware: POST /api/fields 201 9.3ms
2026-10-06 10:04:06 INFO    [req=0e783716-…] app.services.field: field created id=… area_ha=79.00
```

## Архітектура

```text
router (HTTP) → service (бізнес-правила, транзакція) → repository (SQL/PostGIS) → AsyncSession
```

| Шар | Що робить | Чого не робить |
| --- | --- | --- |
| `app/api` | параметри, `Depends`, `response_model`, статус-код | SQL, бізнес-логіка |
| `app/services` | валідація геометрії й площі, `query_time_ms`, межа транзакції (`session.begin()`) | HTTP, `HTTPException` |
| `app/repositories` | лише SQL і PostGIS-запити | commit, HTTP-помилки |
| `app/dependencies` | одна `AsyncSession` на запит; ланцюжок сесія → репозиторій → сервіс | — |

- Сервіс кидає доменні винятки (`FieldNotFoundError`, `InvalidGeometryError`, …); у HTTP-відповідь їх
  перетворює одне місце — `app/core/error_handlers.py`.
- Pydantic перевіряє **форму** даних (422), PostGIS — **зміст** геометрії (400).
- Middleware `request_id` ставить id у contextvar, пише access-лог і ловить необроблені винятки (500 у
  єдиному форматі з request_id).
- Схему БД створюють тільки міграції Alembic; тести теж проганяють міграції.

```text
app/
├── main.py              # create_app(): роутери, middleware, обробники помилок, lifespan
├── core/                # settings, logger, доменні винятки, обробники помилок
├── middleware/          # request_id
├── db/                  # Base (naming convention), engine/сесії, модель Field
├── dependencies/        # get_session, get_field_service
├── repositories/        # FieldRepository — SQL
├── services/            # FieldService — бізнес-логіка
├── schemas/             # Pydantic: GeoJSON Polygon, поля, помилки
├── api/                 # /api/fields, /health
└── openapi/             # приклади й відповіді для Swagger
migrations/              # Alembic
scripts/                 # seed.py, benchmark.py, wait_for_db.py
tests/                   # інтеграційні тести на справжньому PostGIS
```

## Схема БД і SQL-запити

Одна таблиця `fields`:

```sql
CREATE TABLE fields (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        varchar(255) NOT NULL,
    crop        varchar(100) NOT NULL,
    owner       varchar(255) NOT NULL,
    geom        geometry(Polygon, 4326) NOT NULL,
    area_ha     double precision NOT NULL
                GENERATED ALWAYS AS (ST_Area(geom::geography) / 10000) STORED,
    created_at  timestamptz(0) NOT NULL DEFAULT now(),
    CONSTRAINT ck_fields_geom_valid CHECK (ST_IsValid(geom)),
    CONSTRAINT ck_fields_area_min   CHECK (area_ha > 0.1)
);

CREATE INDEX ix_fields_geom          ON fields USING gist (geom);
CREATE INDEX ix_fields_owner         ON fields (owner);
CREATE INDEX ix_fields_area_ha       ON fields (area_ha);
CREATE INDEX ix_fields_created_at_id ON fields (created_at DESC, id DESC);
```

| Рішення | Чому |
| --- | --- |
| `geometry(Polygon, 4326)` + каст у `::geography` для метрів | для «точка всередині поля?» градуси підходять і з ними працює швидкий індекс; площу й відстань рахуємо на еліпсоїді через geography |
| `area_ha` — generated column | рахується один раз під час запису; фільтр за площею — звичайний btree без обчислень у запиті |
| GIST по `geom` | ключовий індекс пошуку за точкою |
| btree по `owner`, `area_ha`; по `crop` — ні | індекс корисний, коли відбирає малу частку рядків: один власник із ~100 — це близько 1%, а основні культури (пшениця, соняшник, кукурудза), за якими фільтрують найчастіше, — 20–24% рядків кожна, тож для них Postgres однаково прочитає всю таблицю |
| `(created_at DESC, id DESC)` | стабільне сортування списку; `id` — tie-breaker для однакових секунд |
| `timestamptz(0)` | час до секунди — відповідь рівно як у ТЗ: `"2024-01-15T10:30:00Z"` |
| `double precision`, не `numeric` | Pydantic серіалізує `Decimal` у JSON рядком |
| CHECK-констрейнти | ешелонований захист: страхують запис в обхід API (сиди) |
| центр поля не зберігаємо | `ST_Centroid` рахується лише для 1–3 знайдених полів — це мікросекунди |

### Ключовий запит: пошук за точкою

```sql
SELECT id, name, area_ha, crop, owner,
       ST_Distance(ST_Centroid(geom)::geography, :point::geography) AS distance_to_center_m
FROM fields
WHERE ST_Intersects(geom, :point)          -- :point = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
ORDER BY distance_to_center_m;
```

`ST_Intersects` неявно додає індексну умову `geom && point`: GIST швидко відбирає поля, чий
обмежувальний прямокутник містить точку, і точна перевірка йде лише для цих кандидатів. Центроїд і
відстань рахуються лише для знайдених рядків. Колонка `geom` у `WHERE` «гола» — усі перетворення лише
над точкою, інакше індекс не спрацює.

### Інші запити

```sql
-- перевірка полігона перед вставкою (площа — лише для валідного: на невалідному ST_Area може впасти)
SELECT ST_IsValid(geom), ST_IsValidReason(geom),
       CASE WHEN ST_IsValid(geom) THEN ST_Area(geom::geography) / 10000 END
FROM (SELECT ST_GeomFromGeoJSON(:geojson) AS geom) AS input;

-- вставка: id, area_ha і created_at заповнює база
INSERT INTO fields (name, crop, owner, geom)
VALUES (:name, :crop, :owner, ST_GeomFromGeoJSON(:geojson))
RETURNING id, name, area_ha, crop, owner, created_at, ST_AsGeoJSON(geom)::json AS geometry;

-- поле за id
SELECT id, name, area_ha, crop, owner, created_at, ST_AsGeoJSON(geom)::json AS geometry
FROM fields WHERE id = :id;

-- список: два запити з однаковим WHERE (умова додається, лише якщо фільтр переданий)
SELECT count(*) FROM fields
WHERE crop = :crop AND owner = :owner AND area_ha >= :min_area AND area_ha <= :max_area;

SELECT id, name, area_ha, crop, owner FROM fields
WHERE crop = :crop AND owner = :owner AND area_ha >= :min_area AND area_ha <= :max_area
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

`total` — окремим `count(*)`, а не `count(*) OVER()`: якщо `offset` більший за кількість рядків,
сторінка порожня і `total` узяти нізвідки.

## Геопросторові рішення

1. **SRID 4326** — звичайні GPS-координати (WGS 84): довгота й широта в градусах. Порядок — як у GeoJSON: `[lon, lat]`.
2. **`geometry` vs `geography`.** `geometry` рахує на площині в градусах — для «точка всередині поля?»
   цього достатньо, і з нею працює швидкий індекс. `geography` рахує на еліпсоїді Землі в метрах — нею
   рахуємо площу й відстань.
3. **GIST-індекс** — дерево обмежувальних прямокутників (R-tree): кожне поле в прямокутнику, прямокутники —
   у більших прямокутниках. Пошук спускається деревом і за кілька кроків відсікає тисячі полів.
4. **Пошук у два кроки:** індекс (`&&`, `Index Cond`) → точна перевірка `ST_Intersects` (`Filter`) лише для
   кандидатів: точка може потрапити в кут прямокутника, але не в саме поле.
5. **`ST_Intersects`, а не `ST_Contains`** — різниця лише для точки рівно на межі: ми вважаємо, що вона
   лежить усередині поля, тож для точки на спільній межі двох полів пошук знаходить обидва.
6. **`ST_IsValid`** ловить самоперетини; `ST_IsValidReason` дає причину й координату. Порядок перевірок
   важливий: спершу валідність, потім площа. У «метелика» частини з протилежним обходом віднімаються
   (у симетричного площа на еліпсоїді дорівнює 0), тож без цього порядку він міг би отримати «замала
   площа» замість «невалідний полігон», а несиметричний — і зовсім пройти перевірку площі.
7. **Центроїд** — «центр мас» фігури. У поля у формі літери «С» він може лежати поза полем.

## Продуктивність

### EXPLAIN ANALYZE (100 000 полів)

```text
Sort (actual rows=3 loops=1)
  ->  Index Scan using ix_fields_geom on fields (actual rows=3 loops=1)
        Index Cond: (geom && '0101…'::geometry)
        Filter: st_intersects(geom, '0101…'::geometry)
Execution Time: 0.276 ms
```

Без індексу (індекс не видаляємо, а вимикаємо в сесії: `SET enable_indexscan = off; SET enable_bitmapscan = off;`):

```text
Sort (actual rows=3 loops=1)
  ->  Gather
        ->  Parallel Seq Scan on fields (actual rows=2 loops=2)
              Filter: st_intersects(geom, '0101…'::geometry)
              Rows Removed by Filter: 50001
Execution Time: 126.153 ms
```

### Бенчмарк

`make bench` (`scripts/benchmark.py`): 1000 точок — половина гарантовано всередині полів, половина
випадково по сільгоспкластерах; міряється лише SQL-запит пошуку (те саме, що `query_time_ms`),
з клієнта через asyncpg, тобто разом із мережевим round-trip до локального Docker.

| Полів | Індекс | p50, мс | p95, мс |
| --- | --- | --- | --- |
| 2 000 | GIST | 0.80 | 1.57 |
| 2 000 | немає | 1.70 | 2.53 |
| 100 000 | GIST | 1.00 | 1.64 |
| 100 000 | немає | 118.34 | 141.26 |

З GIST час майже не росте з обсягом (пошук у дереві має логарифмічну складність), без індексу росте лінійно.
На 2 000 полів різниця непомітна: маленьку таблицю дешево прочитати цілком.

Нюанс, знайдений під час замірів: asyncpg використовує prepared statements, і PostgreSQL кешує для
них generic-план. `SET enable_indexscan = off` цей кеш не скидає, тож режим «без індексу» треба міряти
на новому з'єднанні — інакше виконується старий план з індексом.

### Що вже оптимізовано

| Рішення | Ефект |
| --- | --- |
| GIST по `geom` | пошук відсікає майже всі поля за кілька кроків замість повного проходу |
| `geometry` для зберігання, `geography` для метрик | швидка перевірка входження + точні метри |
| `area_ha` — generated column | фільтр за площею без обчислень у запиті |
| центроїд і відстань лише для знайдених полів | немає обчислень по всій таблиці |
| список без геометрії | менше даних з БД і через мережу |
| `ANALYZE` після сидів | планувальник одразу бачить свіжу статистику |
| async + пул з'єднань | з'єднання не відкривається на кожен запит |

## Масштабування

1. **Один Postgres — до мільйонів полів.** Час пошуку в дереві зростає логарифмічно; головне, щоб індекс
   вміщався в пам'ять.
2. **API масштабується горизонтально.** Застосунок не зберігає стану — усе в Postgres; N копій API за
   балансувальником працюють коректно.
3. **Багато читання — репліки Postgres.** Пошук і списки читають з реплік, запис — в основну базу.
   Підводний камінь: репліка відстає на частки секунди, тож GET одразу після POST може не знайти поле.

Далі, якщо знадобиться: партиціювання за регіонами або шардування (Citus) для десятків мільйонів полів;
`ST_Subdivide` для полігонів з тисячами вершин; keyset-пагінація замість offset; `COPY` для масового
завантаження.

## Trade-offs

| Рішення | Чому | Ціна |
| --- | --- | --- |
| без авторизації | у ТЗ її немає; запити з ТЗ працюють як є | створювати поля може будь-хто |
| шляхи без версії | рівно як у ТЗ | у разі несумісної зміни знадобиться `/api/v2` |
| без захисту від дублів | у ТЗ його немає | повторний POST створить друге поле |
| `geometry(4326)` + каст у `geography` | швидкий індекс, точні метри | пласка перевірка в градусах (для розмірів полів похибкою можна знехтувати) |
| `ST_Intersects` | межа належить полю | точка на спільній межі потрапляє в обидва поля |
| `ST_Centroid` | простий, стандартний | у ввігнутого поля центр може лежати поза ним |
| валідація в PostGIS | одне джерело істини | зайвий запит до БД під час POST |
| UUIDv4 | просто, вбудовано в Postgres | випадкові вставки в індекс PK |
| offset-пагінація, `total` окремим запитом | так у ТЗ; коректно на порожній сторінці | два запити; деградує на великих offset |
| `BaseHTTPMiddleware`, текстові логи | короткий зрозумілий код | трохи повільніше за чистий ASGI |
| сиди в обхід API | швидкість (100 000 полів за ~10 с) | перевірку роблять CHECK-констрейнти |

## Припущення

- Шляхи, параметри й тіла відповідей — рівно як у ТЗ; авторизації немає.
- Координати в порядку GeoJSON: `[lon, lat]`, SRID 4326.
- Невалідний полігон відхиляємо з 400 і координатою проблеми, а не виправляємо автоматично.
- Точка на межі поля вважається всередині поля (`ST_Intersects`).
- «Центр» поля — центроїд (`ST_Centroid`); у ввігнутого поля він може лежати зовні.
- Результати `find-by-point` відсортовані за відстанню до центру; без збігів → 200 з порожнім `fields`.
- Фільтри `crop` і `owner` — точний збіг, порожнє значення → 422; `min_area` і `max_area` — включно.
- Список відсортований від нових до старих; `limit` типово 20, максимум 100; `offset` типово 0.
- Створення поля → 201; `created_at` — UTC з точністю до секунди, як у прикладі ТЗ; повторний POST
  з тим самим тілом створює ще одне поле.
- Приймаємо лише `Polygon`; внутрішні кільця (дірки) допустимі. Порядок обходу кілець не нав'язуємо.
- Координати з прикладів ТЗ — центр Києва (Майдан): реальних полів там немає, демо-поля стоять там
  лише заради прикладів із ТЗ. Решта сидів — у сільгоспрайонах.
- Числа в прикладах відповідей ТЗ ілюстративні: площа квадрата з ТЗ на еліпсоїді — **79.00 га**
  (у прикладі 45.2), відстань від точки з ТЗ до його центру — **241.7 м** (у прикладі 150.5).

## Сиди

`scripts/seed.py` сам заповнює порожню базу під час `docker compose up`: 2000 відтворюваних полів
(`--seed 42`).

- 10 сільгоспкластерів радіусом 30–50 км навколо районних центрів (Карлівка, Тульчин, Звенигородка,
  Бобринець, Старокостянтинів, Бердичів, Біла Церква, Красноград, Павлоград, Баштанка) — далеко від
  великих водойм. Рівномірний random по bbox України не підходить: він захоплює море й сусідні країни.
- Поле — прямокутник зі співвідношенням сторін від 1:1 до 1:4, випадковим поворотом і площею 0.5–300 га (дрібних більше).
- 10 культур з вагами (пшениця, соняшник, кукурудза — основні), ~100 власників (фізособи, ТОВ, ФГ).
- 10% полів спеціально перекривають інші (центр нового поля всередині вже створеного).
- Демо-поля: поле з ТЗ, ще два поля, що накривають точку з ТЗ (пошук з ТЗ → 3 поля), і два сусідні
  поля зі спільною межею.

```text
Seeded 2000 fields in 0.2s (overlapping: 210)
By crop: Пшениця 481, Соняшник 467, Кукурудза 404, Ячмінь 151, Соя 147, ...
Demo points:
  lon=30.5250 lat=50.4550  → 3 fields  (приклад ТЗ)
  lon=30.5700 lat=50.4750  → 2 fields  (спільна межа)
  lon=31.0000 lat=46.0000  → 0 fields  (море)
```

Параметри: `--count`, `--seed`, `--truncate`, `--overlap-ratio`. Без `--truncate` скрипт нічого не
робить, якщо таблиця не порожня.

## Що б я покращив

- **Авторизація:** JWT на запис (`POST`), читання відкрите.
- **Версіонування API:** `/api/v2/...` у разі першої несумісної зміни; поточні шляхи лишаються.
- **Захист від дублів у разі повторного POST:** заголовок `Idempotency-Key` (як у Stripe) — повтор з тим
  самим ключем повертає збережену відповідь. Ключі — у таблиці Postgres в одній транзакції зі вставкою
  або в Redis з TTL.
- **Rate limiting (429):** fixed-window у Redis через `INCR` + `EXPIRE`, відповідь з `Retry-After`.
- **UUIDv7** замість v4: вставки в кінець індексу первинного ключа.
- **Пошук за частковим збігом імені власника:** `pg_trgm` + GIN.
- **Keyset-пагінація** за `(created_at, id)` замість offset; наближений `total` на великих обсягах.
- **JSON-логи, чистий ASGI-middleware**, метрики (Prometheus, `pg_stat_statements`), OpenTelemetry.
- **Тести:** юніт-тести сервісу з моком репозиторію, навантажувальні (locust, k6), CI.

## Розробка

Локально (потрібні [uv](https://docs.astral.sh/uv/) і Docker):

```bash
uv sync                          # залежності, включно з dev
cp .env.example .env             # DATABASE_URL на localhost:5433
make db                          # лише PostGIS і pgAdmin
make migrate                     # uv run alembic upgrade head
uv run python -m scripts.seed    # сиди
uv run uvicorn app.main:app --reload
```

**Тести** — інтеграційні, на справжньому PostGIS у контейнері (testcontainers), схема — через міграції:

```bash
make test                        # uv run pytest; потрібен запущений Docker
```

`ST_Intersects`, `ST_IsValid` і `ST_Area(geography)` не перевірити на SQLite чи моках: тест перевіряв би
фейк, а не наш код.

**Нова міграція:** зміна моделі → `make revision m="опис"` → переглянути файл руками → закомітити;
у compose її застосує контейнер `migrate`.

PostGIS в образі `postgis/postgis:16-3.4` зібраний з GEOS 3.9 — від версії GEOS залежить текст
`ST_IsValidReason` (наприклад, `Self-intersection` vs `Ring Self-intersection`).
