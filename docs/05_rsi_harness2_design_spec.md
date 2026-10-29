# Spec 5 — RSI Engine: Harness² Design Adoption (not a dependency)

Status: **harnessing-level tier built and mechanics-tested** (`rsi/`,
wired into `cli.py --self-improve --harness research`). **Task-level tier
is an explicit, documented stub** — see S6 open question 1; building it for
real needs real mistake-pattern data this project doesn't have enough of
yet (one real episode so far, zero revisions). A policy layer
(`agents/research/policies.py`, Omnigent-inspired) was added alongside
this as the fixed, never-RSI-edited safety boundary — see
docs/01_harness_spec.md S5.

**Superseded in one respect, while building this generally for other
projects/the public**: S0 and S4 below say `selfmod/` stays separate from
`rsi/` "not a shared module." That held while this engine only served
self_healing_ai's own two harnesses; it no longer does. `selfmod/` and
`rsi/` are now unified into one generic engine living in `rsi/`
(`HarnessSpec` + an injected `llm_call`, see `rsi/harness_spec.py` and
`rsi/llm_adapters.py`) — the coding harness is just another `HarnessSpec`
now, Claude-backed via `claude_llm_call()`, rather than a separate
`selfmod/meta_agent.py` implementation. The reasoning below for why they
were separate is left as-is, as the historical record of why that was the
right call *at the time* — it stopped being the right call once a third
consumer (anyone doing `pip install self-healing-ai`) became the actual
design target, not a hypothetical.

## 0. What "design adoption" means here, precisely

We do **not** depend on the `harness2` Python package. It's Python 3.12/`uv`
-only, its Propose-Probe-Compose orchestration models (proposer/judge/
composer) are wired to Vertex AI (`harness2/config.py`'s
`GOOGLE_CLOUD_PROJECT`), and it's built around three enterprise/legal/office
benchmarks with their own task/judge format — none of that fits a
Qwen-only, no-new-cloud-dependency project. What we take is the *shape* of
its design, reimplemented as our own code against our own vendored harness
(Spec 1):

- The **Propose → Probe → Compose** step name and structure.
- The **8-component editable surface** (c1–c8), re-mapped onto
  `agents/research/gpt_researcher/` (Spec 1 §3) instead of OpenCode/Codex.
- The **task-level vs. harnessing-level recursion** split — this is the one
  genuinely new idea vs. our original `selfmod` design (which only had a
  harnessing-level, benchmark-gated tier).

This replaces the original `selfmod/meta_agent.py` + `selfmod/executor.py`
design (still functioning today for the coding harness) with a restructured
engine, renamed `rsi/` to signal the Harness²-aligned design, applied to the
research harness. The coding harness's existing `selfmod/` machinery is left
as-is (Spec 4 §4) — not migrated in this phase.

## 1. The 8-component mapping (c1–c8 → `agents/research/gpt_researcher/`)

Checked against the actual package layout (Spec 1 §3), with honest gaps
flagged rather than forced:

| Harness² component | GPT Researcher location | Fit |
|---|---|---|
| c1 System prompt | `prompts.py`, `actions/agent_creator.py` (dynamic persona) | Strong |
| c2 Guardrails | Nothing dedicated exists; treat as a *new* small section we add inside `prompts.py` (e.g. explicit "every claim needs a source" instruction) rather than something already separable | Weak — we're adding this component, not finding it |
| c3 Memory | **Not inside the vendored tree at all** — this is Cortex (Spec 2 §5a) | N/A by design |
| c4 Skills | GPT Researcher's own `skills/` directory is role *implementations* (closer to c6), not Harness²-style invokable skill files | Weak — naming collision, not a real match; don't force one |
| c5 Tool guidance / specs | `retrievers/`, `actions/retriever.py`, `actions/web_scraping.py`, `config/variables` retriever settings | Strong |
| c6 Subagents | `skills/researcher.py`, `skills/writer.py`, `skills/curator.py`, `agent.py`'s orchestration of them | Strong |
| c7 Scripts | `actions/query_processing.py`, `actions/report_generation.py`, `actions/markdown_processing.py` | Strong |
| c8 Plugins / middleware | `mcp/`, `document/`, `vector_store/` (all optional, unused in v1 per Spec 1 §5 open question 3) | Strong, but inert until those features are turned on |

Two components (c2, c4) don't actually pre-exist in GPT Researcher — they're
places we're introducing structure that Harness²'s taxonomy calls for but
GPT Researcher's own design doesn't have. Worth tracking honestly rather
than pretending the mapping is cleaner than it is; if c2/c4 edits turn out
not to matter in practice, that's fine — the editable allowlist can shrink.

## 2. Component tree spec — `rsi/component_tree.py`

Analogous to Harness²'s `surface() -> SurfaceSpec`: a static mapping from
component id to the actual file(s) + a short description, used both to build
the allowlist and to generate the Proposer's prompt sections.

```python
@dataclass(frozen=True)
class Component:
    id: str              # "c1".."c8"
    name: str
    files: list[str]      # repo-relative paths under agents/research/gpt_researcher/
    description: str

COMPONENT_TREE: list[Component] = [
    Component("c1", "system_prompt", ["agents/research/gpt_researcher/prompts.py",
                                       "agents/research/gpt_researcher/actions/agent_creator.py"], ...),
    Component("c5", "tool_guidance", ["agents/research/gpt_researcher/actions/retriever.py",
                                       "agents/research/gpt_researcher/actions/web_scraping.py"], ...),
    Component("c6", "subagents", ["agents/research/gpt_researcher/skills/researcher.py",
                                   "agents/research/gpt_researcher/skills/writer.py",
                                   "agents/research/gpt_researcher/skills/curator.py"], ...),
    Component("c7", "scripts", ["agents/research/gpt_researcher/actions/query_processing.py",
                                 "agents/research/gpt_researcher/actions/report_generation.py"], ...),
    # c2, c3, c4, c8 — see §1; c2 may point at a new file we create ourselves
    # directly in agents/research/ (ours), not inside agents/research/gpt_researcher/
    # (vendored), since there's nothing to point at yet.
]
```

This directly generalizes `selfmod.harness_spec.HarnessSpec.allowed_files`
(today, a flat list) into a structured, named tree — same enforcement role
(the executor/Probe still requires `old_string` to match exactly once, same
as today), just with Harness²'s taxonomy as the organizing structure instead
of an unstructured list.

## 3. Task-level recursion — Propose / Probe / Compose, per episode

Fires **during** an episode, when the Grader/Reviser loop (Spec 3 §3) is
making repeated, same-category mistakes — not on every episode, and not
needing ground truth:

```
Propose:  rsi/proposer.py — given the current episode's trajectory so far
          (the Grader's mistake list across revision rounds) and the
          relevant component(s) (e.g. c1 system_prompt, c2 guardrails),
          propose a small candidate edit. Same old_string/new_string
          contract as today's selfmod.meta_agent, scoped to this task.

Probe:    rsi/probe.py — re-run the SAME failing stage (e.g. just
          write_report() + Grader, not the whole research phase) with the
          candidate edit applied in an isolated copy, and with the
          unedited harness, side by side. Compare trajectories: does the
          candidate's Grader output show fewer/different mistakes than the
          baseline's, for this same task? This is "contrastive... without
          ground-truth feedback" — exactly Harness²'s framing — because we
          don't need the keyword-grounded benchmark here; we're comparing
          two attempts at the identical task, not scoring absolute
          correctness.

Compose:  rsi/composer.py — if the candidate's trajectory is contrastively
          better, adopt it for the REST of this episode's revision loop
          (not yet promoted to the lineage branch — that only happens at
          harnessing-level, §4, after this edit has evidence from more than
          one task).
```

This tier is new relative to the original `selfmod` design and is the main
thing actually worth adopting from Harness² — it lets the harness adapt
*mid-task* to a stuck pattern, rather than only ever improving between runs.

## 4. Harnessing-level recursion — same role as today's `selfmod`, renamed

```
After N episodes with a task-level-adopted edit showing up repeatedly (or
directly proposed without a task-level trigger, same as today):
  rsi/proposer.py reads tracer.build_report(domain="research") — same
    Cortex-backed trace aggregation as today's selfmod.tracer, unchanged.
  rsi/probe.py (harnessing-level mode) — this IS today's benchmark-gated
    executor: apply the edit in a git worktree on the research lineage
    branch, run the ground-truth benchmark (ground truth kept deliberately,
    per Spec 3 §4 and the earlier design discussion, even though Harness²
    itself doesn't require one), compare scalar scores.
  rsi/composer.py (harnessing-level mode) — accept (fast-forward lineage
    branch) or reject, exactly as today's executor.run_cycle does.
```

So harnessing-level recursion is **not new engineering** — it's today's
`selfmod/executor.py` + `selfmod/meta_agent.py`, renamed to match Harness²'s
vocabulary and pointed at the component tree (§2) instead of a flat file
list. The genuinely new piece is purely the task-level tier (§3) sitting in
front of it.

## 5. File layout — built

```
rsi/
  component_tree.py   # §2 — the c1..c8 -> file mapping. Built.
  proposer.py          # propose_from_report() (harnessing) and
                         # propose_from_trajectory() (task-level) -- both
                         # work standalone; Qwen-backed via GenericLLMProvider
                         # directly (same pattern as agents/research/reflection.py),
                         # not selfmod.meta_agent's Claude-only Agent. Built.
  probe.py              # harnessing_probe() (git worktree + benchmark gate,
                         # ported from selfmod/executor.py) -- built, mechanics
                         # tested. task_probe_not_implemented() -- deliberate
                         # stub, see S6 Q1; raises rather than fabricating a result.
  composer.py           # run_cycle() -- harnessing-level only. Owns
                         # rsi_data/generations.jsonl + the rsi/lineage-research
                         # branch, exact same propose-only safety model as
                         # selfmod/executor.py (never touches main). Built.
  research_benchmark.py # ground-truth-graded, shells out to the real
                         # cli.py --research (Specs 3-4's build), not a stub. Built.
```

Wired into `cli.py --self-improve --harness research` (async, since
`propose_from_report` is a coroutine). **Update, see the status note at
the top of this doc**: `selfmod/` was later retired and unified into this
same `rsi/` package once the engine needed to serve arbitrary third-party
consumers, not just this repo's own two harnesses — `cli.py
--self-improve --harness coding` now goes through the identical
`rsi.run_cycle()` too.

## 6. Open questions

1. What trajectory-contrast judge logic actually decides "candidate's
   mistakes are fewer/better than baseline's" for task-level Probe — **still
   open**. `rsi/probe.py`'s `task_probe_not_implemented()` is an explicit
   stub, not a placeholder that fabricates a result: a real version needs to
   re-run `write_report()` with a candidate c1 edit actually active in the
   live vendored `prompts.py`, then grade that new draft and compare against
   a baseline re-run — which means mutating a live vendored file mid-episode
   and reverting it safely, a mechanism this project hasn't designed yet.
   `propose_from_trajectory()` (the Propose half) works standalone and is
   tested; nothing decides accept/reject on what it proposes yet.
2. Threshold for promoting a task-level-adopted edit into a harnessing-level
   proposal — e.g. "seen helping in 3+ episodes" mirrors Replay's existing
   `promote_threshold=3` pattern (Spec 2 §2) and may be reusable as-is.
3. Whether c2 (guardrails) and c4 (skills) end up mattering enough to keep
   as distinct components once real usage data exists, or whether they
   should be dropped/merged into c1 and c6 respectively (per the honest
   "weak fit" flags in §1).
