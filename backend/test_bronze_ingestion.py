import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd

from app.services import bronze_service
from app.services.bronze_service import (
    _coerce_numeric_columns,
    _csv_typed_columns,
    _dictionary_table_types,
    _source_pg_type,
)
from app.services.dq_calculation import calculate_data_quality


class _AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        _ = exc_type, exc, traceback
        return False


class _FakeCursor:
    def __init__(self, records):
        self.records = records
        self.fetched = False

    async def fetch(self, batch_size, timeout=None):
        _ = batch_size, timeout
        if self.fetched:
            return []
        self.fetched = True
        return self.records


class BronzeTypeResolutionTests(unittest.TestCase):
    def test_source_types_keep_numeric_modifiers_and_character_length(self):
        self.assertEqual(
            _source_pg_type({
                "data_type": "numeric",
                "numeric_precision": 12,
                "numeric_scale": 3,
                "character_maximum_length": None,
                "datetime_precision": None,
                "column_name": "amount",
            }),
            "NUMERIC(12,3)",
        )
        self.assertEqual(
            _source_pg_type({
                "data_type": "character varying",
                "numeric_precision": None,
                "numeric_scale": None,
                "character_maximum_length": 80,
                "datetime_precision": None,
                "column_name": "label",
            }),
            "VARCHAR(80)",
        )
        self.assertEqual(
            _source_pg_type({
                "data_type": "timestamp with time zone",
                "numeric_precision": None,
                "numeric_scale": None,
                "character_maximum_length": None,
                "datetime_precision": 3,
                "column_name": "updated_at",
            }),
            "TIMESTAMP(3) WITH TIME ZONE",
        )

    def test_dictionary_matches_logical_table_or_source_filename(self):
        rows = [
            {
                "logical_table": "etfs",
                "physical_files": "ETF_Master.csv",
                "column_name": "fund_name",
                "data_type": "TEXT",
            },
            {
                "logical_table": "etfs",
                "physical_files": "ETF_Master.csv",
                "column_name": "assets",
                "data_type": "NUMERIC",
            },
        ]

        self.assertEqual(
            _dictionary_table_types(rows, "etfs"),
            {"fund_name": "TEXT", "assets": "NUMERIC"},
        )
        self.assertEqual(
            _dictionary_table_types(rows, "uploaded_file", "ETF_Master.csv"),
            {"fund_name": "TEXT", "assets": "NUMERIC"},
        )
        self.assertEqual(_dictionary_table_types(rows, "unmatched"), {})

    def test_csv_dictionary_types_convert_to_native_values(self):
        inferred = pd.DataFrame({
            "assets": ["10.25", "2.50"],
            "date_added": ["2024-01-02", "2024-02-03"],
        })
        raw = inferred.copy()

        schema, columns = _csv_typed_columns(
            inferred,
            raw,
            {"assets": "NUMERIC", "date_added": "DATE"},
            "bronze.etfs_bronze",
        )

        self.assertEqual([column["type"] for column in schema], ["NUMERIC", "DATE"])
        self.assertEqual(columns[0], [Decimal("10.25"), Decimal("2.50")])
        self.assertEqual(columns[1][0].isoformat(), "2024-01-02")

    def test_numeric_database_values_keep_numeric_dtype_without_negative_issue(self):
        frame = pd.DataFrame({"amount": [Decimal("1")] * 20 + [Decimal("-1")]})

        converted = _coerce_numeric_columns(frame, {"amount"})
        result = calculate_data_quality(converted, "bronze_amounts")

        self.assertTrue(pd.api.types.is_numeric_dtype(converted["amount"].dtype))
        self.assertFalse(any(
            check["check_name"] == "Negative values"
            for check in result["checks"]
        ))

    def test_invalid_dictionary_typed_csv_reports_table_column_and_sample(self):
        inferred = pd.DataFrame({"assets": ["10.25", "bad", "also-bad"]})

        with self.assertRaisesRegex(
            ValueError,
            r"table bronze\.etfs_bronze, column 'assets' \(NUMERIC\).*bad.*also-bad",
        ):
            _csv_typed_columns(
                inferred,
                inferred,
                {"assets": "NUMERIC"},
                "bronze.etfs_bronze",
            )


class BronzeCsvIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_dictionary_typed_csv_fails_before_replacing_a_table(self):
        source_connection = AsyncMock()
        dictionary_rows = [
            {
                "logical_table": "etfs",
                "physical_files": "etfs.csv",
                "column_number": 1,
                "column_name": "assets",
                "data_type": "NUMERIC",
            },
        ]
        with (
            patch.object(
                bronze_service, "_user_conn",
                new=AsyncMock(return_value=source_connection),
            ),
            patch.object(
                bronze_service, "_source_dictionary_rows",
                new=AsyncMock(return_value=dictionary_rows),
            ),
            patch.object(bronze_service, "_aurum_conn") as aurum_conn,
        ):
            with self.assertRaisesRegex(
                ValueError,
                r"table bronze\.etfs_bronze, column 'assets' \(NUMERIC\).*bad-value",
            ):
                await bronze_service.ingest_csv(
                    file_bytes=b"assets\n10.25\nbad-value\n",
                    dataset_name="etfs",
                    dictionary_connection={"database": "source"},
                    source_filename="etfs.csv",
                )

        aurum_conn.assert_not_awaited()
        source_connection.close.assert_awaited_once()


class BronzePostgresIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_values_are_copied_in_batches_without_stringifying(self):
        source_connection = AsyncMock()
        source_connection.transaction = Mock(return_value=_AsyncContext())
        values = [
            {
                "amount": Decimal("1.25"),
                "fund_id": 42,
                "as_of_date": date(2024, 1, 2),
            },
            {
                "amount": Decimal("2.50"),
                "fund_id": 43,
                "as_of_date": date(2024, 1, 3),
            },
        ]
        source_connection.cursor = AsyncMock(
            return_value=_FakeCursor(values)
        )
        source_connection.fetchval = AsyncMock(side_effect=[False, 2])
        source_connection.fetch = AsyncMock(return_value=[
            {
                "column_name": "amount",
                "data_type": "numeric",
                "is_nullable": "YES",
                "character_maximum_length": None,
                "numeric_precision": 12,
                "numeric_scale": 2,
                "datetime_precision": None,
                "udt_name": "numeric",
            },
            {
                "column_name": "fund_id",
                "data_type": "bigint",
                "is_nullable": "NO",
                "character_maximum_length": None,
                "numeric_precision": 64,
                "numeric_scale": 0,
                "datetime_precision": None,
                "udt_name": "int8",
            },
            {
                "column_name": "as_of_date",
                "data_type": "date",
                "is_nullable": "YES",
                "character_maximum_length": None,
                "numeric_precision": None,
                "numeric_scale": None,
                "datetime_precision": None,
                "udt_name": "date",
            },
        ])

        aurum_connection = AsyncMock()
        aurum_connection.transaction = Mock(return_value=_AsyncContext())
        copied_records = []

        async def copy_records_to_table(table, records, **kwargs):
            _ = table, kwargs
            copied_records.extend(list(records))

        aurum_connection.copy_records_to_table = AsyncMock(
            side_effect=copy_records_to_table
        )
        with (
            patch.object(
                bronze_service, "_user_conn",
                new=AsyncMock(return_value=source_connection),
            ),
            patch.object(
                bronze_service, "_aurum_conn",
                new=AsyncMock(return_value=aurum_connection),
            ),
        ):
            result = await bronze_service.ingest_postgres(
                {"schema": "usfund"}, ["etf_prices"]
            )

        self.assertEqual(result[0]["row_count"], 2)
        self.assertEqual(
            [column["type"] for column in result[0]["schema_cols"]],
            ["NUMERIC(12,2)", "BIGINT", "DATE"],
        )
        self.assertEqual(copied_records, [
            (Decimal("1.25"), 42, date(2024, 1, 2)),
            (Decimal("2.50"), 43, date(2024, 1, 3)),
        ])
        source_connection.close.assert_awaited_once()
        aurum_connection.close.assert_awaited_once()


class BronzeDictionaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_dictionary_response_includes_expected_actual_and_match_status(self):
        source_connection = AsyncMock()
        dictionary_rows = [
            {
                "logical_table": "etfs",
                "physical_files": "etfs.csv",
                "column_number": index + 1,
                "column_name": f"column_{index}",
                "data_type": "NUMERIC",
            }
            for index in range(142)
        ] + [
            {
                "logical_table": "mutual_funds",
                "physical_files": "mutual_funds.csv",
                "column_number": index + 1,
                "column_name": f"column_{index}",
                "data_type": "TEXT",
            }
            for index in range(298)
        ] + [
            {
                "logical_table": "etf_prices",
                "physical_files": "etf_prices.csv",
                "column_number": index + 1,
                "column_name": f"column_{index}",
                "data_type": "DATE",
            }
            for index in range(8)
        ] + [
            {
                "logical_table": "mutual_fund_prices",
                "physical_files": "mutual_fund_prices.csv",
                "column_number": index + 1,
                "column_name": f"column_{index}",
                "data_type": "BIGINT",
            }
            for index in range(3)
        ]
        view_rows = [
            {
                "logical_table": row["logical_table"],
                "column_name": row["column_name"],
                "expected_type": row["data_type"],
                "actual_type": row["data_type"].lower(),
                "matches": True,
            }
            for row in dictionary_rows
        ]
        actual_rows = [
            {
                "table_name": row["logical_table"],
                "column_name": row["column_name"],
                "data_type": row["data_type"].lower(),
            }
            for row in dictionary_rows
        ]
        source_connection.fetchval.side_effect = [True, True]
        source_connection.fetch.side_effect = [
            dictionary_rows, view_rows, actual_rows,
        ]

        with patch.object(
            bronze_service, "_user_conn",
            new=AsyncMock(return_value=source_connection),
        ):
            response = await bronze_service.get_data_dictionary(
                {"database": "source", "schema": "usfund"}
            )

        self.assertEqual(response["row_count"], 451)
        self.assertFalse(response["fallback_used"])
        self.assertEqual(response["rows"][0]["expected_type"], "NUMERIC")
        self.assertEqual(response["rows"][0]["actual_type"], "numeric")
        self.assertTrue(response["rows"][0]["matches"])
        source_connection.close.assert_awaited_once()

    async def test_missing_dictionary_returns_information_schema_fallback(self):
        source_connection = AsyncMock()
        source_connection.fetchval.return_value = False
        source_connection.fetch.return_value = [
            {
                "table_name": "sample",
                "column_number": 1,
                "column_name": "amount",
                "data_type": "numeric",
            }
        ]
        with patch.object(
            bronze_service, "_user_conn",
            new=AsyncMock(return_value=source_connection),
        ):
            response = await bronze_service.get_data_dictionary(
                {"database": "source", "schema": "public"}
            )

        self.assertTrue(response["fallback_used"])
        self.assertEqual(response["row_count"], 1)
        self.assertEqual(response["rows"][0]["expected_type"], "numeric")
        self.assertIn("information_schema.columns", response["message"])
        source_connection.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
