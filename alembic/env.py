"""Alembic environment.

The database URL is resolved in this order:
1. ``sqlalchemy.url`` set on the Config object (tests set this programmatically),
2. the ``BGAPP_DB_URL`` environment variable,
so a real patient DB path is never committed to the repo.
"""

from __future__ import annotations

import os

from sqlalchemy import engine_from_config, pool

from alembic import context
from data.tables import Base

config = context.config

_url = config.get_main_option("sqlalchemy.url") or os.environ.get("BGAPP_DB_URL")
if _url:
    config.set_main_option("sqlalchemy.url", _url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
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
            render_as_batch=True,  # SQLite: batch mode for ALTER support
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
