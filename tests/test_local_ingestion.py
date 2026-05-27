"""Tests for DeltaIngestionService: validation, append, error paths."""

from pathlib import Path

import polars as pl
import pytest
from deltalake import DeltaTable, Field, Schema
from deltalake.schema import PrimitiveType

from backend.core.interfaces.storage_config import DatasetStorageConfig
from backend.infrastructure.ingestion.local import DeltaIngestionService


def _create_delta_table(datasets_dir: Path, table_name: str, fields: list[Field]) -> None:
    """Stand in for `apply_delta_migrations.py` in unit tests."""
    DeltaTable.create(str(datasets_dir / table_name), schema=Schema(fields), mode="error")


@pytest.fixture()
def datasets_dir(tmp_path: Path) -> Path:
    d = tmp_path / "datasets"
    d.mkdir()
    return d


@pytest.fixture()
def service(datasets_dir: Path) -> DeltaIngestionService:
    config = DatasetStorageConfig(
        datasets_uri=str(datasets_dir),
        local_cache_dir=datasets_dir,
    )
    return DeltaIngestionService(storage_config=config)


@pytest.fixture()
def orders_fields() -> list[Field]:
    """Schema matching the `csv_file` fixture (id,name,amount)."""
    return [
        Field("id", PrimitiveType("long"), nullable=True),
        Field("name", PrimitiveType("string"), nullable=True),
        Field("amount", PrimitiveType("double"), nullable=True),
    ]


@pytest.fixture()
def tsv_fields() -> list[Field]:
    """Schema matching the `tsv_file` fixture (id,value)."""
    return [
        Field("id", PrimitiveType("long"), nullable=True),
        Field("value", PrimitiveType("string"), nullable=True),
    ]


@pytest.fixture()
def csv_file(tmp_path: Path) -> Path:
    f = tmp_path / "orders.csv"
    f.write_text("id,name,amount\n1,Acme,100.5\n2,Beta,200.0\n")
    return f


@pytest.fixture()
def tsv_file(tmp_path: Path) -> Path:
    f = tmp_path / "data.tsv"
    f.write_text("id\tvalue\n1\tabc\n2\tdef\n")
    return f


class TestTableNameValidation:
    def test_reject_path_traversal(self, service: DeltaIngestionService, csv_file: Path) -> None:
        with pytest.raises(ValueError, match="Invalid table name"):
            service.ingest(csv_file, "../../escape")

    def test_reject_absolute_path(self, service: DeltaIngestionService, csv_file: Path) -> None:
        with pytest.raises(ValueError, match="Invalid table name"):
            service.ingest(csv_file, "/abs/evil")

    def test_reject_dots(self, service: DeltaIngestionService, csv_file: Path) -> None:
        with pytest.raises(ValueError, match="Invalid table name"):
            service.ingest(csv_file, ".hidden")

    def test_reject_spaces(self, service: DeltaIngestionService, csv_file: Path) -> None:
        with pytest.raises(ValueError, match="Invalid table name"):
            service.ingest(csv_file, "has spaces")

    def test_reject_empty(self, service: DeltaIngestionService, csv_file: Path) -> None:
        with pytest.raises(ValueError, match="Invalid table name"):
            service.ingest(csv_file, "")

    def test_accept_alphanumeric_underscore_dash(
        self,
        service: DeltaIngestionService,
        csv_file: Path,
        datasets_dir: Path,
        orders_fields: list[Field],
    ) -> None:
        _create_delta_table(datasets_dir, "my-table_2", orders_fields)
        result = service.ingest(csv_file, "my-table_2")
        assert result.table_name == "my-table_2"


class TestUnsupportedFiles:
    def test_reject_unsupported_extension(
        self,
        service: DeltaIngestionService,
        tmp_path: Path,
        datasets_dir: Path,
        orders_fields: list[Field],
    ) -> None:
        _create_delta_table(datasets_dir, "test", orders_fields)
        f = tmp_path / "data.parquet"
        f.write_bytes(b"fake")
        with pytest.raises(ValueError, match="Unsupported file type"):
            service.ingest(f, "test")

    def test_reject_missing_file(self, service: DeltaIngestionService, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            service.ingest(tmp_path / "nonexistent.csv", "test")

    def test_reject_empty_csv(
        self,
        service: DeltaIngestionService,
        tmp_path: Path,
        datasets_dir: Path,
    ) -> None:
        _create_delta_table(
            datasets_dir,
            "test",
            [
                Field("id", PrimitiveType("long"), nullable=True),
                Field("name", PrimitiveType("string"), nullable=True),
            ],
        )
        f = tmp_path / "empty.csv"
        f.write_text("id,name\n")
        with pytest.raises(ValueError, match="no rows"):
            service.ingest(f, "test")


class TestAppend:
    def test_first_ingest_appends_at_version_one(
        self,
        service: DeltaIngestionService,
        csv_file: Path,
        datasets_dir: Path,
        orders_fields: list[Field],
    ) -> None:
        _create_delta_table(datasets_dir, "orders", orders_fields)
        result = service.ingest(csv_file, "orders")

        assert result.table_name == "orders"
        # Version 0 is the migration's CREATE; first append is version 1.
        assert result.delta_version == 1
        assert result.row_count == 2
        assert "id" in result.schema
        assert result.schema["id"] == "Int64"

        assert (datasets_dir / "orders" / "_delta_log").is_dir()

    def test_append_increments_version(
        self,
        service: DeltaIngestionService,
        csv_file: Path,
        datasets_dir: Path,
        orders_fields: list[Field],
    ) -> None:
        _create_delta_table(datasets_dir, "orders", orders_fields)
        r1 = service.ingest(csv_file, "orders")
        assert r1.delta_version == 1

        r2 = service.ingest(csv_file, "orders")
        assert r2.delta_version == 2
        assert r2.row_count == 2

    def test_append_preserves_data(
        self,
        service: DeltaIngestionService,
        csv_file: Path,
        datasets_dir: Path,
        orders_fields: list[Field],
    ) -> None:
        """After two appends, the Delta table should contain all rows."""
        _create_delta_table(datasets_dir, "orders", orders_fields)
        service.ingest(csv_file, "orders")
        service.ingest(csv_file, "orders")

        df = pl.read_delta(str(datasets_dir / "orders"))
        assert len(df) == 4  # 2 rows x 2 appends

    def test_tsv_support(
        self,
        service: DeltaIngestionService,
        tsv_file: Path,
        datasets_dir: Path,
        tsv_fields: list[Field],
    ) -> None:
        _create_delta_table(datasets_dir, "tsv_data", tsv_fields)
        result = service.ingest(tsv_file, "tsv_data")
        assert result.row_count == 2
        assert result.schema["value"] == "String"

    def test_missing_table_errors(
        self,
        service: DeltaIngestionService,
        csv_file: Path,
    ) -> None:
        """Ingesting into an unmigrated table must fail explicitly."""
        with pytest.raises(FileNotFoundError, match="does not exist"):
            service.ingest(csv_file, "unmigrated")

    def test_schema_mismatch_errors(
        self,
        service: DeltaIngestionService,
        datasets_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Extra columns in the batch must be a hard error — schema is migration-driven."""
        _create_delta_table(
            datasets_dir,
            "evolving",
            [
                Field("id", PrimitiveType("long"), nullable=True),
                Field("name", PrimitiveType("string"), nullable=True),
            ],
        )
        f = tmp_path / "v2.csv"
        f.write_text("id,name,score\n2,Beta,99\n")
        with pytest.raises(ValueError, match="Schema mismatch"):
            service.ingest(f, "evolving")
