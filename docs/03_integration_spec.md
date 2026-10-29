# Spec 3 — Integrating the Harness with Cortex (and the RSI engine)

Status: **built and live-tested end to end** against a local Ollama
`qwen3:14b` — `research_pipeline.py`, `agents/research/session.py`,
`agents/research/reflection.py`. Cortex (Spec 2) needed zero changes, as
predicted. Spec 5 (RSI engine) is still just a design.

## 1. Episode start — retrieval hook

```
question arrives (CLI / cron / future caller)
  → cortex.retrieve(store, graph, question, scope=<scope>)
  → RetrievalContext.to_prompt_text()
  → folded into the query/context GPTResearcher receives
    (GPT Researcher's agent_creator.py persona step and
    query_processing.py's sub-question generation are the two places this
    plausibly needs to land — confirm exact injection point when
    implementing Spec 4)
```

Same intent as the original spec: prior Cortex memory should be able to
shortcut or steer what GPT Researcher decides to investigate, not just be
appended as unused context.

## 2. During the episode — trace capture

| Accumulator | Written by | Read by |
|---|---|---|
| Episode's `action_arc` | our `agents/research/session.py` wrapper, logging each GPT Researcher call (conduct_research, write_report) plus our own Reflection stage | Cortex at write-back; `selfmod.tracer` later |
| GPT Researcher's own internal trace/sources | vendored tree, not persisted by us beyond what feeds the final report's citations | Reflection stage (reads it to judge citation quality) |
| `CostActual` | our own Grader/Reviser/Reflection calls via `GenericLLMProvider.last_usage_metadata` | `Episode.cost_actual`; RSI benchmark parsing |

No Notebook/scratchpad module is needed (per Spec 1 §1) — GPT Researcher's
own context-filtering pipeline already does the within-run distillation job
that module would have done.

**Known limitation, confirmed live**: `CostActual` only captures our own
Grader/Reviser/Reflection calls, not GPT Researcher's internal
conduct_research()/write_report() token usage. `GPTResearcher.get_costs()`
exists but returns an estimated *dollar* cost, not token counts — a unit
mismatch with `CostActual`'s token fields, and a meaningless unit anyway
for a local Ollama model with no per-token price. Left unresolved rather
than forcing a bad fit; `Episode.cost_actual` undercounts total spend for
now.

## 3. Episode end — write-back hook

```
GPTResearcher.write_report() → draft
  → Reflection stage's Grader step: verdict + mistakes (ours, §4 of Spec 1)
  → if revise: Reviser re-invokes write_report() with critique folded in,
    up to MAX_REVISIONS — loop with Grader
  → Reflection stage's output: abstracted_pattern / failure_summary /
    distilled_learnings
  → Episode(domain="research", ...) constructed
  → cortex.write_back(store, graph, episode, retrieved=retrieved)
  → graph.save()
```

Identical shape to the original design's write-back hook — only the thing
producing the draft (vendored GPT Researcher vs. a hand-rolled Synthesizer)
changed.

## 4. The RSI hook — now a two-tier design, see Spec 5

This is the part that changes most from the original plan. Previously:
`selfmod` proposed edits, gated purely by a fixed benchmark suite
(harnessing-level only). Adopting Harness²'s design means two tiers:

- **Task-level** (new): while a single episode is still running, if the
  Grader/Reviser loop is repeatedly failing on the same class of mistake,
  a Propose-Probe-Compose step can try a small harness edit *for this task*
  and judge it by trajectory contrast (does the revised attempt show fewer
  of the same mistake?) — no ground truth needed, no full benchmark re-run.
- **Harnessing-level** (same role the original `selfmod` played): after
  enough episodes, promote evidence-supported edits into the persistent
  lineage, gated by the existing ground-truth benchmark (Spec 5 §4) — this
  is still benchmark-gated, for the same reason named back when ground-truth
  grading was chosen over Harness²'s no-answer-key approach: a stronger,
  falsifiable signal, kept deliberately even though Harness² itself doesn't
  require one.

See Spec 5 for the full design; this section exists only to mark where in
the episode lifecycle each tier's hook fires.

## 5. What this spec still does not cover

Actually building any of this — vendoring GPT Researcher (done, Spec 1),
writing `agents/research/session.py` and `agents/research/reflection.py`,
wiring the two-tier RSI
engine — is implementation work that comes after Spec 4's walkthrough is
agreed and, likely, after a first working non-self-improving version exists
to even have traces worth learning from.
