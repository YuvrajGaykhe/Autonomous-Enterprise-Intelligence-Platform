"""
Alembic migration environment for AI CEO Layer 1.

This module configures Alembic to:
  1. Read the database URL from the project's Settings (app.core.config),
     overriding the placeholder in alembic.ini.
  2. Use the shared SQLAlchemy metadata from app.core.database.Base,
     so that autogenerate can detect model changes introduced in B1+.
  3. Run migrations synchronously using psycopg2 (the project's chosen driver).

Supports both offline (SQL script generation) and online (direct DB) modes.
"""

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the project root is on sys.path so that `app.*` imports resolve
# when running Alembic from any working directory (local or Docker).
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import get_settings
from app.core.database import Base

# This is the Alembic Config object, providing access to alembic.ini values.
config = context.config

# Override the placeholder sqlalchemy.url with the real, environment-driven URL.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.effective_database_url)

# The MetaData object for autogenerate support.
# When B1 adds ORM models that inherit from Base, Alembic will detect them.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database.
    Useful for review or environments where a live DB isn't available.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Creates a synchronous engine connection and runs migrations
    directly against the database.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
