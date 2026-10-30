#!/usr/bin/env python3
"""Build Zanybyte weekly partner XLSX from an in-memory summary DataFrame.

Live runs execute extract.sql via BigQuery; offline tests pass a fake DataFrame.
Writes Summary + Detail tabs, run_status JSON, and a handoff markdown note.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "outputs" / "reports"


def build_report(summary_df: pd.DataFrame, detail_df: pd.DataFrame, report_date: date) -> dict:
    """Return metadata dict; does not write files."""
    return {
        "partner": "Zanybyte Media Partners",
        "report_date": report_date.isoformat(),
        "row_count_summary": len(summary_df),
        "row_count_detail": len(detail_df),
        "metrics": summary_df.to_dict(orient="records"),
    }


def write_workbook(
    summary_df: pd.DataFrame,
    detail_df: pd.DataFrame,
    out_xlsx: Path,
) -> None:
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        detail_df.to_excel(writer, sheet_name="Detail", index=False)


def write_run_status(status_path: Path, payload: dict) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_handoff(handoff_path: Path, report_date: date, out_xlsx: Path) -> None:
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        f"# Partner report handoff — {report_date.isoformat()}\n\n"
        f"- Partner: Zanybyte Media Partners (fictional)\n"
        f"- Deliverable: `{out_xlsx.name}`\n"
        f"- Contact: dana.quill@example.com\n"
        f"- Notes: Compare 7-day vs 14-day windows per PLT-009.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Acme referral partner weekly report")
    parser.add_argument("--report-date", type=lambda s: date.fromisoformat(s), default=date.today())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true", help="Skip writing xlsx (status + handoff only)")
    args = parser.parse_args()

    # Placeholder: live mode would load from BQ. Demo uses empty frames unless caller imports build_report.
    summary = pd.DataFrame(
        columns=["partner_code", "clicks", "signups", "trials_started", "paid_subscriptions"]
    )
    detail = pd.DataFrame(columns=["ref_click_id", "signup_id", "user_id", "window_days"])

    meta = build_report(summary, detail, args.report_date)
    stem = f"zanybyte_referral_{args.report_date.isoformat()}"
    out_xlsx = args.output_dir / f"{stem}.xlsx"
    status_path = args.output_dir / f"{stem}_run_status.json"
    handoff_path = args.output_dir / f"{stem}_handoff.md"

    if not args.dry_run:
        write_workbook(summary, detail, out_xlsx)
    write_run_status(
        status_path,
        {
            **meta,
            "status": "ok",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "xlsx_path": str(out_xlsx) if not args.dry_run else None,
        },
    )
    write_handoff(handoff_path, args.report_date, out_xlsx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
