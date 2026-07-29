"""
AURUM Table Naming Convention
==============================
Given uploaded_filename = "customer_orders.csv":

  base_name  = "customer_orders"          (stem, lowercased, safe chars only)

  bronze.*   = bronze."customer_orders_bronze"
  silver.*   = silver."customer_orders_silver"
  gold.*     = gold."customer_orders_gold_{kpi_slug}"

For PostgreSQL source tables:
  source table "sales" in schema "public"
  base_name = "sales"
  bronze.*  = bronze."sales_bronze"
  silver.*  = silver."sales_silver"
  gold.*    = gold."sales_gold_{kpi_slug}"
"""
import re
from pathlib import Path


def make_base_name(raw: str) -> str:
    """
    Convert any string (filename, table name, dataset name) to a safe base_name.
    Strips extension, lowercases, replaces non-alphanumeric with underscore,
    collapses repeated underscores, strips leading/trailing underscores.
    """
    stem = Path(raw).stem if "." in raw else raw
    safe = re.sub(r"[^a-z0-9]", "_", stem.lower())
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "dataset"


def bronze_table(base_name: str) -> str:
    return f"{base_name}_bronze"


def silver_table(base_name: str) -> str:
    return f"{base_name}_silver"


def gold_table(base_name: str, kpi_name: str) -> str:
    kpi_slug = re.sub(r"[^a-z0-9]", "_", kpi_name.lower())
    kpi_slug = re.sub(r"_+", "_", kpi_slug).strip("_")
    return f"{base_name}_gold_{kpi_slug}"


def base_name_from_bronze(bronze_tbl: str) -> str:
    """
    Extract base_name from a bronze table name.
    "customer_orders_bronze"  →  "customer_orders"
    "bronze.customer_orders_bronze"  →  "customer_orders"
    """
    bare = bronze_tbl.split(".")[-1]   # strip schema prefix
    if bare.endswith("_bronze"):
        return bare[: -len("_bronze")]
    return bare
