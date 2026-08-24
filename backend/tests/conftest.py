import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AuditLog, FailedPayment  # noqa: F401 -- registers tables on Base


@pytest.fixture()
def db():
    # StaticPool keeps every connection pointed at the SAME in-memory
    # database. Without it SQLite hands each connection its own blank one, so
    # a test driving the app through TestClient (which runs the request in a
    # separate thread) would write to a different database than it asserts
    # against, and silently see nothing.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
