# Fields API

REST API для керування сільськогосподарськими полями зі швидким пошуком полів, що містять задану точку.
Геометрію перевіряє й рахує PostGIS, пошук за точкою йде через GIST-індекс: на 100 000 полів — ~1 мс.

**Стек:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), GeoAlchemy2, Alembic,
PostgreSQL 16 + PostGIS 3.4, Docker Compose, uv, pytest + testcontainers.

## Швидкий старт

Потрібен Docker з **Docker Compose v2+** (команда `docker compose`).

```bash
git clone https://github.com/IhorVoskoboinikov/fields-test-app.git && cd fields-test-app
cp .env.example .env            # необов'язково: без .env діють ті самі значення за замовчуванням
docker compose up -d --build    # db → міграції → сиди (2000 полів) → api, а також pgAdmin
docker compose ps               # дочекатися, поки api стане healthy
```

Налаштування бази й логування — у `.env` (шаблон з коментарями — `.env.example`).

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
| Swagger UI (усі сценарії — кнопкою *Try it out*) | http://localhost:8000/docs |
| Postman | *Import* → `http://localhost:8000/openapi.json` |
| pgAdmin (Geometry Viewer показує полігони на карті) | http://localhost:5050, пароль бази `fields` |
| PostgreSQL з хоста | `localhost:5433`, база/користувач/пароль `fields` |

> На Mac з Apple Silicon образ `postgis/postgis` (лише amd64) працює через емуляцію Rosetta — повільніше.

| make | Без make | Що робить |
| --- | --- | --- |
| `make up` / `make down` | `docker compose up -d --build` / `docker compose down` | підняти / зупинити |
| `make reset` | `docker compose down -v` | зупинити й видалити дані БД |
| `make reseed` | `docker compose run --rm seed python -m scripts.seed --truncate` | перестворити 2000 полів |
| `make seed-large` | `docker compose run --rm seed python -m scripts.seed --truncate --count 100000` | 100 000 полів |
| `make test` | `uv run pytest` | тести (потрібен Docker) |
| `make bench` | `uv run python -m scripts.benchmark` | бенчмарк пошуку |

## API

Шляхи, параметри й тіла відповідей — рівно як у ТЗ.

| Метод | Шлях | Успіх | Помилки |
| --- | --- | --- | --- |
| POST | `/api/fields` | 201 | 400, 422 |
| GET | `/api/fields?crop=&owner=&min_area=&max_area=&limit=&offset=` | 200 | 422 |
| GET | `/api/fields/find-by-point?lon=&lat=` | 200 | 422 |
| GET | `/api/fields/{id}` | 200 | 404, 422 |
| GET | `/health` | 200 | 503 |

- **POST** — полігон має бути валідним: незамкнене кільце, не `Polygon`, координати поза діапазоном → 422
  (Pydantic); самоперетин → 400 `INVALID_GEOMETRY` з причиною й координатою, наприклад
  `Self-intersection[30.01 50.01]` (PostGIS `ST_IsValid`); площа ≤ 0.1 га → 400 `FIELD_AREA_TOO_SMALL`.
- **Список** — `{total, fields}` без геометрії, нові зверху; `limit` 1–100 (типово 20).
- **find-by-point** — усі поля, що містять точку (кілька, якщо поля перекриваються), за відстанню до
  центру поля; `query_time_ms` — час SQL-запиту пошуку.
- **Помилки** — єдиний формат `{"error": {code, message, details}}` (`details` — лише якщо є); `request_id` запиту —
  у заголовку `X-Request-ID` і в кожному рядку логу.

## Архітектурні рішення

```text
router (HTTP) → service (бізнес-правила, транзакція) → repository (SQL/PostGIS) → AsyncSession
```

Роутер не пише SQL, сервіс не знає про HTTP (кидає доменні винятки, у відповідь їх перетворює одне
місце — `app/core/error_handlers.py`), репозиторій не комітить. Pydantic перевіряє **форму** даних,
PostGIS — **зміст** геометрії. Схему БД створюють лише міграції Alembic.

**Ключовий запит** — пошук полів, що містять точку:

```sql
SELECT id, name, area_ha, crop, owner,
       ST_Distance(ST_Centroid(geom)::geography, :point::geography) AS distance_to_center_m
FROM fields
WHERE ST_Intersects(geom, :point)          -- :point = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
ORDER BY distance_to_center_m;
```

`ST_Intersects` використовує GIST-індекс (`geom && point`): індекс відбирає поля, чий обмежувальний
прямокутник містить точку, і точна перевірка йде лише для них. Відстань рахується лише для знайдених полів.

| Рішення | Чому |
| --- | --- |
| `geometry(Polygon, 4326)` + каст у `::geography` для метрів | для «точка всередині поля?» вистачає градусів, і з ними працює швидкий індекс; площу й відстань рахуємо на еліпсоїді |
| GIST-індекс по `geom` | ключова оптимізація: пошук за деревом прямокутників замість перебору таблиці |
| `area_ha` — generated column | площу рахує база один раз під час запису; фільтр за площею — звичайний btree-індекс |
| btree по `owner`, `area_ha`; по `crop` — ні | одна основна культура — 20–24% рядків, індекс не допоможе |
| `ST_Intersects`, а не `ST_Contains` | точка на межі поля вважається всередині |
| невалідний полігон відхиляємо, а не виправляємо | ТЗ вимагає валідації; `ST_MakeValid` мовчки змінив би форму поля |
| `total` окремим `count(*)` | коректний навіть для порожньої сторінки (`offset` > кількості) |
| CHECK-констрейнти `ST_IsValid` і `area_ha > 0.1` | страхують запис в обхід API (сиди) |
| middleware з `X-Request-ID` | трасування запиту від входу до логу і тіла помилки |

**Продуктивність** (`make bench`: 1000 точок, лише SQL-запит пошуку):

| Полів | Індекс | p50, мс | p95, мс |
| --- | --- | --- | --- |
| 2 000 | GIST | 0.80 | 1.57 |
| 100 000 | GIST | 1.00 | 1.64 |
| 100 000 | немає | 118.34 | 141.26 |

З індексом час майже не росте з обсягом даних, без індексу — росте лінійно. `EXPLAIN ANALYZE` на
100 000 полів: `Index Scan using ix_fields_geom`, 0.28 мс проти `Parallel Seq Scan`, 126 мс.

**Сиди** (`scripts/seed.py`): 2000 відтворюваних полів у 10 сільгоспкластерах України, різних розмірів
(0.5–300 га), культур і власників, 10% полів перекриваються; плюс демо-поля для запитів з ТЗ.

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

## Тести й лінтер

Застосунок запускається лише через `docker compose` (див. «Швидкий старт»). Тести й бенчмарк
запускаються на хості через [uv](https://docs.astral.sh/uv/):

```bash
uv sync                          # залежності для тестів і бенчмарку
make test                        # інтеграційні тести на справжньому PostGIS (testcontainers)
make lint
```

Тести — 30 інтеграційних сценаріїв на справжньому PostGIS у контейнері, схема — через міграції:
`ST_Intersects`, `ST_IsValid` і `ST_Area(geography)` не перевірити на SQLite чи моках.
