---
name: voice-rewrite
description: Rewrite draft text in the operator voice from repo-root SOUL.md.
---

# voice-rewrite

Rewrite the provided text to match **`SOUL.md`** at the repo root (voice, register, epistemic norms).

## Steps

1. Read `SOUL.md`. If missing, stop and ask the user to fill the template.
2. Preserve facts and numbers; change tone and structure only.
3. Flag any unsupported claims instead of inventing certainty.

## Optional external style guide

Document a local path in your notes if you keep a richer guide outside this repo. Default is bundled `SOUL.md` only.

## Usage

`/voice-rewrite <paste or file path>`
