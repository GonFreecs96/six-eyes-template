# Governed knowledge promotion (slim)

Template replacement for a full multi-detector promotion engine.

## What runs today

```bash
python scripts/governed_knowledge_promote.py
python scripts/governed_knowledge_promote.py --json
```

Steps:

1. Read `data/bq-knowledge.md`
2. Privacy pass (emails/secrets redacted in plan metadata)
3. Write `outputs/governed-promotion/promotion-plan.json`
4. Append ledger event to `data/release-ledger/events.yaml`

If `GOVERNED_REPO` points at a directory, the plan lists suggested patch paths inside that repo. No automatic git push in v1.

## Tests

`tests/test_governed_knowledge_promote.py` uses pytest `tmp_path` for both unset and throwaway governed repos.

## Roadmap

- GitHub Actions workflow (draft PRs, org secrets) — intentionally omitted from this public template
- Richer classifiers (metric gaps, glossary drift) — reintroduce behind interfaces if needed
