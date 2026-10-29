"""Composer -- decides accept/reject and owns the lineage branch + generation
log. Harnessing-level only (docs/05_rsi_harness2_design_spec.md S4) -- the
one tier that's "not new engineering," ported from selfmod/executor.py and
retargeted at the research harness's component tree + git lineage branch.
Task-level composition has nothing to call yet (probe.py's task_probe is
an explicit stub), so there is no task-level accept path here either.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .component_tree import ALLOWED_FILES
from .probe import add_worktree, apply_edits, harnessing_probe, remove_worktree
from .proposer import SelfEditPlan, propose_from_report

LINEAGE_BRANCH = "rsi/lineage-research"
DATA_DIR = "rsi_data"


@dataclass
class CycleResult:
    generation: int
    status: str  # accepted | rejected | skipped
    summary: str
    baseline_score: float | None = None
    candidate_score: float | None = None
    detail: str = ""
    applied_edits: list[str] = field(default_factory=list)


def _run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}:\n{proc.stderr}")
    return proc


def _data_dir(repo_root: Path) -> Path:
    d = repo_root / DATA_DIR
    (d / "proposals").mkdir(parents=True, exist_ok=True)
    (d / "worktrees").mkdir(parents=True, exist_ok=True)
    return d


def _generations_log(repo_root: Path) -> Path:
    return _data_dir(repo_root) / "generations.jsonl"


def _next_generation(repo_root: Path) -> int:
    log = _generations_log(repo_root)
    if not log.exists():
        return 1
    with open(log) as f:
        return sum(1 for line in f if line.strip()) + 1


def _append_generation(repo_root: Path, record: dict) -> None:
    with open(_generations_log(repo_root), "a") as f:
        f.write(json.dumps(record) + "\n")


def _lineage_history(repo_root: Path, n: int = 3) -> str:
    log = _generations_log(repo_root)
    if not log.exists():
        return "(no prior self-improvement cycles)"
    records = [json.loads(line) for line in open(log) if line.strip()]
    recent = records[-n:]
    if not recent:
        return "(no prior self-improvement cycles)"
    return "\n".join(
        f"gen {r['generation']} [{r['status']}]: {r['summary']} "
        f"(baseline={r.get('baseline_score')}, candidate={r.get('candidate_score')})"
        for r in recent
    )


def _ensure_lineage_branch(repo_root: Path) -> None:
    if _run_git(["rev-parse", "--verify", LINEAGE_BRANCH], repo_root, check=False).returncode != 0:
        _run_git(["branch", LINEAGE_BRANCH, "HEAD"], repo_root)


async def run_cycle(repo_root: Path, cortex_dir: str = "./cortex_data", python_bin: str = "python3") -> CycleResult:
    """One Propose -> Probe -> Compose step, harnessing-level. Never touches
    main -- all compounding happens on LINEAGE_BRANCH, same safety model as
    selfmod/executor.py (propose-only; the user merges the branch by hand)."""
    from agents.research import configure_qwen
    from selfmod.tracer import build_report  # reused as-is -- fully provider-agnostic, see docs/02 S3

    configure_qwen()  # sets STRATEGIC_LLM etc. -- propose_from_report() reads them, same as research_pipeline.py
    repo_root = repo_root.resolve()
    _ensure_lineage_branch(repo_root)
    gen_n = _next_generation(repo_root)
    data_dir = _data_dir(repo_root)

    report = build_report(cortex_dir, domain="research")
    lineage_history = _lineage_history(repo_root)
    plan: SelfEditPlan = await propose_from_report(repo_root, report.to_prompt_text(), lineage_history)

    def finish(status: str, summary: str, **kw) -> CycleResult:
        _append_generation(repo_root, {"generation": gen_n, "timestamp": time.time(),
                                        "status": status, "summary": summary, **kw})
        return CycleResult(generation=gen_n, status=status, summary=summary,
                            baseline_score=kw.get("baseline_score"), candidate_score=kw.get("candidate_score"),
                            detail=kw.get("detail", ""), applied_edits=kw.get("applied_edits", []))

    if not plan.edits:
        return finish("skipped", plan.summary or "no edits proposed", detail=plan.parse_error or "")

    baseline_wt = data_dir / "worktrees" / f"gen{gen_n}_baseline"
    candidate_branch = f"rsi/research-gen{gen_n}-candidate"
    candidate_wt = data_dir / "worktrees" / f"gen{gen_n}_candidate"
    keep_candidate_branch = False

    try:
        add_worktree(repo_root, baseline_wt, LINEAGE_BRANCH, LINEAGE_BRANCH, new_branch=False)
        add_worktree(repo_root, candidate_wt, candidate_branch, LINEAGE_BRANCH, new_branch=True)

        applied, skipped = apply_edits(candidate_wt, plan.edits)
        if not applied:
            return finish("rejected", plan.summary, detail="no edits applied: " + "; ".join(skipped))

        _run_git(["add", *applied], candidate_wt)
        commit_msg = f"rsi[research] gen{gen_n}: {plan.summary}\n\n" + "\n".join(
            f"- {e.file}: {e.rationale}" for e in plan.edits if e.file in applied
        )
        _run_git(["commit", "-m", commit_msg], candidate_wt)
        patch_path = data_dir / "proposals" / f"gen{gen_n}.patch"
        patch_path.write_text(_run_git(["show", "HEAD"], candidate_wt).stdout)

        result = harnessing_probe(repo_root, baseline_wt, candidate_wt, python_bin)
        if not result.tests_ok:
            return finish("rejected", plan.summary, applied_edits=applied,
                           detail=f"test suite failed:\n{result.test_output}")

        remove_worktree(repo_root, baseline_wt)  # must drop before force-updating LINEAGE_BRANCH

        if result.candidate_score.scalar_score > result.baseline_score.scalar_score:
            _run_git(["branch", "-f", LINEAGE_BRANCH, candidate_branch], repo_root)
            keep_candidate_branch = True
            return finish("accepted", plan.summary, applied_edits=applied,
                          baseline_score=result.baseline_score.scalar_score,
                          candidate_score=result.candidate_score.scalar_score,
                          detail=f"baseline:\n{result.baseline_score.to_prompt_text()}\n"
                                 f"candidate:\n{result.candidate_score.to_prompt_text()}")
        return finish("rejected", plan.summary, applied_edits=applied,
                      baseline_score=result.baseline_score.scalar_score,
                      candidate_score=result.candidate_score.scalar_score,
                      detail="no improvement over lineage tip")
    finally:
        remove_worktree(repo_root, baseline_wt)
        remove_worktree(repo_root, candidate_wt)
        if not keep_candidate_branch:
            _run_git(["branch", "-D", candidate_branch], repo_root, check=False)
