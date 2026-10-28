# Self-Healing Coding Agent + Cortex — Working MVP

Implements the core integration of `coding_agent_plan.md` and
`cortex_reasoning.md` end-to-end: a real agent pipeline, wired to a real
Cortex memory store, verified to run without crashing.

## What's fully built and tested

- **Cortex core** (`cortex/`) — schema, ChromaDB-backed Recall/Intuition/
  Caution/Instinct indices, the groove-weighted memory graph (NetworkX),
  spreading activation, decay, and Sleep-like Consolidation Replay
  (cluster → model-compare → merge/reject → promote to Instinct).
  **Fully tested standalone, no API key required** — `python -m tests.test_cortex`.
- **Agent pipeline** (`agents/`, `pipeline.py`) — Planner, Coder, Tester
  (mechanical, zero thinking), Debugger (escalating effort + parallel
  hypotheses), Reviewer, Learning Agent. Wired end-to-end through
  `cli.py`. Verified to run without crashing in dry-run mode (no API key) —
  exercises the full failure/Debugger-loop path correctly.

## What's deliberately scoped down for this MVP

- **Context Builder** is a stub (lists workspace files). Real codebase
  reading is the most natural next extension.
- **Complexity scoring** is a crude word-count heuristic, not the full
  signal described in the plan (past episode healer-attempt counts aren't
  wired into it yet).
- **Debugger's "parallel hypotheses"** run sequentially in this MVP, not
  concurrently — same logic, straightforward upgrade to `asyncio`/threads later.
- **Layered compression Tier 3** (raw original, reversible cache) isn't
  implemented — Tier 1 (`distilled_learnings`) and Tier 2 (full structured
  arc, in `episodes.jsonl`) are real.
- **Sleep-like Replay** is callable on demand (`cortex.run_replay`), not
  yet wired to idle-detection scheduling — that's a deployment concern.
- **No sandboxing** — Tester runs generated code via direct `subprocess`,
  not Docker/E2B. Fine for trusted local use; revisit before running
  untrusted tasks.

## Setup

```bash
cd self_healing_ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...   # omit to run in dry-run mode
```

## Run

```bash
python cli.py "write a function that returns the nth fibonacci number"
python cli.py --stats   # Cortex memory stats
```

Without `ANTHROPIC_API_KEY` set, agents return placeholder text instead of
real completions — useful for verifying the pipeline wiring, not for real
coding tasks. The Debugger loop, Tester, and Cortex write-back all still
run for real in dry-run mode; only the LLM calls are stubbed.

## Test Cortex in isolation (no API key needed)

```bash
python -m tests.test_cortex
```

Covers: write-back + Recall, Intuition catching a structurally-similar but
surface-dissimilar problem, groove reinforcement strengthening with repeated
success, topic-scoped decay weakening unused edges, spreading activation
decaying with hop distance, and Replay correctly merging a confirmed
cluster vs. rejecting a false-positive one.
