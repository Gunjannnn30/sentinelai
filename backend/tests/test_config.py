"""Config normalisation that live deployment depends on.

Kept deliberately tiny: these two behaviours are what stop a fresh PaaS deploy
from crashing on its first database connection.
"""

from app.core.config import Settings


def test_bare_postgresql_url_is_pinned_to_psycopg3() -> None:
    # Render/Railway/Cloud Run all hand out this shape; we ship psycopg v3 only,
    # and bare `postgresql://` resolves to the absent psycopg2 dialect.
    settings = Settings(database_url="postgresql://user:pass@db:5432/sentinel")
    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/sentinel"


def test_legacy_postgres_scheme_is_pinned_to_psycopg3() -> None:
    settings = Settings(database_url="postgres://user:pass@db:5432/sentinel")
    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/sentinel"


def test_explicit_driver_and_sqlite_urls_are_untouched() -> None:
    pinned = "postgresql+psycopg://user:pass@db:5432/sentinel"
    assert Settings(database_url=pinned).database_url == pinned
    assert Settings(database_url="sqlite:///./data/x.db").database_url == "sqlite:///./data/x.db"
