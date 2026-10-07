"""create fields table

Revision ID: 85509a646877
Revises:
Create Date: 2026-10-06 09:55:59.556717

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "85509a646877"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "fields",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("crop", sa.String(length=100), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column(
            "geom",
            Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        # Площа на еліпсоїді Землі в гектарах; база рахує її сама при кожному записі
        sa.Column(
            "area_ha",
            sa.Double(),
            sa.Computed("ST_Area(geom::geography) / 10000", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True, precision=0),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ST_IsValid(geom)", name=op.f("ck_fields_geom_valid")),
        sa.CheckConstraint("area_ha > 0.1", name=op.f("ck_fields_area_min")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fields")),
    )

    # Ключовий індекс: пошук полів, що містять точку
    op.create_index("ix_fields_geom", "fields", ["geom"], postgresql_using="gist")
    op.create_index(op.f("ix_fields_owner"), "fields", ["owner"])
    op.create_index(op.f("ix_fields_area_ha"), "fields", ["area_ha"])
    # Стабільне сортування списку: нові зверху, id — tie-breaker
    op.create_index(
        "ix_fields_created_at_id",
        "fields",
        [sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
    )


def downgrade() -> None:
    """Видаляє таблицю разом з індексами. Розширення postgis не чіпаємо."""
    op.drop_table("fields")
