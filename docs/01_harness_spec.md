# Spec 1 — Base Harness: vendored GPT Researcher, Qwen-configured

Status: **built and smoke-tested** (vendoring + Qwen config; Cortex/session/
reflection wiring is still Specs 3-4). Supersedes the earlier from-scratch
harness design (providers/tools/loop/notebook built by hand) — dropped in
favor of adopting GPT Researcher as the base harness, vendored rather than
treated as an opaque pip dependency.

Lives under `agents/research/` — a sibling of `agents/base.py` /
`agents/pipeline_agents.py` (the coding harness), not a separate top-level
folder. `agents/` is the parent namespace for every harness this project
has; each harness gets its own subfolder.

## 0. Why vendor instead of `pip install gpt-researcher`

The RSI engine (Spec 5) needs to read and propose edits to the harness's
actual source — prompts, stage logic, tool/retriever config. A pip-installed
package sitting in `site-packages` is not something our RSI loop can safely
diff, edit, and benchmark-gate inside this repo's git history. So:
GPT Researcher's source gets copied into this repo at a pinned commit,
tracked in our own git history from that point forward, same as any other
file selfmod/RSI is allowed to touch.

```
agents/
  research/
    gpt_researcher/          # vendored source tree (see §3)
    VENDOR.md                 # source repo, commit SHA, date vendored,
                                # Apache 2.0 license notice, and any diff
                                # applied on top of upstream at vendor time
```

No separate `vendor/` wrapper directory — `agents/research/` already is the
harness boundary, and `gpt_researcher/`'s own name already marks it as the
vendored package. A nesting level that exists only to re-say "this is
third-party" when the directory name already says so isn't earning its
keep.

GPT Researcher is Apache 2.0 — vendoring and modifying it is permitted;
`VENDOR.md` exists so upstream attribution and license terms travel with the
copy, and so future `git log agents/research/gpt_researcher/` shows
our edits distinctly from "what upstream shipped."

## 1. Confirmed facts (checked against the actual repo and verified live, not
secondhand)

- Apache 2.0, Python 3.12+, pip-installable, and usable as a plain library:
  `from gpt_researcher import GPTResearcher; r = GPTResearcher(query=...); 
  await r.conduct_research(); report = await r.write_report()`.
- **Qwen support confirmed, and better than the README's generic
  `OPENAI_BASE_URL` mention suggested**: GPT Researcher's
  `llm_provider/generic/base.py` has a native `"dashscope"` provider branch
  (Alibaba Cloud's hosted Qwen API, reads `DASHSCOPE_API_KEY`) and a
  `"vllm_openai"` branch (any self-hosted OpenAI-compatible endpoint —
  confirmed working against a local **Ollama** server, which is what this
  project actually uses: `QWEN_BASE_URL=http://localhost:11434/v1`).
  `agents/research/qwen_config.py` auto-selects between the two.
- Model selection is `FAST_LLM`/`SMART_LLM`/`STRATEGIC_LLM` env vars in
  `"<provider>:<model>"` format (confirmed in `config/config.py`,
  `llm_str.split(":", 1)`).
- Retrievers are pluggable via `RETRIEVER=<name>` — defaults to Tavily
  (needs a key); **`RETRIEVER=duckduckgo`** (via the `ddgs` package) needs
  no key and is confirmed working for dev/benchmark use.
- Built-in context filtering ("Jev," falls back to free local BM25 keyword
  ranking with zero API key/embeddings needed) — GPT Researcher's own
  answer to context management. No hand-rolled truncation or
  notebook/scratchpad module needed.
- Recursive deep-research mode exists natively (tree-shaped, configurable
  breadth/depth, concurrent sub-branches) — already "recursive research
  loop" behavior; nothing to add there.
- MCP client support, local document research (`DOC_PATH`) — optional, not
  used for v1.
- **No self-critique/revision loop, and no cross-session memory.** GPT
  Researcher goes planner → crawler/researcher agents → writer/publisher,
  once, with no "grade the draft, revise on criticism" step, and no
  persistence across separate `GPTResearcher(...)` invocations. Both are
  gaps **we fill ourselves**, not inside the vendored tree — see §4 and
  Spec 3.

### Live verification performed

- `agents/research/qwen_config.configure_qwen()` tested directly against
  GPT Researcher's real `Config` class for all three paths: DashScope mode,
  self-hosted/Ollama mode, and the no-key `"dry_run"` signal.
- A real, non-trivial `conduct_research()` + `write_report()` call against
  a locally-running **Ollama `qwen3:14b`** model with `RETRIEVER=duckduckgo`
  produced a correctly-cited, multi-section research report end to end.
- Existing `cortex/` test suite still passes after the dependency changes
  this pulled in.

## 2. What GPT Researcher does NOT give us (confirm before assuming otherwise)

- No Grader/Reflection step — nothing produces a structured "what went wrong"
  signal. Needed for "learn from failures," per the project's original goal.
- No cross-episode memory — `memory/embeddings.py` inside the vendored tree
  is an embedding provider for *within-run* context similarity, not
  persistent memory across separate research tasks. Cortex (Spec 2) is the
  only cross-episode memory in this system; nothing inside
  `agents/research/gpt_researcher/` should be mistaken for it.
- No episode/session lifecycle (checkpointing, steering) — if we still want
  that for long sessions, it's a thin wrapper we write ourselves around the
  `GPTResearcher` calls, not inside the vendored tree.

## 3. GPT Researcher's actual package layout (confirmed via GitHub, for the
component-taxonomy mapping in Spec 5)

```
agents/research/gpt_researcher/
  __init__.py
  agent.py            # GPTResearcher class — top-level orchestration
  prompts.py          # prompt templates — the single most important file for RSI
  config/
    config.py           # Config class — model strings, retriever, context-filter mode
    variables/           # default values (breadth/depth, thresholds, etc.)
  skills/
    researcher.py        # the "investigate a sub-question" role
    writer.py            # the "produce the report" role
    curator.py           # source curation/quality filtering
    deep_research.py     # the recursive tree-depth/breadth orchestration
    context_manager.py   # Jev/BM25 relevance filtering
    browser.py            # page fetching
    image_generator.py    # optional, not used
  actions/
    query_processing.py   # sub-question generation logic
    report_generation.py  # report-writing logic
    retriever.py           # retriever dispatch
    web_scraping.py         # scraping mechanics
    markdown_processing.py  # formatting
    agent_creator.py         # builds a task-specific "persona" per query
  llm_provider/
    generic/              # the actual model-calling layer (dashscope/vllm_openai live here)
  retrievers/              # search backend implementations (incl. duckduckgo/)
  memory/embeddings.py     # within-run embedding similarity, NOT cross-episode memory
  context/                 # supporting context-filter code
  document/                # local document loading (PDF/CSV/Word/etc.)
  mcp/                      # MCP client integration
  vector_store/             # optional vector-store backend for context filtering
```

**Fixed, never-RSI-edited boundary** (same role `agents/base.py` plays for
the coding harness): `llm_provider/`, `retrievers/` mechanics, `scraper`/
`browser.py`'s actual fetch code, `vector_store/`, `mcp/`. These are
infrastructure RSI will never touch — no legibility argument requires
hand-rolling or restricting edits to plumbing nothing will ever propose a
change to.

**RSI-editable surface**: `prompts.py`, `skills/*.py`'s role logic (not the
underlying fetch/retrieval calls they make, but how they use their results),
`actions/query_processing.py`, `actions/report_generation.py`,
`actions/agent_creator.py`, and the tunable values in `config/variables/`
(breadth, depth, thresholds). Exact file list finalized in Spec 5 §2's
component-taxonomy table.

## 4. What we build ourselves, around the vendored tree

```
agents/research/
  __init__.py          # puts this dir on sys.path so `import gpt_researcher`
                         # works without callers knowing where it lives
  qwen_config.py        # built — sets FAST_LLM/SMART_LLM/STRATEGIC_LLM +
                          # the matching provider API key/base from our own
                          # QWEN_* env vars
  session.py            # not yet built — EpisodeSession: episode_id,
                          # workspace dir, checkpoint log, steer-file check
                          # (Spec 1 §5's original design, now wrapping
                          # GPTResearcher calls instead of a hand-rolled loop)
  reflection.py          # not yet built — Grader + Reflection stage: takes
                          # GPT Researcher's draft report, produces (a) a
                          # revise/pass verdict + mistakes list, and (b)
                          # abstracted_pattern/failure_summary/
                          # distilled_learnings for Cortex write-back
  gpt_researcher/        # vendored, see §0
  VENDOR.md
```

`reflection.py`'s Grader/Reviser loop is NOT vendored — it's ours, because
GPT Researcher has no revision mechanism to begin with (confirmed §1). If a
revision is needed, the Reviser re-invokes the vendored
`GPTResearcher.write_report()` (or a narrower `skills/writer.py` call) with
the critique folded into the prompt, rather than re-running the entire
research phase — cheaper, and correctness fixes at the writing stage don't
need new web research.

## 5. Policy layer — `agents/research/policies.py` (built)

Borrowed from Databricks' Omnigent (Apache 2.0, `github.com/omnigent-ai/omnigent`)
after checking its primary docs directly: guardrails enforced as
deterministic checks *outside* the model's own reasoning, not as prompt
text the model can choose to ignore. Omnigent's own mechanism —
`policies:` declared as `{handler, factory_params}` or `{function: {path,
arguments}}`, evaluated against cumulative session state (cost so far,
tool-call history) on every action, returning **ALLOW / ASK / DENY** with
DENY winning over ASK winning over ALLOW — is adopted as-is, minus the
YAML config layer (we already have one atomic-edit-unit convention via the
Harness² component tree, Spec 5 §2; a second declarative format would
fragment "where the harness lives").

This directly answers Spec 5 §1's "c2 guardrails" gap: that gap was about
GPT Researcher having nothing to point RSI's editable surface at for
guardrails. The resolution is to split the concept in two rather than force
one answer:
- **Soft guardrails** (RSI-editable): instructional text added to
  `prompts.py` — "cite every claim," "cross-check contested numbers." The
  model can be wrong despite this; that's what makes it "soft."
- **Hard guardrails** (`agents/research/policies.py`, never RSI-editable):
  deterministic caps — `hard_revision_cap()`, `episode_timeout()`,
  `token_budget()` — checked every revision round in `research_pipeline.py`'s
  Grader/Reviser loop, independent of whatever the RSI-editable
  `MAX_REVISIONS` constant has been edited to. A bad self-edit that
  inflates `MAX_REVISIONS` still can't exceed this. Same fixed-substrate
  role as `agents/base.py`'s client wiring.

`ASK` has no meaning in this batch pipeline (no approval UI exists), so it
degrades to DENY-with-a-logged-reason — documented in the module, not
silently changed.

## 6. Resolved / open questions

1. ~~Exact pinned commit~~ — **resolved**: `v3.7.0`, commit `0957c301ed06c2a5857b834358c7227c739041d4`.
2. ~~Which free retriever to default to~~ — **resolved**: `RETRIEVER=duckduckgo`
   (the `ddgs` package), confirmed working with zero API key.
3. Whether to also vendor the optional `multi_agents/` (LangGraph/AG2)
   variant — still open, not needed for v1; the single-process
   `GPTResearcher` class is sufficient and keeps one fewer framework
   (LangGraph) in the vendored surface.
4. **Found while building Spec 5**: this project's local Ollama setup for
   `qwen3:14b` has a much smaller effective context window than the model
   natively supports — binary-searched live: an ~8KB prompt returns valid
   JSON, an ~20KB prompt returns a coherent but free-form (wrong-format)
   response, pointing at Ollama's conservative default (commonly ~4096
   tokens) rather than a model-capability limit. `rsi/proposer.py` works
   around this by capping each component file to `MAX_FILE_CHARS` (1200)
   before embedding it in a prompt — safe, since `apply_edits()` always
   validates against the real, untruncated file regardless of what the
   model saw. The real fix, if larger prompts are needed later (e.g. once
   task-level recursion is built), is server-side: set
   `OLLAMA_CONTEXT_LENGTH=32768` when starting `ollama serve`, or create a
   custom model variant with `PARAMETER num_ctx 32768` in its Modelfile.
   Left as the user's call since it's a system-level change to a running
   service, not something this codebase should do on its own.
