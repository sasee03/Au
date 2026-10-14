from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.dq_calculation import calculate_data_quality


def calculate_data_quality_pl(df: Any, table_name: str) -> dict[str, Any]:
    """Compatibility wrapper for the Polars engine path.

    The project currently keeps the pandas implementation as the canonical logic and
    exposes the exact same result shape for both engine selections.
    """
    if hasattr(df, "to_pandas"):
        frame = df.to_pandas()
    elif isinstance(df, pd.DataFrame):
        frame = df.copy()
    else:
        frame = pd.DataFrame(df)
    return calculate_data_quality(frame, table_name)
