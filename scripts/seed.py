"""Seed the project with plausible manufacturing company data.

Creates:
  - ERP/CRM-style Delta Lake tables (unfriendly names)
  - Semantic SQL views with agent-friendly schemas
  - Example task outputs for the generate-signals task (production + sales)

Usage:
    uv run python scripts/seed.py
    uv run python scripts/seed.py --clean   # wipe existing data first
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import logging
import random
import shutil
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import settings
from backend.core.interfaces.storage_config import DatasetStorageConfig
from backend.core.interfaces.task_output_repository import TaskOutputRepositoryInterface
from backend.core.tasks.generate_signals import TASK_NAME as GENERATE_SIGNALS_TASK
from backend.core.tasks.generate_signals import generate_signals
from backend.customer.toolboxes import Toolbox
from backend.infrastructure.db.repositories.task_output_repository import TaskOutputRepository
from backend.infrastructure.ingestion.local import DeltaIngestionService

logger = logging.getLogger(__name__)

DATASETS_DIR = settings.DATASETS_DIR
VIEWS_DIR = DATASETS_DIR / "views"
SCRATCH_DIR = ROOT / "data" / "_seed_tmp"


def _get_async_engine() -> AsyncEngine:
    """Create an async engine using the same DATABASE_URL as the app."""
    return create_async_engine(settings.database_url, echo=False)


# ---------------------------------------------------------------------------
# Constants — the manufacturing universe
# ---------------------------------------------------------------------------

LINES = ["L-101", "L-102", "L-103", "L-104", "L-105"]
MACHINES = {
    "L-101": ["CNC-1A", "CNC-1B", "LATHE-1"],
    "L-102": ["PRESS-2A", "PRESS-2B"],
    "L-103": ["WELD-3A", "WELD-3B", "WELD-3C"],
    "L-104": ["ASSY-4A", "ASSY-4B", "ASSY-4C", "ASSY-4D"],
    "L-105": ["PAINT-5A", "PAINT-5B"],
}
ALL_MACHINES = [m for ms in MACHINES.values() for m in ms]

DOWNTIME_REASONS = [
    ("MECH_FAIL", "Mechanical failure"),
    ("ELEC_FAIL", "Electrical fault"),
    ("TOOL_WEAR", "Tool wear / breakage"),
    ("MAINT_SCHED", "Scheduled maintenance"),
    ("MAINT_UNSCHED", "Unscheduled maintenance"),
    ("MAT_SHORT", "Material shortage"),
    ("OPER_ERR", "Operator error"),
    ("QUAL_HOLD", "Quality hold"),
    ("CHANGEOVER", "Product changeover"),
    ("UTIL_OUTAGE", "Utility outage (air/power/water)"),
]

PRODUCTS = [
    ("SKU-1001", "Precision Shaft Assembly", "Drivetrain"),
    ("SKU-1002", "Hydraulic Valve Block", "Hydraulics"),
    ("SKU-1003", "Motor Housing", "Enclosures"),
    ("SKU-1004", "Control Panel Frame", "Enclosures"),
    ("SKU-1005", "Gearbox Plate", "Drivetrain"),
    ("SKU-1006", "Pump Impeller", "Hydraulics"),
    ("SKU-1007", "Bearing Sleeve", "Drivetrain"),
    ("SKU-1008", "Weld Bracket", "Structural"),
    ("SKU-1009", "Mounting Flange", "Structural"),
    ("SKU-1010", "Heat Exchanger Tube", "Thermal"),
]

CUSTOMERS = [
    ("C-4010", "Midwest Industrial Supply", "IL", "Tier 1"),
    ("C-4011", "Great Lakes Manufacturing Co", "MI", "Tier 1"),
    ("C-4012", "Pacific Rim Automation", "CA", "Tier 1"),
    ("C-4013", "Southern Hydraulics Inc", "TX", "Tier 2"),
    ("C-4014", "Northeast Precision Parts", "PA", "Tier 2"),
    ("C-4015", "Rocky Mountain Equipment", "CO", "Tier 2"),
    ("C-4016", "Delta Fabrication LLC", "OH", "Tier 3"),
    ("C-4017", "Sunrise Mechanical", "FL", "Tier 3"),
    ("C-4018", "Atlas Assembly Corp", "IN", "Tier 2"),
    ("C-4019", "Cascade Engineering Works", "WA", "Tier 1"),
]

SALES_REPS = [
    ("SR-01", "Martinez, R."),
    ("SR-02", "Chen, L."),
    ("SR-03", "Williams, D."),
    ("SR-04", "Kowalski, P."),
]

NOW = datetime(2026, 3, 15)
YEAR_AGO = NOW - timedelta(days=365)

rng = random.Random(42)  # noqa: S311

# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------


def _rand_ts(start: datetime, end: datetime) -> datetime:
    delta = (end - start).total_seconds()
    return start + timedelta(seconds=rng.random() * delta)


def generate_downtime_events() -> list[dict[str, str]]:
    """ERP table: PP_DWNTIME_LOG — production downtime events."""
    rows: list[dict[str, str]] = []
    for _ in range(600):
        line = rng.choice(LINES)
        machine = rng.choice(MACHINES[line])
        start = _rand_ts(YEAR_AGO, NOW - timedelta(hours=1))
        duration_min = rng.choices(
            [rng.randint(5, 30), rng.randint(30, 120), rng.randint(120, 480), rng.randint(480, 1440)],
            weights=[40, 35, 20, 5],
        )[0]
        end = start + timedelta(minutes=duration_min)
        reason_code, _ = rng.choice(DOWNTIME_REASONS)
        shift = "A" if start.hour < 8 else ("B" if start.hour < 16 else "C")
        rows.append(
            {
                "EVT_ID": str(len(rows) + 50000),
                "WRKCTR_ID": line,
                "EQUIP_NO": machine,
                "DT_START": start.strftime("%Y-%m-%d %H:%M:%S"),
                "DT_END": end.strftime("%Y-%m-%d %H:%M:%S"),
                "DUR_MIN": str(duration_min),
                "RSN_CD": reason_code,
                "SHIFT_CD": shift,
                "RPRT_BY": f"OP-{rng.randint(100, 199)}",
                "NOTES": "",
            }
        )
    return rows


def generate_production_orders() -> list[dict[str, str]]:
    """ERP table: PP_PRODORD — production orders / work orders."""
    rows: list[dict[str, str]] = []
    for i in range(400):
        sku, _, _ = rng.choice(PRODUCTS)
        line = rng.choice(LINES)
        start = _rand_ts(YEAR_AGO, NOW - timedelta(days=1))
        planned_qty = rng.choice([50, 100, 200, 500, 1000])
        scrap_rate = rng.uniform(0.01, 0.08)
        actual_qty = max(1, int(planned_qty * (1 - rng.uniform(0, scrap_rate * 2))))
        status = rng.choices(["COMP", "COMP", "COMP", "COMP", "WIP", "HOLD"], weights=[50, 20, 15, 5, 8, 2])[0]
        rows.append(
            {
                "ORD_NO": f"PO-{30000 + i}",
                "MAT_NO": sku,
                "WRKCTR_ID": line,
                "PLANNED_QTY": str(planned_qty),
                "ACTUAL_QTY": str(actual_qty),
                "SCRAP_QTY": str(planned_qty - actual_qty),
                "UOM": "EA",
                "ORD_STATUS": status,
                "SCHED_START": start.strftime("%Y-%m-%d"),
                "SCHED_END": (start + timedelta(days=rng.randint(1, 10))).strftime("%Y-%m-%d"),
                "ACT_START": start.strftime("%Y-%m-%d"),
                "ACT_END": (start + timedelta(days=rng.randint(1, 12))).strftime("%Y-%m-%d")
                if status == "COMP"
                else "",
            }
        )
    return rows


def generate_products() -> list[dict[str, str]]:
    """ERP table: MM_MATMASTER — material master / product catalog."""
    rows: list[dict[str, str]] = []
    for sku, desc, group in PRODUCTS:
        rows.append(
            {
                "MAT_NO": sku,
                "MAT_DESC": desc,
                "MAT_GRP": group,
                "BASE_UOM": "EA",
                "STD_COST": f"{rng.uniform(45, 650):.2f}",
                "LIST_PRC": f"{rng.uniform(80, 1200):.2f}",
                "WEIGHT_KG": f"{rng.uniform(0.5, 85):.1f}",
                "STAT": "ACTV",
            }
        )
    return rows


def generate_customers() -> list[dict[str, str]]:
    """CRM table: CRM_ACCT — customer accounts."""
    rows: list[dict[str, str]] = []
    for cid, name, state, tier in CUSTOMERS:
        rows.append(
            {
                "ACCT_ID": cid,
                "ACCT_NM": name,
                "ST_CD": state,
                "TIER_CD": tier,
                "CRTD_DT": (YEAR_AGO - timedelta(days=rng.randint(365, 2000))).strftime("%Y-%m-%d"),
                "OWN_REP": rng.choice(SALES_REPS)[0],
                "STAT_CD": "A",
            }
        )
    return rows


def generate_sales_orders() -> list[dict[str, str]]:
    """CRM/ERP table: SD_SALESORD — sales orders."""
    rows: list[dict[str, str]] = []
    for i in range(500):
        cust = rng.choice(CUSTOMERS)
        sku, _, _ = rng.choice(PRODUCTS)
        order_date = _rand_ts(YEAR_AGO, NOW - timedelta(days=1))
        qty = rng.choice([10, 25, 50, 100, 200, 500])
        unit_prc = rng.uniform(80, 1200)
        rows.append(
            {
                "SO_NO": f"SO-{70000 + i}",
                "ACCT_ID": cust[0],
                "MAT_NO": sku,
                "ORD_DT": order_date.strftime("%Y-%m-%d"),
                "REQ_DT": (order_date + timedelta(days=rng.randint(7, 45))).strftime("%Y-%m-%d"),
                "QTY": str(qty),
                "UOM": "EA",
                "UNIT_PRC": f"{unit_prc:.2f}",
                "NET_VAL": f"{qty * unit_prc:.2f}",
                "CURR": "USD",
                "SO_STATUS": rng.choices(["DLVD", "DLVD", "DLVD", "OPEN", "PRTL"], weights=[55, 15, 10, 12, 8])[0],
                "SLS_REP": rng.choice(SALES_REPS)[0],
            }
        )
    return rows


def generate_quotes() -> list[dict[str, str]]:
    """CRM table: CRM_QUOTES — sales quotes / proposals."""
    rows: list[dict[str, str]] = []
    for i in range(120):
        cust = rng.choice(CUSTOMERS)
        sku, _, _ = rng.choice(PRODUCTS)
        created = _rand_ts(NOW - timedelta(days=90), NOW - timedelta(days=1))
        qty = rng.choice([25, 50, 100, 250, 500])
        unit_prc = rng.uniform(80, 1200)
        days_open = (NOW - created).days

        # Some quotes are won, some lost, many still open
        if days_open > 30:
            status = rng.choices(["WON", "LOST", "OPEN", "EXPIRED"], weights=[30, 25, 30, 15])[0]
        elif days_open > 14:
            status = rng.choices(["WON", "LOST", "OPEN"], weights=[20, 10, 70])[0]
        else:
            status = rng.choices(["WON", "OPEN"], weights=[10, 90])[0]

        last_activity = created if status == "OPEN" else created + timedelta(days=rng.randint(1, max(1, days_open)))
        rows.append(
            {
                "QT_ID": f"QT-{20000 + i}",
                "ACCT_ID": cust[0],
                "MAT_NO": sku,
                "QTY": str(qty),
                "UNIT_PRC": f"{unit_prc:.2f}",
                "TOT_VAL": f"{qty * unit_prc:.2f}",
                "CURR": "USD",
                "QT_STATUS": status,
                "CRTD_DT": created.strftime("%Y-%m-%d"),
                "LAST_ACT_DT": last_activity.strftime("%Y-%m-%d"),
                "SLS_REP": rng.choice(SALES_REPS)[0],
                "VALID_UNTIL": (created + timedelta(days=30)).strftime("%Y-%m-%d"),
            }
        )
    return rows


def generate_purchase_history() -> list[dict[str, str]]:
    """CRM table: CRM_PURCH_HIST -- monthly purchase summaries per customer x product.

    Used to detect spending baselines and decline trends.
    """
    rows: list[dict[str, str]] = []
    for cust_id, _, _, tier in CUSTOMERS:
        # Each customer buys a subset of products
        n_products = {"Tier 1": 6, "Tier 2": 4, "Tier 3": 2}[tier]
        bought_products = rng.sample(PRODUCTS, n_products)
        for sku, _, _ in bought_products:
            baseline_qty = {"Tier 1": 200, "Tier 2": 80, "Tier 3": 30}[tier] * rng.uniform(0.6, 1.4)
            # Simulate a trend: some customers declining
            declining = rng.random() < 0.3
            for month_offset in range(12):
                month_start = YEAR_AGO + timedelta(days=30 * month_offset)
                month_label = month_start.strftime("%Y-%m")
                trend_factor = 1.0
                if declining:
                    trend_factor = max(0.1, 1.0 - (month_offset * 0.06))
                qty = max(0, int(baseline_qty * trend_factor * rng.uniform(0.7, 1.3)))
                unit_prc = rng.uniform(80, 1200)
                rows.append(
                    {
                        "ACCT_ID": cust_id,
                        "MAT_NO": sku,
                        "PERIOD": month_label,
                        "QTY": str(qty),
                        "NET_VAL": f"{qty * unit_prc:.2f}",
                        "CURR": "USD",
                    }
                )
    return rows


def generate_machine_catalog() -> list[dict[str, str]]:
    """ERP table: PM_EQUIPMASTER — equipment master data."""
    rows: list[dict[str, str]] = []
    for line, machines in MACHINES.items():
        for m in machines:
            install_year = rng.randint(2012, 2023)
            rows.append(
                {
                    "EQUIP_NO": m,
                    "WRKCTR_ID": line,
                    "EQUIP_DESC": m.replace("-", " ").title() + " Unit",
                    "INSTALL_DT": f"{install_year}-{rng.randint(1, 12):02d}-01",
                    "MFR": rng.choice(["Siemens", "Fanuc", "ABB", "Kuka", "DMG Mori"]),
                    "MODEL": f"M-{rng.randint(1000, 9999)}",
                    "STAT": "ACTV",
                }
            )
    return rows


# ---------------------------------------------------------------------------
# CSV writer helper
# ---------------------------------------------------------------------------


def write_csv(name: str, rows: list[dict[str, str]]) -> Path:
    """Write rows to a CSV file in the scratch directory."""
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    path = SCRATCH_DIR / f"{name}.csv"
    if not rows:
        return path
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d rows → %s", len(rows), path.name)
    return path


# ---------------------------------------------------------------------------
# Semantic views
# ---------------------------------------------------------------------------

VIEWS: dict[str, str] = {
    "downtime_events.sql": """\
-- description: One row per downtime event. Production line stoppages with reason, duration, machine, and shift.
CREATE OR REPLACE VIEW downtime_events AS
SELECT
    d.EVT_ID         AS event_id,
    d.WRKCTR_ID      AS line_id,
    d.EQUIP_NO       AS machine_id,
    e.EQUIP_DESC     AS machine_name,
    e.MFR            AS machine_manufacturer,
    CAST(d.DT_START AS TIMESTAMP) AS started_at,
    CAST(d.DT_END AS TIMESTAMP)   AS ended_at,
    CAST(d.DUR_MIN AS INTEGER)    AS duration_minutes,
    ROUND(CAST(d.DUR_MIN AS DOUBLE) / 60, 1) AS duration_hours,
    d.RSN_CD         AS reason_code,
    CASE d.RSN_CD
        WHEN 'MECH_FAIL'     THEN 'Mechanical failure'
        WHEN 'ELEC_FAIL'     THEN 'Electrical fault'
        WHEN 'TOOL_WEAR'     THEN 'Tool wear / breakage'
        WHEN 'MAINT_SCHED'   THEN 'Scheduled maintenance'
        WHEN 'MAINT_UNSCHED' THEN 'Unscheduled maintenance'
        WHEN 'MAT_SHORT'     THEN 'Material shortage'
        WHEN 'OPER_ERR'      THEN 'Operator error'
        WHEN 'QUAL_HOLD'     THEN 'Quality hold'
        WHEN 'CHANGEOVER'    THEN 'Product changeover'
        WHEN 'UTIL_OUTAGE'   THEN 'Utility outage (air/power/water)'
        ELSE d.RSN_CD
    END AS reason,
    CASE
        WHEN d.RSN_CD IN ('MAINT_SCHED', 'CHANGEOVER') THEN 'planned'
        ELSE 'unplanned'
    END AS downtime_type,
    d.SHIFT_CD        AS shift,
    d.RPRT_BY         AS reported_by
FROM _raw_PP_DWNTIME_LOG d
LEFT JOIN _raw_PM_EQUIPMASTER e ON d.EQUIP_NO = e.EQUIP_NO;
""",
    "production_orders.sql": """\
-- description: One row per production order. Work orders with product, yield, scrap rate, and schedule dates.
CREATE OR REPLACE VIEW production_orders AS
SELECT
    p.ORD_NO          AS order_id,
    p.MAT_NO          AS product_sku,
    m.MAT_DESC        AS product_name,
    m.MAT_GRP         AS product_group,
    p.WRKCTR_ID       AS line_id,
    CAST(p.PLANNED_QTY AS INTEGER) AS planned_qty,
    CAST(p.ACTUAL_QTY AS INTEGER)  AS actual_qty,
    CAST(p.SCRAP_QTY AS INTEGER)   AS scrap_qty,
    ROUND(CAST(p.SCRAP_QTY AS DOUBLE) / NULLIF(CAST(p.PLANNED_QTY AS DOUBLE), 0) * 100, 1) AS scrap_rate_pct,
    ROUND(CAST(p.ACTUAL_QTY AS DOUBLE) / NULLIF(CAST(p.PLANNED_QTY AS DOUBLE), 0) * 100, 1) AS yield_pct,
    CASE p.ORD_STATUS
        WHEN 'COMP' THEN 'Completed'
        WHEN 'WIP'  THEN 'In Progress'
        WHEN 'HOLD' THEN 'On Hold'
        ELSE p.ORD_STATUS
    END AS status,
    CAST(p.SCHED_START AS DATE) AS scheduled_start,
    CAST(p.SCHED_END AS DATE)   AS scheduled_end,
    CAST(p.ACT_START AS DATE)   AS actual_start,
    CASE WHEN p.ACT_END = '' THEN NULL ELSE CAST(p.ACT_END AS DATE) END AS actual_end
FROM _raw_PP_PRODORD p
LEFT JOIN _raw_MM_MATMASTER m ON p.MAT_NO = m.MAT_NO;
""",
    "products.sql": """\
-- description: One row per product. Catalog with SKU, product group, standard cost, and list price.
CREATE OR REPLACE VIEW products AS
SELECT
    MAT_NO       AS sku,
    MAT_DESC     AS name,
    MAT_GRP      AS product_group,
    CAST(STD_COST AS DOUBLE) AS standard_cost,
    CAST(LIST_PRC AS DOUBLE) AS list_price,
    CAST(WEIGHT_KG AS DOUBLE) AS weight_kg
FROM _raw_MM_MATMASTER;
""",
    "customers.sql": """\
-- description: One row per customer. Active accounts with tier, state, and assigned sales rep.
CREATE OR REPLACE VIEW customers AS
SELECT
    a.ACCT_ID    AS customer_id,
    a.ACCT_NM    AS customer_name,
    a.ST_CD      AS state,
    a.TIER_CD    AS tier,
    CAST(a.CRTD_DT AS DATE) AS customer_since,
    a.OWN_REP    AS sales_rep_id
FROM _raw_CRM_ACCT a
WHERE a.STAT_CD = 'A';
""",
    "sales_orders.sql": """\
-- description: One row per sales order. Orders with customer, product, value, and delivery status.
CREATE OR REPLACE VIEW sales_orders AS
SELECT
    s.SO_NO       AS order_id,
    s.ACCT_ID     AS customer_id,
    a.ACCT_NM     AS customer_name,
    a.TIER_CD     AS customer_tier,
    s.MAT_NO      AS product_sku,
    m.MAT_DESC    AS product_name,
    m.MAT_GRP     AS product_group,
    CAST(s.ORD_DT AS DATE)  AS order_date,
    CAST(s.REQ_DT AS DATE)  AS requested_delivery_date,
    CAST(s.QTY AS INTEGER)  AS quantity,
    CAST(s.UNIT_PRC AS DOUBLE) AS unit_price,
    CAST(s.NET_VAL AS DOUBLE)  AS total_value,
    CASE s.SO_STATUS
        WHEN 'DLVD' THEN 'Delivered'
        WHEN 'OPEN' THEN 'Open'
        WHEN 'PRTL' THEN 'Partially Delivered'
        ELSE s.SO_STATUS
    END AS status,
    s.SLS_REP     AS sales_rep_id
FROM _raw_SD_SALESORD s
LEFT JOIN _raw_CRM_ACCT a ON s.ACCT_ID = a.ACCT_ID
LEFT JOIN _raw_MM_MATMASTER m ON s.MAT_NO = m.MAT_NO;
""",
    "quotes.sql": """\
-- description: One row per quote. Sales proposals with value, status, and days since last activity.
CREATE OR REPLACE VIEW quotes AS
SELECT
    q.QT_ID       AS quote_id,
    q.ACCT_ID     AS customer_id,
    a.ACCT_NM     AS customer_name,
    a.TIER_CD     AS customer_tier,
    q.MAT_NO      AS product_sku,
    m.MAT_DESC    AS product_name,
    CAST(q.QTY AS INTEGER)     AS quantity,
    CAST(q.UNIT_PRC AS DOUBLE) AS unit_price,
    CAST(q.TOT_VAL AS DOUBLE)  AS total_value,
    CASE q.QT_STATUS
        WHEN 'WON'     THEN 'Won'
        WHEN 'LOST'    THEN 'Lost'
        WHEN 'OPEN'    THEN 'Open'
        WHEN 'EXPIRED' THEN 'Expired'
        ELSE q.QT_STATUS
    END AS status,
    CAST(q.CRTD_DT AS DATE)     AS created_date,
    CAST(q.LAST_ACT_DT AS DATE) AS last_activity_date,
    CAST(q.VALID_UNTIL AS DATE)  AS valid_until,
    CURRENT_DATE - CAST(q.CRTD_DT AS DATE)     AS days_since_created,
    CURRENT_DATE - CAST(q.LAST_ACT_DT AS DATE) AS days_since_activity,
    q.SLS_REP     AS sales_rep_id
FROM _raw_CRM_QUOTES q
LEFT JOIN _raw_CRM_ACCT a ON q.ACCT_ID = a.ACCT_ID
LEFT JOIN _raw_MM_MATMASTER m ON q.MAT_NO = m.MAT_NO;
""",
    "customer_purchase_trends.sql": """\
-- description: One row per customer per product per month. Purchase history for baseline comparisons and churn detection.
CREATE OR REPLACE VIEW customer_purchase_trends AS
SELECT
    h.ACCT_ID     AS customer_id,
    a.ACCT_NM     AS customer_name,
    a.TIER_CD     AS customer_tier,
    h.MAT_NO      AS product_sku,
    m.MAT_DESC    AS product_name,
    h.PERIOD      AS month,
    CAST(h.QTY AS INTEGER)     AS quantity,
    CAST(h.NET_VAL AS DOUBLE)  AS revenue
FROM _raw_CRM_PURCH_HIST h
LEFT JOIN _raw_CRM_ACCT a ON h.ACCT_ID = a.ACCT_ID
LEFT JOIN _raw_MM_MATMASTER m ON h.MAT_NO = m.MAT_NO;
""",
    "machines.sql": """\
-- description: One row per machine. Equipment catalog with manufacturer, model, install date, and line assignment.
CREATE OR REPLACE VIEW machines AS
SELECT
    EQUIP_NO     AS machine_id,
    WRKCTR_ID    AS line_id,
    EQUIP_DESC   AS name,
    CAST(INSTALL_DT AS DATE) AS installed_date,
    MFR          AS manufacturer,
    MODEL        AS model
FROM _raw_PM_EQUIPMASTER;
""",
}

# ---------------------------------------------------------------------------
# Task outputs for the generate-signals task
# ---------------------------------------------------------------------------

# Per-toolbox prompts shape what the LLM generates so demo signals reference the
# seeded manufacturing dataset instead of random topics. The task itself always
# returns 3 signals — that's defined by the task's own instructions.
_SEED_PROMPTS: dict[Toolbox, str] = {
    Toolbox.PRODUCTION: (
        "Generate 3 diverse actionable signals for a plant operations team. "
        "Cover downtime, quality/scrap, and maintenance. Reference specific "
        "machine or line IDs where plausible."
    ),
    Toolbox.SALES: (
        "Generate 3 diverse actionable signals for a B2B industrial sales team. "
        "Cover customer churn risk, stalled quotes, and pipeline gaps. Reference "
        "specific customer or rep names where plausible."
    ),
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def seed_tables() -> None:
    """Generate CSVs and ingest into Delta Lake tables. Skips tables that already exist.

    Schemas are created by ``scripts/apply_delta_migrations.py`` (which the caller
    runs first); ingestion validates the batch against the migrated schema.
    """
    table_defs: list[tuple[str, Callable[[], list[dict[str, str]]]]] = [
        ("PP_DWNTIME_LOG", generate_downtime_events),
        ("PP_PRODORD", generate_production_orders),
        ("MM_MATMASTER", generate_products),
        ("PM_EQUIPMASTER", generate_machine_catalog),
        ("CRM_ACCT", generate_customers),
        ("SD_SALESORD", generate_sales_orders),
        ("CRM_QUOTES", generate_quotes),
        ("CRM_PURCH_HIST", generate_purchase_history),
    ]

    config = DatasetStorageConfig(datasets_uri=str(DATASETS_DIR), local_cache_dir=DATASETS_DIR)
    ingestion = DeltaIngestionService(storage_config=config)

    for table_name, generator in table_defs:
        table_path = DATASETS_DIR / table_name
        # The migration runner already created the empty Delta table. Skip if it
        # has data from a prior seed.
        if table_path.exists() and any(p.suffix == ".parquet" for p in table_path.iterdir()):
            logger.info("Skipping %s — already populated", table_name)
            continue

        rows = generator()
        csv_path = write_csv(table_name, rows)
        result = ingestion.ingest(csv_path, table_name)
        logger.info("Ingested %s → %d rows (v%d)", result.table_name, result.row_count, result.delta_version)


def seed_views() -> None:
    """Write semantic SQL view files. Skips files that already exist."""
    VIEWS_DIR.mkdir(parents=True, exist_ok=True)
    skipped = 0
    for filename, sql in VIEWS.items():
        path = VIEWS_DIR / filename
        if path.exists():
            skipped += 1
            continue
        path.write_text(sql, encoding="utf-8")
        logger.info("Wrote view → %s", path.name)
    if skipped:
        logger.info("Skipped %d view files that already exist", skipped)


async def seed_generate_signals_outputs() -> None:
    """Run generate-signals for each toolbox so seeded signals match real output.

    Uses the same code path as the production task — no divergent schema or
    fixture data to maintain per customer fork. Skips per-toolbox if outputs
    already exist so re-runs don't hammer the LLM.
    """
    engine = _get_async_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def repo_factory() -> AsyncIterator[TaskOutputRepositoryInterface]:
        async with session_factory() as session:
            yield TaskOutputRepository(session)

    try:
        for toolbox, prompt in _SEED_PROMPTS.items():
            async with engine.begin() as conn:
                result = await conn.execute(
                    sa.text("SELECT COUNT(*) FROM task_outputs WHERE task_name = :task_name AND toolbox = :toolbox"),
                    {"task_name": GENERATE_SIGNALS_TASK, "toolbox": toolbox.value},
                )
                count = result.scalar() or 0
            if count > 0:
                logger.info("Skipping %s signals — %d rows already exist", toolbox.value, count)
                continue

            logger.info("Generating signals for toolbox=%s via LLM...", toolbox.value)
            await generate_signals(repo_factory=repo_factory, prompt=prompt, toolbox=toolbox.value)
    finally:
        await engine.dispose()


def _apply_delta_migrations() -> None:
    """Re-run Delta schema migrations to recreate the empty tables `clean()` wiped.

    `scripts/` is not a Python package, so we can't `import` it; load by path.
    """
    path = ROOT / "scripts" / "apply_delta_migrations.py"
    spec = importlib.util.spec_from_file_location("_apply_delta_migrations", path)
    if spec is None or spec.loader is None:
        msg = f"Cannot load migration runner: {path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rc = module.main()
    if rc != 0:
        msg = f"Delta migrations failed (exit code {rc})"
        raise RuntimeError(msg)


async def clean() -> None:
    """Remove existing seed data, then re-apply Delta migrations.

    Wiping ``DATASETS_DIR`` also deletes the empty Delta tables created by the
    migration runner. ``seed_tables()`` requires those tables to exist, so we
    re-run migrations here to leave the on-disk state ready for seeding.
    """
    for path in [DATASETS_DIR, SCRATCH_DIR]:
        if path.exists():
            shutil.rmtree(path)
            logger.info("Removed %s", path)

    try:
        engine = _get_async_engine()
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("DELETE FROM task_outputs WHERE task_name = :task_name"),
                {"task_name": GENERATE_SIGNALS_TASK},
            )
        await engine.dispose()
        logger.info("Cleared seed task outputs from database")
    except Exception:
        logger.warning("Could not connect to database to clear task outputs (may not be running)")

    logger.info("Re-applying Delta migrations after clean...")
    _apply_delta_migrations()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Seed manufacturing data for development.")
    parser.add_argument("--clean", action="store_true", help="Remove existing data before seeding")
    args = parser.parse_args()

    if args.clean:
        await clean()

    logger.info("Seeding Delta Lake tables...")
    seed_tables()

    logger.info("Writing semantic views...")
    seed_views()

    logger.info("Seeding task outputs...")
    await seed_generate_signals_outputs()

    # Clean up scratch CSVs
    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR)

    logger.info("Done! Run the backend to see data in action.")


if __name__ == "__main__":
    asyncio.run(main())
