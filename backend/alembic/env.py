"""Alembic environment configuration.

We use the sync URL because Alembic doesn't yet have great async support
for autogenerate. Imports every model module so Base.metadata is complete.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.core.config import settings
from app.core.db import Base

# Importing the models registers them with Base.metadata so autogenerate sees them
from app.modules.tenants import models as _tenants  # noqa: F401
from app.modules.roles import models as _roles  # noqa: F401
from app.modules.users import models as _users  # noqa: F401
from app.modules.sites import models as _sites  # noqa: F401
from app.modules.cameras import models as _cameras  # noqa: F401
from app.modules.alerts import models as _alerts  # noqa: F401
from app.modules.floor_plans import models as _floor_plans  # noqa: F401
from app.modules.tracks import models as _tracks  # noqa: F401
from app.modules.live_wall import models as _live_wall  # noqa: F401
from app.modules.recordings import models as _recordings  # noqa: F401
from app.modules.persons import models as _persons  # noqa: F401
from app.modules.mv3dt import models as _mv3dt  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# DB-side artifacts not declared in any SQLAlchemy model. We exclude
# them from autogenerate so `alembic check` doesn't flag them.
#
# - tenants_subdomain_key: Postgres auto-named UNIQUE constraint. Model
#   declares unique=True (which alembic treats as an index, not a named
#   constraint), so the named constraint appears as DB-only.
# - track_points_ts_idx: Auto-created by TimescaleDB on hypertable
#   creation. Required for hypertable operations, must not be dropped.

def _include_object(object, name, type_, reflected, compare_to):
    EXCLUDED = {
        ("unique_constraint", "tenants_subdomain_key"),
        ("index", "track_points_ts_idx"),
    }
    if (type_, name) in EXCLUDED:
        return False
    return True


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
