# Spec 4 — End-to-End Research Agent (walkthrough + definition of done)

Status: **built and live-tested end to end**, against a local Ollama
`qwen3:14b` + `RETRIEVER=duckduckgo` — real web research, a real Grader
pass, a real Cortex write-back. Spec 5 (RSI) is still a later phase.

## 1. Entry point

```
python cli.py --research "In what year was the Eiffel Tower completed?" \
  --scope default --workspace-dir ./workspace --cortex-dir ./cortex_data
```

Same CLI shape as the original plan.

## 2. Full worked trace

```
1. EpisodeSession created (agents/research/session.py — built):
   episode_id, workspace dir, checkpoint log.
2. cortex.retrieve(question) → memory_context.
3. agents/research/qwen_config.configure_qwen() (built, Spec 1) sets
   FAST_LLM/SMART_LLM/STRATEGIC_LLM + DASHSCOPE_API_KEY or
   VLLM_OPENAI_API_KEY/BASE from our own QWEN_* env vars, so the vendored
   tree calls Qwen (confirmed live against Ollama) underneath.
4. Instantiate vendored GPTResearcher(query=question, ...), with
   memory_context folded into the query/context per Spec 3 §1.
5. await researcher.conduct_research()
     - internally: agent_creator persona → query_processing sub-questions →
       per-sub-question researcher.py + browser.py + context_manager.py
       (Jev/BM25 filtering) → curator.py source curation.
     - checkpoint() after this call returns (crash-recovery boundary).
6. await researcher.write_report() → draft.
     - checkpoint() again.
7. Reflection stage (agents/research/reflection.py, ours, not vendored —
   calls GenericLLMProvider directly, reusing whatever configure_qwen() set):
     grade(question, draft) → verdict + mistakes
     while verdict != pass and revisions < MAX_REVISIONS:
       revise(draft, mistakes) re-invokes the model with critique folded in
       grade(...) again
       checkpoint() each round
8. reflect(...) → abstracted_pattern / failure_summary / distilled_learnings.
9. Episode(domain="research", ...) built, cortex.write_back(...).
10. CLI prints: Outcome, Revisions, Cost, then the final report text.
```

## 3. Definition of done for phase 4 — all confirmed live

Real run: `QWEN_API_KEY=ollama QWEN_BASE_URL=http://localhost:11434/v1
QWEN_MODEL=qwen3:14b RETRIEVER=duckduckgo python cli.py --research "What is
the boiling point of water in Celsius at sea level?"`.

- [x] Runs with zero Anthropic dependency anywhere in the call path.
- [x] Vendored GPT Researcher actually performs real web research.
- [x] Produces a final report with citations traceable to real sources
      (~900 words, multiple cited sources, a comparative table).
- [x] Our own Reflection stage runs on top of the vendored output and
      produces a verdict + Cortex write-back fields — confirmed: outcome
      `success`, `abstracted_pattern="Direct retrieval of a well-established
      scientific fact"`, two `distilled_learnings` bullets.
- [x] Writes exactly one `Episode` into Cortex with `domain="research"` —
      confirmed via `python cli.py --stats` (`recall_count: 1,
      intuition_count: 1`).
- [x] Does not crash — ran to completion (took several minutes on a local
      14B model; several sequential Qwen calls, not a budget/hang issue).

Independent of a live key: `--research` with no `QWEN_API_KEY` set runs the
full control flow (Cortex retrieve, dry-run draft, Grader/Reviser loop
skipped cleanly, Reflection, Cortex write-back) without raising, confirmed.
Outcome in dry-run is always `failure` (no real grading happens, so
`verdict_value` never reaches `"pass"`) — weaker than the old hand-rolled
design's dry-run coverage, as anticipated; accepted as-is rather than
building a GPT-Researcher-side dry-run mode.

**New known limitation, found during the live run** (not anticipated in
this spec originally): `Episode.cost_actual` only captures our own
Grader/Reviser/Reflection token usage, not GPT Researcher's internal
research/writing calls — see docs/03_integration_spec.md §2 for why
(`get_costs()` returns a dollar estimate, not tokens, and is a meaningless
unit for a local Ollama model anyway). Left unresolved; cost is undercounted.

## 4. Explicitly out of scope for phase 4

- The RSI engine (Spec 5) — task-level and harnessing-level recursion both
  come after a working non-self-improving version exists.
- Parallel multi-task fan-out beyond whatever GPT Researcher already does
  internally.
- Resume-from-checkpoint (log is written; resume code isn't).
- Porting the original Anthropic-based coding harness (`agents/`,
  `pipeline.py`) onto this pattern — left as a separate, untouched demo.
- Vendoring/using GPT Researcher's optional `multi_agents/` LangGraph
  variant, or its MCP/local-document/image-generation features.

## 5. Suggested build order within phase 4

1. ~~Vendor GPT Researcher~~ — **done**: `agents/research/gpt_researcher/`, `VENDOR.md` written.
2. ~~`qwen_config.py`, confirm a real Qwen call works standalone~~ — **done**,
   live-tested against Ollama, including a full `conduct_research()` +
   `write_report()` run.
3. ~~`agents/research/session.py`~~ — **done**.
4. ~~`agents/research/reflection.py`~~ — **done**, calls
   `GenericLLMProvider` directly rather than a new client wrapper.
5. ~~Wire Cortex retrieve/write-back~~ — **done**, `research_pipeline.py`.
6. ~~CLI integration, dry-run check, live smoke test~~ — **done**, all of
   §3's definition-of-done checked live.

## 6. What stays untouched through all of this

`cortex/` (zero changes, per Spec 2), the coding pipeline (`agents/base.py`,
`agents/pipeline_agents.py`, `pipeline.py`, still on Claude, not migrated),
and the CLI's `--stats` flag shape.
