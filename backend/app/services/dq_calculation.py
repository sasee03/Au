"""Shape-based data quality checks for bronze DataFrames."""
from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd


MAX_FAILED_ROW_DETAILS = 100
CHECK_DIMENSIONS = {
    "Completeness": "Completeness",
    "Full-row duplicates": "Uniqueness",
    "Numeric type consistency": "Validity",
    "Date format validity": "Validity",
    "Constant column warning": "Validity",
    "Referential integrity": "Referential Integrity",
    "Schema integrity": "Schema Integrity",
}
QUALITY_DIMENSIONS = (
    "Completeness",
    "Uniqueness",
    "Validity",
    "Referential Integrity",
    "Schema Integrity",
)
_SEVERITY_LEVELS = ("Low", "Medium", "High", "Critical")
_BUMPED_SEVERITY_CHECKS = {"Full-row duplicates", "Referential integrity"}
log = logging.getLogger("aurum.dq")
_DATE_SHAPE_PATTERN = re.compile(
    r"(?:\b\d{1,4}[-/]\d{1,2}(?:[-/]\d{1,4})?\b"
    r"|\b\d{1,4}\.\d{1,2}\.\d{1,4}\b"
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\b"
    r"|(?<![A-Za-z0-9])\d{8}(?![A-Za-z0-9])"
    r"|(?<![A-Za-z0-9])\d{4}(?![A-Za-z0-9])"
    r"|\b\d{1,2}\s+[A-Za-z]{3,}\b"
    r"|\b\d{4}\s+[A-Za-z]{3,}\b"
    r"|\b[A-Za-z]{3,}\s+\d{1,2}\b)",
    re.IGNORECASE,
)
_UUID_SHAPE_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def check_severity(check_name: str, bad_pct: float, passed: bool = False) -> str:
    """Map failure rate to severity, increasing uniqueness and RI one level."""
    if passed:
        return "Low"
    if bad_pct >= 50:
        index = 3
    elif bad_pct >= 20:
        index = 2
    elif bad_pct >= 5:
        index = 1
    else:
        index = 0
    if check_name in _BUMPED_SEVERITY_CHECKS:
        index = min(index + 1, len(_SEVERITY_LEVELS) - 1)
    return _SEVERITY_LEVELS[index]


def dimension_for_check(check_name: str) -> str:
    dimension = CHECK_DIMENSIONS.get(check_name)
    if dimension is None:
        log.warning("Unmapped DQ check %r; assigning it to Validity", check_name)
        return "Validity"
    return dimension


def dimension_statuses(checks: list[dict[str, Any]]) -> dict[str, str]:
    grouped = {dimension: [] for dimension in QUALITY_DIMENSIONS}
    for check in checks:
        grouped[dimension_for_check(check["check_name"])].append(check)
    return {
        dimension: (
            "N/A" if not dimension_checks
            else "Fail" if any(not check["passed"] for check in dimension_checks)
            else "Pass"
        )
        for dimension, dimension_checks in grouped.items()
    }


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _failed_rows(
    data: pd.DataFrame, mask: pd.Series
) -> list[dict[str, Any]]:
    positions = mask.fillna(False).to_numpy().nonzero()[0][:MAX_FAILED_ROW_DETAILS]
    return [
        {
            "row_number": int(position + 1),
            "values": {
                str(column): _json_value(value)
                for column, value in data.iloc[position].items()
            },
        }
        for position in positions
    ]


def _date_series(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values.dtype) or pd.api.types.is_bool_dtype(values.dtype):
        return pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns, UTC]")
    if pd.api.types.is_datetime64_any_dtype(values.dtype):
        return pd.to_datetime(values, errors="coerce", utc=True)

    text = values.astype("string")
    candidates = text.str.contains(_DATE_SHAPE_PATTERN, na=False)
    candidates &= ~text.str.fullmatch(_UUID_SHAPE_PATTERN, na=False)
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns, UTC]")
    if not candidates.any():
        return parsed

    candidate_values = text[candidates]
    unique_values = candidate_values.drop_duplicates()
    unique_parsed = pd.to_datetime(
        unique_values, errors="coerce", format="mixed", utc=True
    )
    mapped_values = pd.to_datetime(
        candidate_values.map(dict(zip(unique_values, unique_parsed))),
        errors="coerce",
        utc=True,
    )
    parsed.loc[candidate_values.index] = mapped_values
    return parsed


def _check(
    table_name: str,
    column_name: str,
    inferred_type: str,
    check_name: str,
    total_checked: int,
    bad_records: int,
    data: pd.DataFrame,
    failed_mask: pd.Series | None = None,
    kpi_name: str | None = None,
    kpi_value: float | None = None,
    bad_pct: float | None = None,
) -> dict[str, Any]:
    passed = bad_records == 0
    rate = (bad_records / total_checked * 100.0) if total_checked else 0.0
    bad_pct = round(rate if bad_pct is None else bad_pct, 2)
    result = {
        "table_name": table_name,
        "column_name": column_name,
        "inferred_type": inferred_type,
        "semantic_type": None,
        "check_name": check_name,
        "rule": check_name,
        "total_checked": int(total_checked),
        "bad_records": int(bad_records),
        "bad_pct": bad_pct,
        "passed": passed,
        "severity": check_severity(check_name, bad_pct, passed),
        "count": int(bad_records),
        "kpi_name": kpi_name,
        "kpi_value": round(float(kpi_value), 2) if kpi_value is not None else None,
    }
    if failed_mask is not None:
        result["failed_rows"] = _failed_rows(data, failed_mask)
        result["failed_rows_truncated"] = len(result["failed_rows"]) >= MAX_FAILED_ROW_DETAILS
    return result


def _date_rates(data: pd.DataFrame) -> list[tuple[str, pd.Series, float]]:
    rates = []
    for column_name in data.columns:
        values = data[column_name]
        candidates = values.notna()
        denominator = int(candidates.sum())
        parsed = _date_series(values)
        rate = float(parsed[candidates].notna().mean()) if denominator else 0.0
        rates.append((str(column_name), parsed, rate))
    return rates


def calculate_data_quality(data: pd.DataFrame, table_name: str) -> dict[str, Any]:
    """Run applicable checks and return a pass-rate score for this table."""
    checks: list[dict[str, Any]] = []
    row_count = len(data.index)
    date_rates = _date_rates(data)
    today = pd.Timestamp.now(tz="UTC")

    if row_count:
        for column_name in data.columns:
            name = str(column_name)
            values = data[column_name]
            text = values.astype("string")
            null_mask = values.isna()
            blank_mask = values.notna() & text.str.strip().eq("").fillna(False)
            incomplete_mask = null_mask | blank_mask
            complete_pct = 100.0 - (int(incomplete_mask.sum()) / row_count * 100.0)
            checks.append(_check(
                table_name, name, str(values.dtype), "Completeness", row_count,
                int(incomplete_mask.sum()), data, incomplete_mask,
                "% Complete", complete_pct,
            ))

            if not (
                pd.api.types.is_numeric_dtype(values.dtype)
                and not pd.api.types.is_bool_dtype(values.dtype)
            ):
                candidates = values.notna() & text.str.strip().ne("").fillna(False)
                candidate_values = text[candidates].str.strip()
                numeric = pd.to_numeric(candidate_values, errors="coerce")
                numeric_rate = float(numeric.notna().mean()) if len(candidate_values) else 0.0
                date_rate = next(rate for col, _, rate in date_rates if col == name)

                if numeric_rate > 0.5 and date_rate <= 0.5:
                    invalid = numeric.isna()
                    failed_mask = pd.Series(False, index=data.index)
                    failed_mask.loc[candidate_values.index[invalid]] = True
                    checks.append(_check(
                        table_name, name, "TEXT",                         "Numeric type consistency", len(candidate_values),
                        int(invalid.sum()), data, failed_mask,
                    ))
                elif date_rate > 0.5:
                    parsed = next(parsed for col, parsed, _ in date_rates if col == name)
                    invalid_mask = candidates & parsed.isna()
                    checks.append(_check(
                        table_name, name, "DATE", "Date format validity", int(candidates.sum()),
                        int(invalid_mask.sum()), data, invalid_mask,
                    ))
                else:
                    distinct_count = int(values.nunique(dropna=True))
                    if distinct_count == 1:
                        checks.append(_check(
                            table_name, name, "TEXT", "Constant column warning", 1, 1, data,
                            bad_pct=0.0,
                        ))

    if row_count:
        duplicate_count = row_count - int(len(data.drop_duplicates()))
        duplicate_mask = data.duplicated(keep=False)
        checks.append(_check(
            table_name, "__table__", "TABLE", "Full-row duplicates", row_count,
            duplicate_count, data, duplicate_mask, "% Unique",
            (row_count - duplicate_count) / row_count * 100.0,
        ))

    issues = [check for check in checks if not check["passed"]]
    passed_checks = sum(1 for check in checks if check["passed"])
    total_checks = len(checks)
    score = passed_checks / total_checks * 100.0 if total_checks else 0.0
    return {
        "table_name": table_name,
        "score": round(score, 2),
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "issue_count": len(issues),
        "rows_tested": row_count,
        "checks": checks,
        "issues": issues,
    }


def _aggregate_check(
    table_name: str,
    column_name: str,
    inferred_type: str,
    check_name: str,
    total_checked: int,
    bad_records: int,
    failed_rows: list[dict[str, Any]] | None = None,
    kpi_name: str | None = None,
    kpi_value: float | None = None,
    bad_pct: float | None = None,
    include_failed_rows: bool = False,
) -> dict[str, Any]:
    passed = bad_records == 0
    resolved_bad_pct = round(
        bad_records / total_checked * 100.0 if total_checked else 0.0,
        2,
    ) if bad_pct is None else round(bad_pct, 2)
    result = {
        "table_name": table_name,
        "column_name": column_name,
        "inferred_type": inferred_type,
        "semantic_type": None,
        "check_name": check_name,
        "rule": check_name,
        "total_checked": int(total_checked),
        "bad_records": int(bad_records),
        "bad_pct": resolved_bad_pct,
        "passed": passed,
        "severity": check_severity(check_name, resolved_bad_pct, passed),
        "count": int(bad_records),
        "kpi_name": kpi_name,
        "kpi_value": round(float(kpi_value), 2) if kpi_value is not None else None,
    }
    if include_failed_rows and failed_rows is not None:
        result["failed_rows"] = failed_rows
        result["failed_rows_truncated"] = len(failed_rows) >= MAX_FAILED_ROW_DETAILS
    return result


class DataQualityAccumulator:
    """Aggregate exact data-quality counts while retaining only bounded row samples."""

    def __init__(self, table_name: str, column_names: list[str]):
        self.table_name = table_name
        self.column_names = column_names
        self.row_count = 0
        self.columns: dict[str, dict[str, Any]] = {
            name: {
                "dtype": "object",
                "native_numeric": False,
                "non_null": 0,
                "blank": 0,
                "date_valid": 0,
                "date_valid_nonblank": 0,
                "date_max": None,
                "numeric_candidates": 0,
                "numeric_valid": 0,
                "distinct_values": [],
                "samples": {},
            }
            for name in column_names
        }

    def _add_samples(
        self,
        state: dict[str, Any],
        check_name: str,
        data: pd.DataFrame,
        mask: pd.Series,
    ) -> None:
        samples = state["samples"].setdefault(check_name, [])
        remaining = MAX_FAILED_ROW_DETAILS - len(samples)
        if remaining <= 0:
            return
        positions = mask.fillna(False).to_numpy().nonzero()[0][:remaining]
        for position in positions:
            samples.append({
                "row_number": self.row_count + int(position) + 1,
                "values": {
                    str(column): _json_value(value)
                    for column, value in data.iloc[position].items()
                },
            })

    def update(self, data: pd.DataFrame) -> None:
        batch_size = len(data.index)
        if not batch_size:
            return

        for name in self.column_names:
            values = data[name]
            state = self.columns[name]
            text = values.astype("string")
            non_null = values.notna()
            blank = non_null & text.str.strip().eq("").fillna(False)
            nonblank = non_null & ~blank
            state["non_null"] += int(non_null.sum())
            state["blank"] += int(blank.sum())

            if non_null.any() and state["dtype"] == "object":
                state["dtype"] = str(values.dtype)

            numeric_dtype = (
                pd.api.types.is_numeric_dtype(values.dtype)
                and not pd.api.types.is_bool_dtype(values.dtype)
            )
            state["native_numeric"] |= numeric_dtype

            parsed_dates = _date_series(values)
            valid_dates = parsed_dates.notna()
            state["date_valid"] += int((valid_dates & non_null).sum())
            state["date_valid_nonblank"] += int((valid_dates & nonblank).sum())
            if valid_dates.any():
                batch_max = parsed_dates.max()
                if state["date_max"] is None or batch_max > state["date_max"]:
                    state["date_max"] = batch_max

            if numeric_dtype:
                numeric = pd.to_numeric(values, errors="coerce")
                valid_numeric = numeric.notna()
                state["numeric_candidates"] += int(valid_numeric.sum())
            else:
                candidate_values = text[nonblank].str.strip()
                numeric = pd.to_numeric(candidate_values, errors="coerce")
                valid_numeric = numeric.notna()
                state["numeric_candidates"] += len(candidate_values)
                invalid_numeric = pd.Series(False, index=data.index)
                invalid_numeric.loc[candidate_values.index[~valid_numeric]] = True
                self._add_samples(state, "Numeric type consistency", data, invalid_numeric)

            valid_values = numeric[valid_numeric]
            state["numeric_valid"] += len(valid_values)

            for value in values.dropna().tolist():
                if len(state["distinct_values"]) >= 2:
                    break
                if not any(value == existing for existing in state["distinct_values"]):
                    state["distinct_values"].append(value)

            invalid_dates = nonblank & ~valid_dates
            self._add_samples(state, "Date format validity", data, invalid_dates)
            self._add_samples(state, "Completeness", data, ~non_null | blank)

        self.row_count += batch_size

    def finish(self, duplicate_count: int = 0) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        date_rates = {
            name: state["date_valid"] / state["non_null"] if state["non_null"] else 0.0
            for name, state in self.columns.items()
        }

        if self.row_count:
            for name, state in self.columns.items():
                incomplete = self.row_count - state["non_null"] + state["blank"]
                checks.append(_aggregate_check(
                    self.table_name, name, state["dtype"], "Completeness", self.row_count,
                    incomplete, state["samples"].get("Completeness"),
                    "% Complete", 100.0 - incomplete / self.row_count * 100.0,
                    include_failed_rows=True,
                ))

                numeric_rate = (
                    state["numeric_valid"] / state["numeric_candidates"]
                    if state["numeric_candidates"] else 0.0
                )
                date_rate = date_rates[name]
                if state["native_numeric"]:
                    continue
                elif numeric_rate > 0.5 and date_rate <= 0.5:
                    invalid_numeric = state["numeric_candidates"] - state["numeric_valid"]
                    checks.append(_aggregate_check(
                        self.table_name, name, "TEXT", "Numeric type consistency",
                        state["numeric_candidates"], invalid_numeric,
                        state["samples"].get("Numeric type consistency"),
                        include_failed_rows=True,
                    ))
                elif date_rate > 0.5:
                    date_candidates = state["non_null"] - state["blank"]
                    invalid_dates = date_candidates - state["date_valid_nonblank"]
                    checks.append(_aggregate_check(
                        self.table_name, name, "DATE", "Date format validity",
                        date_candidates, invalid_dates,
                        state["samples"].get("Date format validity"),
                        include_failed_rows=True,
                    ))
                elif len(state["distinct_values"]) == 1:
                    checks.append(_aggregate_check(
                        self.table_name, name, "TEXT", "Constant column warning",
                        1, 1, bad_pct=0.0,
                    ))

            checks.append(_aggregate_check(
                self.table_name, "__table__", "TABLE", "Full-row duplicates",
                self.row_count, duplicate_count, bad_pct=(
                    (self.row_count - duplicate_count) / self.row_count * 100.0
                ),
            ))

        issues = [check for check in checks if not check["passed"]]
        passed_checks = sum(1 for check in checks if check["passed"])
        total_checks = len(checks)
        return {
            "table_name": self.table_name,
            "score": round(passed_checks / total_checks * 100.0, 2) if total_checks else 0.0,
            "passed_checks": passed_checks,
            "total_checks": total_checks,
            "issue_count": len(issues),
            "rows_tested": self.row_count,
            "checks": checks,
            "issues": issues,
        }