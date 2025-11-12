"""Database models and helpers using SQLAlchemy."""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

try:
    from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, create_engine
    from sqlalchemy.orm import declarative_base, sessionmaker
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    JSON = dict  # type: ignore
    Column = lambda *args, **kwargs: None  # type: ignore
    DateTime = Float = Integer = String = object  # type: ignore

    def create_engine(*args, **kwargs):  # type: ignore
        raise RuntimeError("sqlalchemy not available")

    def declarative_base():  # type: ignore
        class Base:  # minimal stand-in
            metadata = type("Meta", (), {"create_all": staticmethod(lambda *_, **__: None)})

        return Base

    def sessionmaker(*args, **kwargs):  # type: ignore
        def factory():
            raise RuntimeError("sqlalchemy session unavailable")

        return factory

    SQLALCHEMY_AVAILABLE = False
else:
    SQLALCHEMY_AVAILABLE = True

from ..config import get_config

Base = declarative_base()


def _engine_url() -> str:
    return get_config().storage.url


def _engine():
    if not SQLALCHEMY_AVAILABLE:
        raise RuntimeError("sqlalchemy engine unavailable")
    return create_engine(_engine_url(), echo=False, future=True)


if SQLALCHEMY_AVAILABLE:
    SessionLocal = sessionmaker(bind=_engine(), autoflush=False, autocommit=False)
else:  # pragma: no cover - offline fallback
    SessionLocal = None


@contextmanager
def session_scope() -> Generator:
    """Provide a transactional scope around operations."""

    if SessionLocal is None:
        class DummySession:
            def add(self, *_args, **_kwargs):
                pass

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        session = DummySession()
    else:
        session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class Bar(Base):
    __tablename__ = "bars"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True, nullable=False)
    interval = Column(String, nullable=False)
    open_time = Column(DateTime, index=True, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    exchange_id = Column(String, index=True)
    symbol = Column(String, index=True, nullable=False)
    side = Column(String, nullable=False)
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, index=True)
    symbol = Column(String, nullable=False)
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fee = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, unique=True)
    qty = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Funding(Base):
    __tablename__ = "funding"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True)
    rate = Column(Float, nullable=False)
    payment = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class PnL(Base):
    __tablename__ = "pnl"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True)
    realized = Column(Float, nullable=False)
    unrealized = Column(Float, nullable=False)
    equity = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class Metric(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True)
    run_id = Column(String, index=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def init_db(create_all: bool = True) -> None:
    """Initialise database with tables."""

    if SQLALCHEMY_AVAILABLE:
        engine = _engine()
        if create_all:
            Base.metadata.create_all(engine)


def record_metric(run_id: str, payload: dict) -> None:
    """Persist metric payload."""

    if SQLALCHEMY_AVAILABLE:
        with session_scope() as session:
            session.add(Metric(run_id=run_id, payload=payload))
    else:  # pragma: no cover - offline fallback
        path = Path("runs") / run_id
        path.mkdir(parents=True, exist_ok=True)
        out = path / "metrics.json"
        existing = []
        if out.exists():
            existing = json.loads(out.read_text())
        existing.append({"run_id": run_id, "payload": payload})
        out.write_text(json.dumps(existing, indent=2))


__all__ = [
    "session_scope",
    "init_db",
    "record_metric",
    "Bar",
    "Order",
    "Trade",
    "Position",
    "Funding",
    "PnL",
    "Metric",
]
