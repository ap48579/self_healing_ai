"""The research harness's RSI-editable surface, structured as Harness²'s
c1-c8 component taxonomy (docs/05_rsi_harness2_design_spec.md S1/S2)
instead of a flat file list.

Resolves open question 3 from that spec, now that real usage exists:
c2 (guardrails) is merged into c1 -- both are instructional text inside
prompts.py, and agents/research/policies.py (never RSI-editable, see
docs/01_harness_spec.md S5) is the actual hard-guardrail layer, so there
was never a separate *editable* guardrails file to point at. c4 (skills)
is merged into c6 -- GPT Researcher's own skills/ directory is role
*implementation*, matching c6's "subagents" better than Harness²'s
invokable-skill-file sense of c4. c3 (memory) is Cortex, external, never
part of this tree by design. c8 (plugins) is excluded for v1: mcp/,
document/, vector_store/ are inert (not turned on), and editing dead code
has nothing for the benchmark to gate on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Component:
    id: str
    name: str
    files: list[str]
    description: str


COMPONENT_TREE: list[Component] = [
    Component(
        id="c1",
        name="system_prompt",
        files=[
            "agents/research/gpt_researcher/prompts.py",
            "agents/research/gpt_researcher/actions/agent_creator.py",
        ],
        description="Prompt templates and the dynamic per-query persona. c2 (guardrails) merged here.",
    ),
    Component(
        id="c5",
        name="tool_guidance",
        files=[
            "agents/research/gpt_researcher/actions/retriever.py",
            "agents/research/gpt_researcher/actions/web_scraping.py",
        ],
        description="How retriever/scraper results get used -- not the fetch mechanics themselves.",
    ),
    Component(
        id="c6",
        name="subagents",
        files=[
            "agents/research/gpt_researcher/skills/researcher.py",
            "agents/research/gpt_researcher/skills/writer.py",
            "agents/research/gpt_researcher/skills/curator.py",
        ],
        description="The investigate/write/curate role implementations. c4 (skills) merged here.",
    ),
    Component(
        id="c7",
        name="scripts",
        files=[
            "agents/research/gpt_researcher/actions/query_processing.py",
            "agents/research/gpt_researcher/actions/report_generation.py",
            "research_pipeline.py",
        ],
        description="Sub-question generation, report-writing glue, and our own orchestration "
                    "constants (MAX_REVISIONS) -- same role pipeline.py's MAX_DEBUGGER_ATTEMPTS plays today.",
    ),
]

ALLOWED_FILES: list[str] = [f for c in COMPONENT_TREE for f in c.files]
