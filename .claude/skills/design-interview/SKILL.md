---
name: design-interview
description: >
  Structured interview for ideation, scoping, and planning phases of new projects.
  Walks down the design tree branch-by-branch, resolving dependencies one decision
  at a time. Provides a recommended answer for every question; explores the codebase
  instead of asking when the answer is discoverable.
allowed-tools:
  - Read
  - Bash(find:*)
  - Bash(grep:*)
  - Bash(git log:*)
  - Bash(git diff:*)
  - Bash(ls:*)
  - Glob
  - Grep
---

# Skill: Design Interview

## Purpose

Drive a structured, relentless interview that walks down every branch of a design tree
until a shared understanding is reached. Useful at the start of any new project, feature,
or significant refactor — before implementation begins.

## Invocation

```
/design-interview [brief description of the plan or idea]
```

The argument is optional. If omitted, ask the operator for a one-sentence description before
starting.

## Behavior

### Core rules

1. **One question at a time.** Never present a list of questions. Pick the highest-priority
   unresolved question, ask it, wait for the answer, then move to the next.
2. **Always provide a recommended answer.** Frame it as: "My recommendation: [answer] —
   [one-line rationale]." the operator can accept, override, or redirect.
3. **Explore the codebase instead of asking** when the answer is discoverable. If a
   question is about existing behavior, data shape, naming conventions, file structure,
   or anything that can be resolved by reading the repo — read it and report what you
   found rather than asking.
4. **Resolve dependencies in order.** Walk the decision tree depth-first: settle
   foundational decisions before derivative ones. Don't ask about implementation details
   before the approach is agreed on.
5. **Keep going.** Continue the interview until every major branch of the design is
   resolved and the plan is specific enough to implement without ambiguity. Don't
   wrap up early.

### Question categories (walk in this order when applicable)

1. **Goal & success** — What problem does this solve? How do we know it worked?
2. **Scope & boundaries** — What's in, what's explicitly out, what's deferred?
3. **Integration points** — What existing systems, data, or workflows does this touch?
4. **Data & schema** — What data is needed? Where does it come from? What's the shape?
5. **Behavior & logic** — How should it work? What are the edge cases?
6. **Implementation approach** — What's the technical strategy? What alternatives exist?
7. **Sequencing & phasing** — What's the right order? What's the MVP? What comes later?
8. **Risks & unknowns** — What could go wrong? What are we uncertain about?

Not every project needs all categories. Skip a category if it's clearly not applicable;
explain why.

### Codebase exploration

Before asking any question that touches existing code or structure:
- Use `find` / `grep` / `Read` to check what's already there.
- Report what you found: "I checked — here's what exists: [finding]. So the question
  becomes: [refined question]."
- If the codebase answers the question fully, skip asking and move on.

### Closing the interview

When all branches are resolved, produce a **Design Summary** in-conversation:

```
## Design Summary — [Plan Title]

### Goal
[One paragraph]

### Scope
- In: ...
- Out: ...
- Deferred: ...

### Key Decisions
[Numbered list — each decision + the agreed answer + one-line rationale]

### Open Items
[Anything deliberately left unresolved, with reason]

### Suggested First Step
[The single most useful next action]
```

Do not write the summary to a file unless the operator asks.
