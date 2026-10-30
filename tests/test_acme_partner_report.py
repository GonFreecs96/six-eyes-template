"""Hermetic test for referral partner report builder (no BigQuery)."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from reports.acme_referral_partner.build_report import build_report, write_workbook


@pytest.fixture
def sample_frames():
    summary = pd.DataFrame(
        [
            {
                "partner_code": "zanybyte_podcast",
                "clicks": 1200,
                "signups": 180,
                "trials_started": 150,
                "paid_subscriptions": 42,
            }
        ]
    )
    detail = pd.DataFrame(
        [
            {
                "ref_click_id": "clk_001",
                "signup_id": "sgn_001",
                "user_id": "usr_001",
                "window_days": 14,
            }
        ]
    )
    return summary, detail


def test_build_report_metadata(sample_frames, tmp_path: Path):
    summary, detail = sample_frames
    meta = build_report(summary, detail, date(2026, 10, 13))
    assert meta["partner"] == "Zanybyte Media Partners"
    assert meta["row_count_summary"] == 1
    assert meta["metrics"][0]["paid_subscriptions"] == 42

    out = tmp_path / "report.xlsx"
    write_workbook(summary, detail, out)
    assert out.exists()
    loaded = pd.read_excel(out, sheet_name="Summary")
    assert loaded.iloc[0]["clicks"] == 1200
