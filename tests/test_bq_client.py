import pytest

from scripts.lib import bq_client


def test_read_only_guard_blocks_mutations():
    with pytest.raises(ValueError, match="read-only"):
        bq_client.assert_read_only_sql("UPDATE acme_analytics.signups SET x=1")


def test_load_bq_config_defaults(monkeypatch):
    monkeypatch.delenv("SIX_EYES_BQ_PROJECT", raising=False)
    monkeypatch.delenv("SIX_EYES_BQ_DATASET", raising=False)
    cfg = bq_client.load_bq_config()
    assert cfg.project == "your-gcp-project"
    assert cfg.dataset == "acme_analytics"
    assert cfg.max_bytes_billed == 1_000_000_000


def test_qualified_table():
    cfg = bq_client.BqConfig("proj", "ds", 1000)
    assert bq_client.qualified_table("signups", cfg) == "proj.ds.signups"
    assert bq_client.qualified_table("ds.signups", cfg) == "proj.ds.signups"


def test_dry_run_uses_client(monkeypatch):
    class FakeJob:
        total_bytes_processed = 123
        total_bytes_billed = 123
        statement_type = "SELECT"

    class FakeClient:
        def query(self, sql, job_config=None, project=None):
            assert job_config.dry_run is True
            return FakeJob()

    stats = bq_client.dry_run_query(
        "SELECT 1",
        client=FakeClient(),
        bq_config=bq_client.BqConfig("p", "d", 999),
    )
    assert stats["total_bytes_processed"] == 123
