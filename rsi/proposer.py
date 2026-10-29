"""Proposer -- both RSI tiers' edit-proposal logic (docs/05_rsi_harness2_design_spec.md
S3/S4). Harnessing-level reads a Cortex trace report; task-level reads the
current episode's Grader mistake list. Same JSON contract either way,
Qwen-backed via GenericLLMProvider directly (same pattern as
agents/research/reflection.py) instead of the coding harness's
agents.base.Agent (Claude-only) -- selfmod.meta_agent's Claude dependency is
exactly why this is a separate module, not a shared one (see docs/05 S0).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import agents.research  # noqa: F401 -- side effect: puts gpt_researcher on sys.path
from gpt_researcher.llm_provider.generic import GenericLLMProvider

from .component_tree import ALLOWED_FILES, COMPONENT_TREE

MAX_EDITS_PER_CYCLE = 3
MAX_EDIT_CHARS = 4000

_RULES = f"""Rules:
- Propose at most {MAX_EDITS_PER_CYCLE} edits. Fewer, sharper edits beat many.
- Each edit is an exact (old_string, new_string) replacement. old_string must \
appear VERBATIM and EXACTLY ONCE in the target file (including whitespace/indentation).
- You may ONLY propose edits to files in the allowlist given below.
- Ground every edit in something specific from the report/trajectory you were given \
-- state the hypothesis in `rationale`.
- Prefer the smallest change that tests the hypothesis: a tuned constant, a sentence \
added to a prompt -- not a rewrite of a whole function.
- If nothing is worth changing, return an empty edits list.

Respond with ONLY a single JSON object, no prose, no markdown fence:
{{"summary": "<one sentence>", "edits": [{{"file": "...", "rationale": "...", \
"old_string": "...", "new_string": "..."}}]}}
"""

HARNESSING_SYSTEM_PROMPT = (
    "You are the Harnessing-level Proposer for a deep-research agent harness "
    "(GPT Researcher, Qwen-backed). You read a trace report of its recent "
    "real-world performance across many episodes and propose small, targeted "
    "edits to improve it going forward.\n\n" + _RULES
)

TASK_SYSTEM_PROMPT = (
    "You are the Task-level Proposer for a deep-research agent harness. A single "
    "episode's Grader keeps finding the same category of mistake across revision "
    "rounds. Propose a small edit, scoped to fixing that one mistake pattern for "
    "the rest of THIS episode -- not a general improvement.\n\n" + _RULES
)


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


def _build_plan(text: str) -> SelfEditPlan:
    data = _extract_json(text)
    if data is None:
        return SelfEditPlan(summary="skipped: planner response was not valid JSON",
                             edits=[], parse_error="unparseable_response")
    raw_edits = data.get("edits", [])[:MAX_EDITS_PER_CYCLE]
    edits: list[ProposedEdit] = []
    for e in raw_edits:
        try:
            file, rationale, old, new = e["file"], e["rationale"], e["old_string"], e["new_string"]
        except (KeyError, TypeError):
            continue
        if file not in ALLOWED_FILES:
            continue
        if not old.strip() or len(old) > MAX_EDIT_CHARS or len(new) > MAX_EDIT_CHARS:
            continue
        edits.append(ProposedEdit(file=file, rationale=rationale, old_string=old, new_string=new))
    return SelfEditPlan(summary=data.get("summary", ""), edits=edits)


async def _call(system: str, user: str, tier: str = "STRATEGIC_LLM") -> str:
    llm_str = os.environ.get(tier)
    if not llm_str:
        return ""
    provider, model = llm_str.split(":", 1)
    llm = GenericLLMProvider.from_provider(provider, model=model, temperature=0.3, verbose=False)
    return await llm.get_chat_response(
        [{"role": "system", "content": system}, {"role": "user", "content": user}], stream=False,
    )


MAX_FILE_CHARS = 1200  # see docs/05 S6 Q4 -- binary-searched live against this project's
# actual local Ollama/qwen3:14b setup: ~8KB total prompt produces valid JSON, ~20KB
# produces a coherent but wrong-format free-form essay instead (not garbling -- the model
# is on-topic, just drops the JSON-only instruction). That gap points at Ollama's default
# ~4096-token context window for this model (qwen3 natively supports far more; this is a
# serving-default limitation, not a model-capability one) -- see docs/01_harness_spec.md
# S6 Q4 for how to raise it (OLLAMA_CONTEXT_LENGTH or a custom Modelfile num_ctx). Until
# that's done, keep our own prompt small enough to reliably fit under the default.
# Truncation here is safe: apply_edits() validates old_string against the REAL, untruncated
# file at apply time, so a model proposing an edit against content it couldn't see just
# gets a clean "old_string occurs 0 times" rejection, never a silently-wrong edit.


def _render_component_files(repo_root: Path, files: list[str]) -> str:
    sections = []
    for rel_path in files:
        content = (repo_root / rel_path).read_text()
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS] + f"\n# ... TRUNCATED at {MAX_FILE_CHARS} chars ..."
        sections.append(f"### {rel_path}\n```python\n{content}\n```")
    return "\n\n".join(sections)


async def propose_from_report(repo_root: Path, report_text: str, lineage_history_text: str) -> SelfEditPlan:
    """Harnessing-level: cross-episode Cortex trace report -> candidate edit."""
    file_sections = _render_component_files(repo_root, ALLOWED_FILES)
    prompt = (
        f"## Trace report (real production episodes, domain=research)\n{report_text}\n\n"
        f"## Lineage history (prior self-improvement cycles)\n{lineage_history_text}\n\n"
        f"## Allowlisted files you may edit\n{', '.join(ALLOWED_FILES)}\n\n"
        f"## Current source\n{file_sections}\n\nPropose this cycle's edit plan."
    )
    text = await _call(HARNESSING_SYSTEM_PROMPT, prompt)
    if not text:
        return SelfEditPlan(summary="skipped: dry-run (no QWEN_API_KEY)", edits=[], parse_error="dry_run")
    return _build_plan(text)


async def propose_from_trajectory(repo_root: Path, mistakes: list[str], component_id: str = "c1") -> SelfEditPlan:
    """Task-level: this episode's repeated Grader mistakes -> candidate edit,
    scoped by default to c1 (system_prompt) since a repeated mistake category
    is most often a missing/weak instruction, not a tool or orchestration bug.
    """
    component = next((c for c in COMPONENT_TREE if c.id == component_id), COMPONENT_TREE[0])
    file_sections = _render_component_files(repo_root, component.files)
    mistakes_text = "\n".join(f"- {m}" for m in mistakes)
    prompt = (
        f"## Repeated mistakes this episode\n{mistakes_text}\n\n"
        f"## Allowlisted files you may edit\n{', '.join(component.files)}\n\n"
        f"## Current source\n{file_sections}\n\nPropose a scoped fix for this episode."
    )
    text = await _call(TASK_SYSTEM_PROMPT, prompt)
    if not text:
        return SelfEditPlan(summary="skipped: dry-run (no QWEN_API_KEY)", edits=[], parse_error="dry_run")
    return _build_plan(text)
