import os
import re
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Convert URL scheme for asyncpg
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Check if original URL required SSL
needs_ssl = "sslmode=require" in DATABASE_URL or "sslmode=verify" in DATABASE_URL

# Strip sslmode from URL (asyncpg uses connect_args for ssl)
DATABASE_URL_CLEAN = re.sub(r"[?&]sslmode=\w+", "", DATABASE_URL)
DATABASE_URL_CLEAN = DATABASE_URL_CLEAN.rstrip("?&")

connect_args = {}
if needs_ssl:
    import ssl
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ssl_ctx

engine = create_async_engine(
    DATABASE_URL_CLEAN,
    echo=False,
    connect_args=connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    # Import all models explicitly so SQLAlchemy registers them before create_all
    from backend.models import (  # noqa: F401
        User, Session, Message, Document, Chunk, Memory,
        ToolRun, Finding, VoiceInteraction, WorkspaceRecord,
        BrainVisitedPage, BrainFrontier, BrainDeadLetter, BrainStats
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
