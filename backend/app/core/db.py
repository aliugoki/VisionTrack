"""Database engine, session factory, and declarative base.

We use SQLAlchemy 2.0 async API throughout. Every request gets one
session via the `get_db` dependency. Modules import `Base` to declare
their models — the Base.metadata is what Alembic compares against.

Worker-vs-API engine config:
  Celery worker tasks each run their own `asyncio.run()` loop. A
  module-level connection pool would cache connections bound to one
  loop, then fail with "Event loop is closed" / "attached to a different
  loop" when the next task runs on a fresh loop. We detect Celery
  context via sys.argv[0] (Celery's entry point is literally `celery`)
  and use NullPool — every task gets a fresh connection that's closed
  on task end. Slightly less efficient than pooling but actually works.
"""

import sys
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class all ORM models inherit from."""
    pass


# True if running as `celery -A ... worker` or `celery -A ... beat`.
# sys.argv[0] in those processes is the celery binary path.
_is_celery_process = "celery" in (sys.argv[0] or "")


if _is_celery_process:
    engine = create_async_engine(
        settings.DATABASE_URL,
        # Workers can be noisy; SQL echo is off regardless of DEBUG.
        echo=False,
        # Critical: no pool. Each task creates + closes its own connection,
        # so connections never outlive the asyncio loop they were made on.
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG and settings.APP_ENV == "development",
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session.

    Commits on success, rolls back on any exception, always closes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
