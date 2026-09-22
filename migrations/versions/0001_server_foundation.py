"""create Banboos 2.0 server foundation tables"""
from alembic import op

from packages.infrastructure.sql_models import Base

revision = "0001_server_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    foundation_tables = [Base.metadata.tables[name] for name in (
        "tenants", "stations", "telemetry_points", "run_records"
    )]
    Base.metadata.create_all(bind=bind, tables=foundation_tables)


def downgrade() -> None:
    bind = op.get_bind()
    foundation_tables = [Base.metadata.tables[name] for name in (
        "run_records", "telemetry_points", "stations", "tenants"
    )]
    Base.metadata.drop_all(bind=bind, tables=foundation_tables)
