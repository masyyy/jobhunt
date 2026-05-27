import pytest

from backend.core.tools.execute_sql.tool import is_read_only


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "select count(*) from orders",
        "  SELECT 1",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
        "with cte as (select * from orders) select * from cte",
        "  WITH t AS (SELECT 1) SELECT * FROM t",
    ],
)
def test_allows_read_only_queries(sql: str) -> None:
    assert is_read_only(sql.strip()) is True


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders VALUES (1)",
        "UPDATE orders SET x = 1",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "CREATE TABLE foo (id INT)",
        "ALTER TABLE orders ADD COLUMN x INT",
        "TRUNCATE TABLE orders",
        "insert into orders values (1)",
    ],
)
def test_rejects_write_queries(sql: str) -> None:
    assert is_read_only(sql.strip()) is False
