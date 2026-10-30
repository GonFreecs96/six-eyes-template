# Module: governed repo (optional)

External sibling repository holding governed metric definitions and guardrails.

Six Eyes does **not** vendor that repo. Configure path via `GOVERNED_REPO` / `runtime.yaml`.

Skills `metric-catalog` and `repo-sync` describe read-only discovery against a local clone.

Promotion v1: `scripts/governed_knowledge_promote.py` only.
