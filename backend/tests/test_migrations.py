"""Alembic: the migrations build exactly the schema of the models, and a
database from before Alembic is completed and stamped as the baseline."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from haushalt_api import db as db_module
from haushalt_api.db import Base, engine


def test_migrations_match_the_models():
    # fresh_db built this database with the migrations alone
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []
        assert context.get_current_revision() is not None


def test_database_from_before_alembic_is_stamped(tmp_path, monkeypatch):
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64) UNIQUE, display_name VARCHAR(128), "
            "password_hash VARCHAR(256), locale VARCHAR(8), created_at TIMESTAMP)"
        ))
        connection.execute(text("INSERT INTO users (id, username, display_name, password_hash, locale) VALUES (1, 'a', 'A', 'x', 'de')"))
    monkeypatch.setattr(db_module, "engine", old)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=old, expire_on_commit=False))
    db_module.init_db()
    with old.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() is not None
        assert connection.execute(text("SELECT username FROM users")).scalar() == "a"
    assert {"is_admin", "token_version"} <= {c["name"] for c in inspect(old).get_columns("users")}
    # a second start changes nothing
    db_module.init_db()
