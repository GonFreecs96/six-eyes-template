# Six Eyes Template

Open MIT-licensed template of a personal **analytics intelligence** workspace: composable Claude Code skills, a self-scoring backlog, optional BigQuery read-only checks, and an offline demo mode with fictional **Acme** (consumer subscription app) data.

**Author:** Mark Reid. Acme Stream Co., its partners, people, and data are entirely fictional.

## What you get

- Skills for weekly pulse, meeting ingest, staleness scoring, deep dives, and staged `/six-eyes-run`
- Flask backlog board (`webapp/backlog_board/`)
- Vendored BigQuery helper (`scripts/lib/bq_client.py`)
- Slim governed-knowledge promotion plan (`scripts/governed_knowledge_promote.py`)
- Placeholder MCP + outbound write guard (`.claude/settings.json`)

## Quickstart (offline)

```bash
git clone <your-fork> six-eyes-template && cd six-eyes-template
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Ensure config/runtime.yaml has mode: offline (default)
python scripts/init-db.py
python scripts/sync-metadata.py
bash scripts/backlog-board.sh     # optional local UI
```

Run skills from Claude Code or Cursor using `.claude/skills/`. With SEED content present, try `/pulse-scan` and `/status`.

A **demo staging run** ships under `data/staging/` (`run-manifest.md` + `staged/`). After your first git commit, run `python scripts/six-eyes-promote.py record-base` (or re-run `/six-eyes-run`), then `python scripts/six-eyes-promote.py check` and `promote` to apply the staged proposals.

## Live mode

Set `mode: live` in `config/runtime.yaml`, configure `.cursor/mcp.json` / Claude MCP for Atlassian, Slack (read), and Granola. Set GCP credentials for BigQuery via standard `GOOGLE_APPLICATION_CREDENTIALS`.

## Governed metrics repo (optional)

Point `governed_repo` or `GOVERNED_REPO` at a sibling repository to generate local promotion plans under `outputs/governed-promotion/`. Full GitHub Actions draft-PR automation is a documented roadmap item.

## License

MIT — see [LICENSE](LICENSE).
