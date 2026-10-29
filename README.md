# self-healing-ai

A memory system, an agent harness, and a self-improvement engine, designed
to be used together or separately:

- **`cortex/`** — cross-episode memory for an agent. Recall (literal
  similarity), Intuition (structural patterns), Caution (known dead ends),
  Instinct (reinforced heuristics promoted after repeated confirmation) —
  backed by ChromaDB + a SQLite-persisted "groove" graph with Hebbian
  reinforcement and time-based decay. Fully domain-agnostic: point it at
  any project via `persist_dir` + `Episode.domain`/`scope`.
- **`agents/`** — two working harnesses built on it: a self-healing coding
  agent (`pipeline.py`, Claude-backed) and an autonomous deep-research
  agent (`research_pipeline.py`, vendoring GPT Researcher, configured for
  local Ollama or DashScope via `agents/research/qwen_config.py`).
- **`rsi/`** — a generic recursive self-improvement engine. Any harness —
  these two, or your own — gets its own git lineage branch, its own
  ground-truth benchmark, and its own ALLOW/ASK/DENY-style hard guardrail
  boundary (`agents/research/policies.py`) that no proposed edit can
  cross. Design: `docs/05_rsi_harness2_design_spec.md`.

Design rationale for the whole project lives in `docs/01` through `docs/05`
— each one documents what was built, what was tried and abandoned, and why,
as the project evolved.

## Install

```bash
git clone https://github.com/ap48579/self_healing_ai.git
cd self_healing_ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

To use it as a dependency from another project instead:

```bash
pip install "self-healing-ai @ git+https://github.com/ap48579/self_healing_ai.git"
# or, for local development against a clone:
pip install -e /path/to/self_healing_ai
```

## Quickstart

```bash
# Coding agent (needs ANTHROPIC_API_KEY; omit it to run in dry-run mode)
export ANTHROPIC_API_KEY=sk-...
python cli.py "write a function that returns the nth fibonacci number"

# Research agent (needs QWEN_API_KEY; QWEN_BASE_URL + QWEN_MODEL for a
# self-hosted/Ollama endpoint, or just QWEN_API_KEY for DashScope)
export QWEN_API_KEY=ollama QWEN_BASE_URL=http://localhost:11434/v1 QWEN_MODEL=qwen3:14b
python cli.py --research "What is the boiling point of water in Celsius at sea level?"

# Cortex memory stats
python cli.py --stats

# Run a self-improvement cycle against one of the two built-in harnesses
python cli.py --self-improve --harness research
python cli.py --self-improve --harness coding
```

## Using the research harness in your own project

The research harness is vendored, not pip-depended-on, specifically so the
self-improvement engine can propose edits to it inside your own git
history instead of a copy shared with anyone else. To get your own copy:

```python
from pathlib import Path
from agents.research.scaffold import export_strategy

export_strategy(Path("./my_research_harness"))
```

This writes a complete, self-sufficient copy (not just the editable files
— see the module's docstring for why a partial copy doesn't work) plus a
`README.md` explaining exactly what to edit, and a `benchmark_template.py`
you need to fill in with your own domain's ground truth before RSI has
anything meaningful to gate on. **Writing that benchmark is the single
most important step** — see `docs/WRITING_YOUR_OWN_BENCHMARK.md`.

Commit the exported directory to your own repo, build a `HarnessSpec`
pointing at it (see `rsi.harness_spec.HarnessSpec` and
`rsi.harnesses.RESEARCH_HARNESS` for the shape), and call `rsi.run_cycle()`
— nothing in `rsi/proposer.py`, `probe.py`, or `composer.py` needs to
change for a new consumer.

## Testing

```bash
python -m tests.test_cortex   # no API key needed
```

## License

Apache 2.0 (`LICENSE`). The vendored GPT Researcher tree under
`agents/research/gpt_researcher/` keeps its own Apache 2.0 license —
see `agents/research/VENDOR.md` for provenance.

## Contributing

See `CONTRIBUTING.md`.
