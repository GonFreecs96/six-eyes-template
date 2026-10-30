"""Read-only BigQuery helper for Six Eyes (vendored; no external analytics plugins).

Loads project/dataset/max_bytes_billed from config/runtime.yaml with env overrides.
Enforces dry-run by default, a max-bytes-billed cap, and a read-only SQL guard.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_CONFIG = REPO_ROOT / "config" / "runtime.yaml"

READ_ONLY_DENIED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BqConfig:
    project: str
    dataset: str
    max_bytes_billed: int


def load_runtime_config() -> dict[str, Any]:
    if not RUNTIME_CONFIG.is_file():
        return {}
    return yaml.safe_load(RUNTIME_CONFIG.read_text()) or {}


def load_bq_config() -> BqConfig:
    cfg = load_runtime_config()
    bq = cfg.get("bigquery") or {}
    project = os.environ.get("SIX_EYES_BQ_PROJECT") or bq.get("project") or "your-gcp-project"
    dataset = os.environ.get("SIX_EYES_BQ_DATASET") or bq.get("dataset") or "acme_analytics"
    max_bytes = int(bq.get("max_bytes_billed") or 1_000_000_000)
    return BqConfig(project=project, dataset=dataset, max_bytes_billed=max_bytes)


def get_mode() -> str:
    return os.environ.get("SIX_EYES_MODE") or (load_runtime_config().get("mode") or "offline")


def assert_read_only_sql(sql: str) -> None:
    if READ_ONLY_DENIED.search(sql):
        raise ValueError("Only read-only SELECT queries are allowed")


def dry_run_query(
    sql: str,
    *,
    client: Any | None = None,
    bq_config: BqConfig | None = None,
) -> dict[str, Any]:
    """Dry-run SQL and return job statistics (no rows)."""
    assert_read_only_sql(sql)
    bq_config = bq_config or load_bq_config()
    from google.cloud import bigquery

    client = client or bigquery.Client(project=bq_config.project)
    jc = bigquery.QueryJobConfig(
        dry_run=True,
        use_query_cache=False,
        maximum_bytes_billed=bq_config.max_bytes_billed,
    )
    job = client.query(sql, job_config=jc, project=bq_config.project)
    return {
        "total_bytes_processed": job.total_bytes_processed,
        "total_bytes_billed": job.total_bytes_billed,
        "statement_type": job.statement_type,
    }


def run_query(
    sql: str,
    *,
    client: Any | None = None,
    bq_config: BqConfig | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Execute or dry-run a read-only query."""
    assert_read_only_sql(sql)
    bq_config = bq_config or load_bq_config()
    if dry_run:
        return dry_run_query(sql, client=client, bq_config=bq_config)

    from google.cloud import bigquery

    client = client or bigquery.Client(project=bq_config.project)
    jc = bigquery.QueryJobConfig(maximum_bytes_billed=bq_config.max_bytes_billed)
    rows = client.query(sql, job_config=jc, project=bq_config.project).result()
    return [dict(row.items()) for row in rows]


def qualified_table(table: str, bq_config: BqConfig | None = None) -> str:
    """Return `project.dataset.table` for a bare table name."""
    bq_config = bq_config or load_bq_config()
    if table.count(".") >= 2:
        return table
    if table.count(".") == 1:
        return f"{bq_config.project}.{table}"
    return f"{bq_config.project}.{bq_config.dataset}.{table}"
