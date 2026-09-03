from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from ecdat.persistence.sql.base import Base
from ecdat.persistence.sql import models  # noqa: F401
from ecdat.settings import get_settings

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().postgres_dsn)
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except KeyError:
        pass

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
