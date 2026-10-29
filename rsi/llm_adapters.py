"""Ready-made llm_call adapters for the proposer -- the engine itself
(proposer.py / probe.py / composer.py) doesn't know or care how a consumer
talks to their LLM; it just awaits whatever `llm_call(system, user) -> str`
coroutine it's given, and treats an empty string as the dry-run signal.

These two adapters are what self_healing_ai's own coding and research
harnesses pass in -- proving the interface works for two genuinely
different providers (Anthropic's Messages API vs. any Ollama/DashScope
model via an OpenAI-compatible endpoint) before any other consumer touches
it. Writing a third one for a different provider means implementing this
same two-argument-in, string-out shape -- nothing elsewhere needs to change.
"""

from __future__ import annotations

import os
from typing import Awaitable, Callable

LLMCall = Callable[[str, str], Awaitable[str]]


def qwen_ollama_llm_call(tier: str = "STRATEGIC_LLM") -> LLMCall:
    """Reads FAST_LLM/SMART_LLM/STRATEGIC_LLM (set once here via
    agents.research.qwen_config.configure_qwen()) and calls through
    GenericLLMProvider -- same pattern as agents/research/reflection.py.
    The underlying call returns "" (the engine's dry-run signal) if no
    QWEN_API_KEY/QWEN_BASE_URL was configured.
    """
    import agents.research  # noqa: F401 -- side effect: puts gpt_researcher on sys.path

    agents.research.configure_qwen()  # called once at adapter construction, not per-request

    async def _call(system: str, user: str) -> str:
        from gpt_researcher.llm_provider.generic import GenericLLMProvider

        llm_str = os.environ.get(tier)
        if not llm_str:
            return ""
        provider, model = llm_str.split(":", 1)
        llm = GenericLLMProvider.from_provider(provider, model=model, temperature=0.3, verbose=False)
        return await llm.get_chat_response(
            [{"role": "system", "content": system}, {"role": "user", "content": user}], stream=False,
        )

    return _call


def claude_llm_call(thinking_budget: str = "max") -> LLMCall:
    """Wraps agents.base.Agent (Claude via the Anthropic SDK, or
    DryRunClient if ANTHROPIC_API_KEY isn't set) -- the pattern
    selfmod/meta_agent.py used before this engine was unified.
    """
    async def _call(system: str, user: str) -> str:
        from agents.base import Agent

        agent = Agent(name="self_improvement_planner", system_prompt=system, thinking_budget=thinking_budget)
        result = agent.run(user)  # synchronous call -- fine here, this is a single-cycle CLI tool, not a server
        return "" if result.dry_run else result.text

    return _call
