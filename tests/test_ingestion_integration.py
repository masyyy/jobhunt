"""Integration tests: ingestion task with DB logging, concurrency safety."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.interfaces.ingestion_log import IngestionLogRepositoryInterface
from backend.core.interfaces.storage_config import DatasetStorageConfig
from backend.core.tasks.ingest_file import ingest_file
from backend.infrastructure.db.models.base import Base
from backend.infrastructure.db.repositories.ingestion_log_repository import IngestionLogRepository
from backend.infrastructure.ingestion.local import DeltaIngestionService


def _create_delta_table(datasets_dir: Path, table_name: str, fields: list[Field]) -> None:
    """Stand in for `apply_delta_migrations.py` in unit tests."""
    DeltaTable.create(str(datasets_dir / table_name), schema=Schema(fields), mode="error")


_ORDERS_FIELDS = [
    Field("id", PrimitiveType("long"), nullable=True),
    Field("name", PrimitiveType("string"), nullable=True),
    Field("amount", PrimitiveType("double"), nullable=True),
]
_ID_VALUE_FIELDS = [
    Field("id", PrimitiveType("long"), nullable=True),
    Field("value", PrimitiveType("string"), nullable=True),
]


async def _create_session_factory(db_path: Path | None = None) -> async_sessionmaker[AsyncSession]:
    url = f"sqlite+aiosqlite:///{db_path}" if db_path else "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture()
def datasets_dir(tmp_path: Path) -> Path:
    d = tmp_path / "datasets"
    d.mkdir()
    return d


@pytest.fixture()
def csv_file(tmp_path: Path) -> Path:
    f = tmp_path / "orders.csv"
    f.write_text("id,name,amount\n1,Acme,100.5\n2,Beta,200.0\n")
    return f


class TestIngestFileTask:
    """Test the full async task handler with real DB logging."""

    @pytest.mark.asyncio
    async def test_task_writes_log_to_db(self, datasets_dir: Path, csv_file: Path) -> None:
        _create_delta_table(datasets_dir, "orders", _ORDERS_FIELDS)
        session_factory = await _create_session_factory()
        service = DeltaIngestionService(
            storage_config=DatasetStorageConfig(datasets_uri=str(datasets_dir), local_cache_dir=datasets_dir)
        )

        @asynccontextmanager
        async def repo_factory() -> AsyncIterator[IngestionLogRepositoryInterface]:
            async with session_factory() as session:
                yield IngestionLogRepository(session)

        await ingest_file(
            ingestion_service=service,
            log_repo_factory=repo_factory,
            file_path=str(csv_file),
            table="orders",
        )

        async with session_factory() as session:
            result = await session.execute(text("SELECT * FROM ingestion_log"))
            rows = result.fetchall()

        assert len(rows) == 1
        row = rows[0]
        assert row.source_file == str(csv_file)
        assert row.delta_table == "orders"
        # Version 0 is the migration's CREATE; first append is version 1.
        assert row.delta_version == 1
        assert row.row_count == 2

    @pytest.mark.asyncio
    async def test_task_logs_append_version(self, datasets_dir: Path, csv_file: Path) -> None:
        _create_delta_table(datasets_dir, "orders", _ORDERS_FIELDS)
        session_factory = await _create_session_factory()
        service = DeltaIngestionService(
            storage_config=DatasetStorageConfig(datasets_uri=str(datasets_dir), local_cache_dir=datasets_dir)
        )

        @asynccontextmanager
        async def repo_factory() -> AsyncIterator[IngestionLogRepositoryInterface]:
            async with session_factory() as session:
                yield IngestionLogRepository(session)

        await ingest_file(
            ingestion_service=service,
            log_repo_factory=repo_factory,
            file_path=str(csv_file),
            table="orders",
        )
        await ingest_file(
            ingestion_service=service,
            log_repo_factory=repo_factory,
            file_path=str(csv_file),
            table="orders",
        )

        async with session_factory() as session:
            result = await session.execute(text("SELECT delta_version FROM ingestion_log ORDER BY created_at"))
            versions = [r[0] for r in result.fetchall()]

        assert versions == [1, 2]


class TestConcurrentIngestion:
    """Verify that concurrent ingestion tasks don't lose DB log entries."""

    @pytest.mark.asyncio
    async def test_concurrent_tasks_all_logged(self, datasets_dir: Path, tmp_path: Path) -> None:
        """Run N ingestion tasks concurrently to different tables — all must be logged."""
        session_factory = await _create_session_factory(tmp_path / "concurrent.db")
        service = DeltaIngestionService(
            storage_config=DatasetStorageConfig(datasets_uri=str(datasets_dir), local_cache_dir=datasets_dir)
        )

        @asynccontextmanager
        async def repo_factory() -> AsyncIterator[IngestionLogRepositoryInterface]:
            async with session_factory() as session:
                yield IngestionLogRepository(session)

        n = 5
        csv_files = []
        for i in range(n):
            f = tmp_path / f"data_{i}.csv"
            f.write_text(f"id,value\n{i},item_{i}\n")
            csv_files.append(f)
            _create_delta_table(datasets_dir, f"table_{i}", _ID_VALUE_FIELDS)

        tasks = [
            ingest_file(
                ingestion_service=service,
                log_repo_factory=repo_factory,
                file_path=str(csv_files[i]),
                table=f"table_{i}",
            )
            for i in range(n)
        ]

        await asyncio.gather(*tasks)

        async with session_factory() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM ingestion_log"))
            count = result.scalar()

        assert count == n

    @pytest.mark.asyncio
    async def test_concurrent_appends_to_same_table(self, datasets_dir: Path, tmp_path: Path) -> None:
        """Sequential appends to the same table must each be logged with correct versions."""
        session_factory = await _create_session_factory()
        service = DeltaIngestionService(
            storage_config=DatasetStorageConfig(datasets_uri=str(datasets_dir), local_cache_dir=datasets_dir)
        )

        @asynccontextmanager
        async def repo_factory() -> AsyncIterator[IngestionLogRepositoryInterface]:
            async with session_factory() as session:
                yield IngestionLogRepository(session)

        _create_delta_table(datasets_dir, "shared", _ID_VALUE_FIELDS)
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,value\n1,abc\n")

        # Sequential appends (Delta doesn't support truly concurrent writes to same table)
        for _ in range(3):
            await ingest_file(
                ingestion_service=service,
                log_repo_factory=repo_factory,
                file_path=str(csv_file),
                table="shared",
            )

        async with session_factory() as session:
            result = await session.execute(text("SELECT delta_version FROM ingestion_log ORDER BY delta_version"))
            versions = [r[0] for r in result.fetchall()]

        # Version 0 is the migration's CREATE; appends are 1, 2, 3.
        assert versions == [1, 2, 3]


class TestPathContainment:
    """Verify that file_path is rejected when outside allowed_dir."""

    @pytest.mark.asyncio
    async def test_reject_file_outside_allowed_dir(self, datasets_dir: Path, tmp_path: Path) -> None:
        """A file outside the allowed directory must be rejected."""
        session_factory = await _create_session_factory()
        service = DeltaIngestionService(
            storage_config=DatasetStorageConfig(datasets_uri=str(datasets_dir), local_cache_dir=datasets_dir)
        )

        @asynccontextmanager
        async def repo_factory() -> AsyncIterator[IngestionLogRepositoryInterface]:
            async with session_factory() as session:
                yield IngestionLogRepository(session)

        # Create a file outside the allowed dir
        outside_file = tmp_path / "outside" / "secret.csv"
        outside_file.parent.mkdir()
        outside_file.write_text("id,value\n1,abc\n")

        allowed = tmp_path / "allowed"
        allowed.mkdir()

        with pytest.raises(ValueError, match="outside the allowed directory"):
            await ingest_file(
                ingestion_service=service,
                log_repo_factory=repo_factory,
                file_path=str(outside_file),
                table="test",
                allowed_dir=allowed,
            )

    @pytest.mark.asyncio
    async def test_accept_file_inside_allowed_dir(self, datasets_dir: Path, tmp_path: Path) -> None:
        """A file inside the allowed directory must be accepted."""
        _create_delta_table(datasets_dir, "test", _ID_VALUE_FIELDS)
        session_factory = await _create_session_factory()
        service = DeltaIngestionService(
            storage_config=DatasetStorageConfig(datasets_uri=str(datasets_dir), local_cache_dir=datasets_dir)
        )

        @asynccontextmanager
        async def repo_factory() -> AsyncIterator[IngestionLogRepositoryInterface]:
            async with session_factory() as session:
                yield IngestionLogRepository(session)

        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,value\n1,abc\n")

        await ingest_file(
            ingestion_service=service,
            log_repo_factory=repo_factory,
            file_path=str(csv_file),
            table="test",
            allowed_dir=tmp_path,
        )

        async with session_factory() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM ingestion_log"))
            assert result.scalar() == 1
