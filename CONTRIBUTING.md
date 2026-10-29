# Contributing

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Running tests

```bash
python -m tests.test_cortex   # no API key needed, covers cortex/ in isolation
```

There's no test suite for `agents/`, `rsi/`, or the pipelines beyond this
— those are exercised via dry-run mode (omit `ANTHROPIC_API_KEY`/
`QWEN_API_KEY` and the pipelines run with placeholder LLM responses,
exercising the real control flow) and the RSI engine's own benchmark-gated
mechanics tests (see `docs/05_rsi_harness2_design_spec.md` for how those
were validated during development).

## The fixed-substrate vs. strategy-surface boundary

This is the one thing to understand before touching `agents/research/`:

- **Fixed substrate** — `agents/research/gpt_researcher/`'s infrastructure
  (`llm_provider/`, `retrievers/`, `scraper/`, `document/`, `vector_store/`,
  etc.), `agents/research/policies.py` (the hard guardrail layer), and
  `agents/base.py`. Never proposed as an RSI edit, by construction — these
  files aren't in any `HarnessSpec.allowed_files`. If you're adding a new
  retriever or fixing a bug in the vendoring, you're working here, and
  that's a normal PR.
- **Strategy surface** — `agents/research/gpt_researcher/prompts.py`,
  `query_processing.py`, `researcher.py`, `writer.py`, `curator.py`,
  `report_generation.py`, `agent_creator.py`, `retriever.py`,
  `web_scraping.py`, plus `research_pipeline.py`'s orchestration
  constants. These are what `rsi/` is allowed to edit. A PR touching these
  files for this repo's own harness is fine too — just know that any
  third-party consumer who's exported their own copy (`agents.research.
  scaffold.export_strategy()`) won't see your change until they re-export
  or manually port it; see `agents/research/VENDOR.md` for the update
  process.

Don't add a new file to the strategy surface list (`rsi/harnesses.py`'s
`RESEARCH_HARNESS.component_tree`) without a real reason RSI should be
allowed to edit it — the allowlist is deliberately small.

## Updating the vendored GPT Researcher pin

See `agents/research/VENDOR.md`. Re-clone at the new tag, diff against the
current vendored tree, re-apply any edits listed there that upstream
hasn't since incorporated, and update the pinned commit/tag in that file.

## Git safety for RSI's own branches

`rsi/lineage-<harness>` branches are the self-improvement engine's own
accepted-edit history. Don't force-push over them or rebase them away —
treat them the same as any other branch with real history you'd want to
keep, even though nothing merges them into `main` automatically.
