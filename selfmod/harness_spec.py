"""A HarnessSpec is the one thing you need to supply to point the recursive
self-improvement engine at a new agent — this is the seam that lets the same
selfmod/ machinery later target a fintrack or fittrack agent instead of (or
alongside) the coding and research harnesses already defined in harnesses/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class ScoreLike(Protocol):
    scalar_score: float

    def to_prompt_text(self) -> str: ...


BenchmarkFn = Callable[[Path, str], ScoreLike]


@dataclass(frozen=True)
class HarnessSpec:
    name: str  # used as the lineage branch suffix and the on-disk data subdir
    description: str  # shown to the planner for framing
    allowed_files: list[str]  # repo-relative paths the planner may propose edits to
    benchmark_fn: BenchmarkFn  # (repo_root, python_bin) -> ScoreLike, run inside a worktree
    cortex_domain: str  # Episode.domain to filter traces by when building the report
