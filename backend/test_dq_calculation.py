import unittest
import warnings
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pandas as pd

from app.services import bronze_service
from app.services.dq_calculation import (
    DataQualityAccumulator,
    _date_series,
    calculate_data_quality,
    check_severity,
    dimension_statuses,
)


class DataQualityCalculationTests(unittest.TestCase):
    def test_severity_uses_rate_tiers_and_bumps_ri_and_uniqueness(self):
        self.assertEqual(check_severity("Completeness", 50), "Critical")
        self.assertEqual(check_severity("Completeness", 20), "High")
        self.assertEqual(check_severity("Completeness", 5), "Medium")
        self.assertEqual(check_severity("Completeness", 4.99), "Low")
        self.assertEqual(check_severity("Full-row duplicates", 5), "High")
        self.assertEqual(check_severity("Referential integrity", 20), "Critical")
        self.assertEqual(check_severity("Full-row duplicates", 0, passed=True), "Low")

    def test_dimension_statuses_cover_checks_and_use_na_when_absent(self):
        checks = [
            {"check_name": "Completeness", "passed": True},
            {"check_name": "Full-row duplicates", "passed": False},
            {"check_name": "Referential integrity", "passed": False},
        ]

        statuses = dimension_statuses(checks)

        self.assertEqual(statuses, {
            "Completeness": "Pass",
            "Uniqueness": "Fail",
            "Validity": "N/A",
            "Referential Integrity": "Fail",
            "Schema Integrity": "N/A",
        })

    def test_unmapped_check_warns_and_falls_back_to_validity(self):
        with self.assertLogs("aurum.dq", level="WARNING"):
            self.assertEqual(
                dimension_statuses([{"check_name": "Future check", "passed": True}])["Validity"],
                "Pass",
            )

    def test_completeness_and_no_column_business_uniqueness_check(self):
        data = pd.DataFrame({
            "email": ["not-an-email", "  ", None, "ok"] + ["ok"] * 17,
            "key_candidate": [f"k{index}" for index in range(20)] + ["k0"],
        })
        result = calculate_data_quality(data, "orders_bronze")
        completeness = next(check for check in result["checks"] if check["check_name"] == "Completeness")
        self.assertEqual((completeness["bad_records"], completeness["bad_pct"]), (2, round(2 / 21 * 100, 2)))
        self.assertEqual(
            set(completeness["failed_rows"][0]["values"]),
            {"email", "key_candidate"},
        )
        self.assertEqual(completeness["failed_rows"][0]["values"]["email"], "  ")
        self.assertFalse(any(check["check_name"] == "Business-key uniqueness" for check in result["checks"]))
        self.assertFalse(any("email" in check["check_name"].lower() for check in result["checks"]))
        self.assertTrue(all(check["semantic_type"] is None for check in result["checks"]))

    def test_validity_flags_malformed_numeric_text_but_not_negative_numbers(self):
        data = pd.DataFrame({
            "metric": [-5] + [2] * 20,
            "numeric_text": ["1", "2", "bad", "4"] + ["5"] * 17,
        })
        result = calculate_data_quality(data, "metrics_bronze")
        check_names = [(check["column_name"], check["check_name"]) for check in result["checks"]]

        self.assertNotIn(("metric", "Negative values"), check_names)
        self.assertFalse(any(name == "IQR outliers" for _, name in check_names))
        consistency = next(check for check in result["checks"] if check["check_name"] == "Numeric type consistency")
        self.assertEqual((consistency["bad_records"], consistency["total_checked"]), (1, 21))

    def test_negative_numeric_values_do_not_create_an_issue_in_streaming_report(self):
        data = pd.DataFrame({"metric": [-5] + [2] * 20})
        accumulator = DataQualityAccumulator("metrics_bronze", list(data.columns))
        accumulator.update(data.iloc[:10])
        accumulator.update(data.iloc[10:])

        result = accumulator.finish()

        self.assertFalse(any(
            check["check_name"] == "Negative values"
            for check in result["checks"]
        ))
        self.assertFalse(any(
            check["check_name"] == "Negative values"
            for check in result["issues"]
        ))

    def test_full_row_duplicates_and_date_format_only_check(self):
        data = pd.DataFrame({"event": ["1899-01-01", "not-a-date", "1899-01-01"]})
        result = calculate_data_quality(data, "events_bronze")
        full_row = next(check for check in result["checks"] if check["check_name"] == "Full-row duplicates")
        parse_check = next(check for check in result["checks"] if check["check_name"] == "Date format validity")

        self.assertEqual(full_row["bad_records"], 1)
        self.assertEqual(parse_check["bad_records"], 1)
        self.assertFalse(any(check["check_name"] == "Logical date range" for check in result["checks"]))

    def test_failed_row_details_are_sampled_but_failure_count_is_exact(self):
        result = calculate_data_quality(
            pd.DataFrame({"value": [None] * 150, "other": list(range(150))}),
            "missing_bronze",
        )
        completeness = next(check for check in result["checks"] if check["check_name"] == "Completeness")

        self.assertEqual(completeness["bad_records"], 150)
        self.assertEqual(len(completeness["failed_rows"]), 100)
        self.assertTrue(completeness["failed_rows_truncated"])
        self.assertEqual(set(completeness["failed_rows"][0]["values"]), {"value", "other"})

    def test_streaming_failed_rows_include_all_columns(self):
        data = pd.DataFrame({"value": [None, "ok"], "other": ["first", "second"]})
        accumulator = DataQualityAccumulator("sample_bronze", list(data.columns))
        accumulator.update(data)

        result = accumulator.finish(duplicate_count=0)
        completeness = next(
            check for check in result["checks"]
            if check["check_name"] == "Completeness" and check["column_name"] == "value"
        )

        self.assertEqual(completeness["failed_rows"][0]["values"], {
            "value": None,
            "other": "first",
        })

    def test_date_format_and_uniqueness_are_still_scored_without_freshness(self):
        recent = pd.Timestamp.now(tz="UTC").normalize().strftime("%Y-%m-%d")
        data = pd.DataFrame({
            "first_date": [recent, recent, "not-a-date"],
            "second_date": [recent, recent, recent],
        })
        result = calculate_data_quality(data, "events_bronze")

        self.assertFalse(any(check["check_name"] == "Freshness" for check in result["checks"]))
        self.assertTrue(any(check["check_name"] == "Date format validity" for check in result["checks"]))
        self.assertEqual(result["score"], round(result["passed_checks"] / result["total_checks"] * 100, 2))

    def test_date_validity_threshold_is_strictly_over_half_of_non_null_values(self):
        result = calculate_data_quality(pd.DataFrame({"event": ["2024-01-01", ""]}), "events_bronze")
        self.assertFalse(any(check["check_name"] == "Date format validity" for check in result["checks"]))

    def test_date_parser_skips_uuid_shapes_and_supports_mixed_date_formats(self):
        identifiers = pd.Series(["06b8999e2fba1a1fbc88172c00ba8bc7"] * 3)
        with patch("app.services.dq_calculation.pd.to_datetime", side_effect=AssertionError):
            self.assertTrue(_date_series(identifiers).isna().all())

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = calculate_data_quality(
                pd.DataFrame({"event": ["2024-01-02", "01/03/2024", "not-a-date"]}),
                "events_bronze",
            )
        parse_check = next(check for check in result["checks"] if check["check_name"] == "Date format validity")
        self.assertEqual((parse_check["bad_records"], parse_check["total_checked"]), (1, 3))
        self.assertFalse(caught)

    def test_empty_dataframe_has_no_checks_or_score(self):
        result = calculate_data_quality(pd.DataFrame(columns=["email", "price"]), "empty_bronze")
        self.assertEqual(result["rows_tested"], 0)
        self.assertEqual(result["total_checks"], 0)
        self.assertEqual(result["score"], 0.0)

    def test_chunked_calculation_matches_full_dataframe_checks(self):
        data = pd.DataFrame({
            "event": ["2024-01-02", "01/03/2024", "not-a-date", None]
                + ["2024-02-01"] * 18,
            "metric": [1, -2] + [1] * 19 + [None],
            "label": ["same", "same", "", "other"] + ["other"] * 18,
        })
        accumulator = DataQualityAccumulator("events_bronze", list(data.columns))
        accumulator.update(data.iloc[:2])
        accumulator.update(data.iloc[2:])

        expected = calculate_data_quality(data, "events_bronze")
        actual = accumulator.finish(duplicate_count=0)
        expected_checks = {
            (check["column_name"], check["check_name"]): check
            for check in expected["checks"]
            if check["check_name"] != "Full-row duplicates"
        }
        actual_checks = {
            (check["column_name"], check["check_name"]): check
            for check in actual["checks"]
            if check["check_name"] != "Full-row duplicates"
        }

        self.assertEqual(actual["rows_tested"], expected["rows_tested"])
        self.assertEqual(set(actual_checks), set(expected_checks))
        for key, check in expected_checks.items():
            self.assertEqual(actual_checks[key]["bad_records"], check["bad_records"], key)
            self.assertEqual(actual_checks[key]["total_checked"], check["total_checked"], key)
        self.assertNotIn(("metric", "Negative values"), actual_checks)


class DQServicePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_returns_and_persists_per_check_results(self):
        async def fetch_side_effect(query, *args):
            if "information_schema.tables" in query:
                return [{"exists": 1}]
            if "information_schema.columns" in query:
                return [{"name": "email", "type": "text"}, {"name": "price", "type": "text"}]
            if query.startswith("SELECT * FROM bronze."):
                return [
                    {"email": "ok@example.com", "price": "5"},
                    {"email": "bad-email", "price": "-1"},
                ]
            return []

        with (
            patch.object(bronze_service.database, "fetch", new_callable=AsyncMock, side_effect=fetch_side_effect),
            patch.object(
                bronze_service, "_calculate_table_quality", new_callable=AsyncMock,
                return_value=calculate_data_quality(
                    pd.DataFrame({
                        "email": [None, "bad-email"],
                        "price": ["5", "-1"],
                    }),
                    "orders_bronze",
                ),
            ) as calculate_mock,
            patch.object(
                bronze_service.database, "fetchrow", new_callable=AsyncMock,
                side_effect=lambda query, *args: (
                    {"run_id": uuid4()} if "INSERT INTO public.dq_quality_runs" in query else None
                ),
            ),
            patch.object(bronze_service.database, "execute", new_callable=AsyncMock) as execute_mock,
        ):
            result = await bronze_service.run_dq_check("project-1", ["orders"])

        self.assertEqual(result["total_checks"], 5)
        self.assertEqual(result["passed_checks"], 2)
        self.assertEqual(result["table_quality"][0]["total_checks"], 5)
        self.assertEqual(result["table_quality"][0]["passed_checks"], 2)
        self.assertEqual(result["table_quality"][0]["score"], 40.0)
        self.assertEqual(result["issues_count"], 1)
        self.assertEqual(result["warnings_count"], 1)
        calculate_mock.assert_awaited_once_with(
            "orders_bronze", ["email", "price"]
        )
        self.assertEqual(result["dq_score"], round(result["table_quality"][0]["score"], 2))
        self.assertEqual(result["table_quality"][0]["schema_integrity"], {"status": "Pass", "changes": []})
        self.assertEqual(result["table_quality"][0]["dimension_status"], {
            "Completeness": "Fail",
            "Uniqueness": "Pass",
            "Validity": "Fail",
            "Referential Integrity": "N/A",
            "Schema Integrity": "Pass",
        })
        detail_inserts = [
            call for call in execute_mock.await_args_list
            if "INSERT INTO public.dq_check_results" in call.args[0]
        ]
        self.assertEqual(len(detail_inserts), len(result["check_results"]))
        self.assertTrue(any("INSERT INTO public.dq_schema_snapshots" in call.args[0]
                            for call in execute_mock.await_args_list))

    async def test_referential_integrity_counts_orphaned_rows(self):
        source = AsyncMock()
        source.fetch.return_value = [{
            "table_schema": "public",
            "child_table": "orders",
            "fk_column": "customer_id",
            "parent_schema": "public",
            "parent_table": "customers",
            "pk_column": "id",
        }]
        async def bronze_fetch(query, *args):
            if "ANY($1::text[])" in query:
                return [{"table_name": "orders_bronze"}, {"table_name": "customers_bronze"}]
            return [{"count": 1 if "NOT EXISTS" in query else 2}]

        with (
            patch.object(bronze_service, "_user_conn", new_callable=AsyncMock, return_value=source),
            patch.object(bronze_service.database, "fetch", new_callable=AsyncMock, side_effect=bronze_fetch),
        ):
            result = await bronze_service.check_referential_integrity(
                {"schema": "public"}, ["orders"]
            )

        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]["rows_checked"], result[0]["fk_failures"]), (2, 1))
        self.assertEqual((result[0]["ri_pct"], result[0]["status"]), (50.0, "Fail"))
        source.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
