import io
import os
import re

import pandas as pd
import psycopg2
from psycopg2 import sql

# -----------------------------
# Configuration
# -----------------------------
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "usfund"
DB_USER = "postgres"
DB_PASSWORD = "Indium@123"

SCHEMA_NAME = "usfund"

CSV_FOLDER = r"C:\Users\SaseendranS\Downloads\US_Fund"
DICTIONARY_CSV = os.path.join(CSV_FOLDER,"C:/Users/SaseendranS/Downloads/Aurum_US_Funds_All_451_Columns.csv")
CHUNK_SIZE = 100_000

# True  -> drop and recreate every target table at the start of the run,
#          so re-running never duplicates rows.
# False -> create only if missing and append (re-running will duplicate rows).
RECREATE_TABLES = True

PG_TYPES = {"TEXT", "NUMERIC", "BIGINT", "DATE"}
INT_PATTERN = re.compile(r"^[+-]?\d+(\.0+)?$")


# -----------------------------
# Data dictionary
# -----------------------------
def normalize(name):
    return re.sub(r"\s+", "_", str(name).strip().lower())


def load_dictionary(path):
    dd = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    dd["data_type"] = dd["data_type"].str.strip().str.upper()
    dd["column_name"] = dd["column_name"].map(normalize)
    dd["column_number"] = dd["column_number"].astype(int)

    bad = set(dd["data_type"]) - PG_TYPES
    if bad:
        raise ValueError(f"Unsupported data types in dictionary: {sorted(bad)}")
    dup = dd[dd.duplicated(["logical_table", "column_name"], keep=False)]
    if not dup.empty:
        raise ValueError(f"Duplicate columns in dictionary:\n{dup}")

    dd = dd.sort_values(["logical_table", "column_number"])
    schema = {
        table: dict(zip(g["column_name"], g["data_type"]))
        for table, g in dd.groupby("logical_table", sort=False)
    }

    # physical_files is either one file name, or a "A.csv-Z.csv (26 partitions)" range.
    exact, partition_table = {}, None
    for table, files in dd.groupby("logical_table").physical_files.first().items():
        if "partition" in files.lower():
            partition_table = table
        else:
            exact[files.strip().lower()] = table
    return schema, exact, partition_table


def resolve_table(filename, exact, partition_table):
    key = filename.lower()
    if key in exact:
        return exact[key]
    # partition files: "A.csv", or "<anything> - A.csv" such as "MutualFund prices - A.csv"
    if partition_table and re.fullmatch(r"(.+\s-\s)?[a-z]\.csv", key):
        return partition_table
    return None


def partition_letter(filename, partition_table):
    if not partition_table:
        return None
    match = re.fullmatch(r"(?:.+\s-\s)?([a-z])\.csv", filename.lower())
    return match.group(1) if match else None


# -----------------------------
# Type-aware cleaning
# -----------------------------
def clean_series(s, pg_type):
    """Return (cleaned series, number of non-empty values replaced with NULL)."""
    s = s.astype("string").str.strip()
    s = s.mask(s == "")
    present = s.notna()

    if pg_type == "TEXT":
        return s.astype(object), 0

    if pg_type == "BIGINT":
        ok = s.str.match(INT_PATTERN).fillna(False)
        out = s.where(ok).str.replace(r"\.0+$", "", regex=True)
        out = out.str.replace(r"^\+", "", regex=True)

    elif pg_type == "NUMERIC":
        parsed = pd.to_numeric(s, errors="coerce")
        ok = parsed.notna() & ~parsed.isin([float("inf"), float("-inf")])
        out = s.where(ok)  # keep the original text so no precision is lost

    elif pg_type == "DATE":
        try:
            parsed = pd.to_datetime(s, errors="coerce", format="mixed")
        except (TypeError, ValueError):  # pandas < 2.0
            parsed = pd.to_datetime(s, errors="coerce")
        out = parsed.dt.strftime("%Y-%m-%d")
        ok = parsed.notna()

    return out.astype(object), int((present & ~ok).sum())


# -----------------------------
# DDL
# -----------------------------
def create_table(cursor, table, columns):
    cursor.execute(
        sql.SQL("CREATE TABLE IF NOT EXISTS {}.{} ({})").format(
            sql.Identifier(SCHEMA_NAME),
            sql.Identifier(table),
            sql.SQL(", ").join(
                sql.SQL("{} {}").format(sql.Identifier(col), sql.SQL(pg_type))
                for col, pg_type in columns.items()
            ),
        )
    )


def load_file(conn, cursor, file_path, table, columns):
    header = pd.read_csv(file_path, nrows=0, dtype=str, encoding="utf-8-sig").columns
    file_cols = [normalize(c) for c in header]

    unknown = [c for c in file_cols if c not in columns]
    if unknown:
        raise ValueError(f"columns not in dictionary for '{table}': {unknown}")
    missing = [c for c in columns if c not in file_cols]
    if missing:
        print(f"  WARNING: {len(missing)} dictionary column(s) absent from file "
              f"(left NULL): {missing[:5]}{' ...' if len(missing) > 5 else ''}")

    copy_query = sql.SQL(
        "COPY {}.{} ({}) FROM STDIN WITH (FORMAT CSV, NULL '')"
    ).format(
        sql.Identifier(SCHEMA_NAME),
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in file_cols),
    ).as_string(conn)

    row_count = 0
    nulled = {}
    for chunk in pd.read_csv(
        file_path,
        chunksize=CHUNK_SIZE,
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,  # "NA" / "N/A" stay as text until type-checked
        na_values=[""],
    ):
        chunk.columns = file_cols
        for col in file_cols:
            chunk[col], bad = clean_series(chunk[col], columns[col])
            if bad:
                nulled[col] = nulled.get(col, 0) + bad

        buffer = io.StringIO()
        chunk.to_csv(buffer, index=False, header=False, na_rep="")
        buffer.seek(0)
        cursor.copy_expert(copy_query, buffer)
        row_count += len(chunk)

    return row_count, nulled


# -----------------------------
# Main
# -----------------------------
schema, exact_files, partition_table = load_dictionary(DICTIONARY_CSV)
dictionary_path = os.path.abspath(DICTIONARY_CSV)

conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
)

try:
    with conn.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(SCHEMA_NAME))
        )
        if RECREATE_TABLES and partition_table:
            cursor.execute(
                sql.SQL("DROP TABLE IF EXISTS {}.{}").format(
                    sql.Identifier(SCHEMA_NAME),
                    sql.Identifier(partition_table),
                )
            )
        target_tables = {}
        for table, columns in schema.items():
            names = (
                [f"{table}_{letter}" for letter in "abcdefghijklmnopqrstuvwxyz"]
                if table == partition_table
                else [table]
            )
            for target_table in names:
                target_tables[target_table] = columns
                if RECREATE_TABLES:
                    cursor.execute(
                        sql.SQL("DROP TABLE IF EXISTS {}.{}").format(
                            sql.Identifier(SCHEMA_NAME),
                            sql.Identifier(target_table),
                        )
                    )
                create_table(cursor, target_table, columns)
        conn.commit()
        print(f"Tables ready: {', '.join(target_tables)}")

        totals = {table: 0 for table in target_tables}
        for filename in sorted(os.listdir(CSV_FOLDER)):
            file_path = os.path.join(CSV_FOLDER, filename)
            if not filename.lower().endswith(".csv") or os.path.abspath(file_path) == dictionary_path:
                continue

            logical_table = resolve_table(filename, exact_files, partition_table)
            if logical_table is None:
                print(f"Skipping {filename}: no matching table in the dictionary")
                continue

            letter = (
                partition_letter(filename, partition_table)
                if logical_table == partition_table else None
            )
            target_table = f"{logical_table}_{letter}" if letter else logical_table
            if target_table not in target_tables:
                print(f"Skipping {filename}: no target table found for {logical_table}")
                continue

            print(f"Loading: {filename} -> {SCHEMA_NAME}.{target_table}")
            try:
                rows, nulled = load_file(
                    conn, cursor, file_path, target_table, target_tables[target_table]
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"  FAILED, file rolled back: {exc}")
                continue

            totals[target_table] += rows
            print(f"  {rows} rows")
            for col, n in nulled.items():
                print(
                    f"  {col}: {n} value(s) not valid "
                    f"{target_tables[target_table][col]}, loaded as NULL"
                )

    print("\nRows loaded per table:")
    for table, n in totals.items():
        print(f"  {table}: {n}")
finally:
    conn.close()