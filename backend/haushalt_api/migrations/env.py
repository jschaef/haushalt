"""Alembic environment. init_db() runs the migrations on its own connection
(config.attributes["connection"]); the alembic CLI (backend/alembic.ini)
connects with HAUSHALT_DATABASE_URL like the app."""

from alembic import context

from haushalt_api.db import Base, engine

target_metadata = Base.metadata


def run(connection) -> None:
    # batch mode: SQLite can only change constraints by copying the table
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    with engine.begin() as own:
        run(own)
