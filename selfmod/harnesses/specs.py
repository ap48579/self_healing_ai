"""Registry of HarnessSpecs the self-improvement engine can target.

Coding-only for now. The research harness's RSI engine is a separate design
(Harness²-style Propose/Probe/Compose, see docs/05_rsi_harness2_design_spec.md)
living in its own `rsi/` package once built -- not a second entry here. See
that doc's S0 for why selfmod and the research RSI engine are deliberately
not a shared module.

To point this at a further new agent (fintrack, fittrack, ...) later: write
that agent's pipeline the same way pipeline.py is written (produce Cortex
Episodes with a distinct `domain`), write a fixed benchmark module graded by
ground truth rather than self-report, and add one more HarnessSpec here.
Nothing in selfmod/executor.py or meta_agent.py needs to change.
"""

from __future__ import annotations

from . import coding_benchmark
from ..harness_spec import HarnessSpec

CODING_HARNESS = HarnessSpec(
    name="coding",
    description="a self-healing coding agent (Planner/Coder/Tester/Debugger/Reviewer)",
    allowed_files=[
        "agents/pipeline_agents.py",
        "pipeline.py",
        "cortex/graph.py",
        "cortex/replay.py",
    ],
    benchmark_fn=coding_benchmark.run_benchmark,
    cortex_domain="coding",
)

HARNESSES = {h.name: h for h in (CODING_HARNESS,)}
