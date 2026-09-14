"""create Banboos 2.0 server foundation tables"""
from alembic import op

from packages.infrastructure.sql_models import Base

revision = "0001_server_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
