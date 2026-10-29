"""Self-Improvement Planner — the agent that proposes edits to another
agent's own harness source, à la the Weco AI self-rewriting research-agent
loop. Which harness it's editing (coding, research, or a future one) comes
in as a HarnessSpec, so this module has no hardcoded domain knowledge.

Scope is deliberately bounded: it may only touch the target harness's own
allowlisted files, never its own safety machinery, never tests, never the
benchmark it's graded against. The executor is what actually enforces the
allowlist and uniqueness of each edit — this module just asks the model to
propose edits and parses what comes back.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from agents.base import Agent
from .harness_spec import HarnessSpec

MAX_EDITS_PER_CYCLE = 3
MAX_EDIT_CHARS = 4000


@dataclass
class ProposedEdit:
    file: str
    rationale: str
    old_string: str
    new_string: str


@dataclass
class SelfEditPlan:
    summary: str
    edits: list[ProposedEdit] = field(default_factory=list)
    parse_error: str | None = None


def _system_prompt(harness: HarnessSpec) -> str:
    files = "\n".join(f"- {f}" for f in harness.allowed_files)
    return f"""You are the Self-Improvement Planner for {harness.description}. \
You read a trace report of its recent real-world performance (what's succeeding, \
what's failing, how much revision/debugging effort tasks take) and propose small, \
targeted edits to its own harness source code to improve it.

You may ONLY propose edits to these files:
{files}

Rules:
- Propose at most {MAX_EDITS_PER_CYCLE} edits per cycle. Fewer, sharper edits beat many.
- Each edit is an exact (old_string, new_string) replacement. old_string must \
appear VERBATIM and EXACTLY ONCE in the target file (including whitespace/indentation) \
— copy it character-for-character from the file content you were given.
- Never touch files outside the allowlist. Never propose edits to tests, benchmarks, \
or anything under selfmod/.
- Ground every edit in something specific from the trace report or the lineage \
history — state the hypothesis ("this should reduce X because Y") in `rationale`.
- Prefer the smallest change that tests the hypothesis: a tuned constant, a sentence \
added to a system prompt, a tightened instruction — not a rewrite of a whole function.
- If you see nothing worth changing, return an empty edits list rather than inventing \
busywork.

Respond with ONLY a single JSON object, no prose before or after, no markdown fence:
{{"summary": "<one sentence>", "edits": [{{"file": "...", "rationale": "...", \
"old_string": "...", "new_string": "..."}}]}}
"""


def _build_agent(harness: HarnessSpec) -> Agent:
    return Agent(name=f"self_improvement_planner_{harness.name}",
                 system_prompt=_system_prompt(harness), thinking_budget="max")


def _extract_json(text: str) -> dict | None:
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if not brace:
            return None
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            return None


def propose_plan(
    harness: HarnessSpec, report_text: str, allowed_file_contents: dict[str, str], lineage_history_text: str,
) -> SelfEditPlan:
    file_sections = "\n\n".join(
        f"### {path}\n```python\n{content}\n```" for path, content in allowed_file_contents.items()
    )
    prompt = (
        f"## Trace report (real production episodes, domain={harness.cortex_domain})\n{report_text}\n\n"
        f"## Lineage history (prior self-improvement cycles for this harness)\n{lineage_history_text}\n\n"
        f"## Current source of editable files\n{file_sections}\n\n"
        "Propose this cycle's edit plan."
    )

    agent = _build_agent(harness)
    result = agent.run(prompt)

    if result.dry_run:
        return SelfEditPlan(summary="skipped: dry-run (no ANTHROPIC_API_KEY)", edits=[], parse_error="dry_run")

    data = _extract_json(result.text)
    if data is None:
        return SelfEditPlan(summary="skipped: planner response was not valid JSON", edits=[],
                             parse_error="unparseable_response")

    raw_edits = data.get("edits", [])[:MAX_EDITS_PER_CYCLE]
    edits: list[ProposedEdit] = []
    for e in raw_edits:
        try:
            file, rationale, old, new = e["file"], e["rationale"], e["old_string"], e["new_string"]
        except (KeyError, TypeError):
            continue
        if file not in harness.allowed_files:
            continue
        if not old.strip() or len(old) > MAX_EDIT_CHARS or len(new) > MAX_EDIT_CHARS:
            continue
        edits.append(ProposedEdit(file=file, rationale=rationale, old_string=old, new_string=new))

    return SelfEditPlan(summary=data.get("summary", ""), edits=edits)
