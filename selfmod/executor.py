"""Executor — runs one full self-improvement cycle for a given HarnessSpec:

    trace report -> planner proposes edits -> apply in an isolated git
    worktree -> gate on tests + benchmark score vs. the current lineage tip
    -> accept (fast-forward that harness's lineage branch) or reject.

Generic across harnesses on purpose: everything domain-specific (which files
are editable, how to benchmark, which Cortex domain to trace) comes in via
the HarnessSpec. Adding a fintrack/fittrack harness later means writing a
new HarnessSpec, not touching this file.

Safety model (see README "Recursive Self-Modification"):
  - `main` is never touched. All compounding happens on `selfmod/lineage-<harness>`,
    a separate branch per harness — you decide if/when to merge it.
  - Edits only ever land in a throwaway `git worktree`, never in this
    process's own working directory, and never in the files currently
    being imported to run this very cycle.
  - Acceptance requires both: the Cortex test suite still passing, AND a
    strictly better score on that harness's fixed benchmark than the current
    lineage tip. No human judgment call and no self-reported "this is better."
  - Every cycle (accepted, rejected, or skipped) is appended to
    selfmod_data/<harness>/generations.jsonl with the diff saved alongside
    it, so the whole lineage is auditable and any single generation is
    revertible via plain git.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import tracer
from .harness_spec import HarnessSpec
from .meta_agent import ProposedEdit, SelfEditPlan, propose_plan

DATA_DIR_NAME = "selfmod_data"


def lineage_branch(harness: HarnessSpec) -> str:
    return f"selfmod/lineage-{harness.name}"


@dataclass
class CycleResult:
    generation: int
    status: str  # accepted | rejected | skipped | error
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


def _data_dir(repo_root: Path, harness: HarnessSpec) -> Path:
    d = repo_root / DATA_DIR_NAME / harness.name
    (d / "proposals").mkdir(parents=True, exist_ok=True)
    (d / "worktrees").mkdir(parents=True, exist_ok=True)
    return d


def _generations_log(repo_root: Path, harness: HarnessSpec) -> Path:
    return _data_dir(repo_root, harness) / "generations.jsonl"


def _next_generation_number(repo_root: Path, harness: HarnessSpec) -> int:
    log = _generations_log(repo_root, harness)
    if not log.exists():
        return 1
    with open(log) as f:
        return sum(1 for line in f if line.strip()) + 1


def _append_generation(repo_root: Path, harness: HarnessSpec, record: dict) -> None:
    with open(_generations_log(repo_root, harness), "a") as f:
        f.write(json.dumps(record) + "\n")


def _load_lineage_history(repo_root: Path, harness: HarnessSpec, n: int = 3) -> str:
    log = _generations_log(repo_root, harness)
    if not log.exists():
        return "(no prior self-improvement cycles)"
    records = [json.loads(line) for line in open(log) if line.strip()]
    recent = records[-n:]
    if not recent:
        return "(no prior self-improvement cycles)"
    lines = []
    for r in recent:
        lines.append(
            f"gen {r['generation']} [{r['status']}]: {r['summary']} "
            f"(baseline={r.get('baseline_score')}, candidate={r.get('candidate_score')})"
        )
    return "\n".join(lines)


def _ensure_lineage_branch(repo_root: Path, harness: HarnessSpec) -> None:
    branch = lineage_branch(harness)
    proc = _run_git(["rev-parse", "--verify", branch], repo_root, check=False)
    if proc.returncode != 0:
        _run_git(["branch", branch, "HEAD"], repo_root)


def _add_worktree(repo_root: Path, path: Path, branch: str, start_point: str, new_branch: bool) -> None:
    if path.exists():
        shutil.rmtree(path)
    args = ["worktree", "add"]
    if new_branch:
        args += ["-b", branch, str(path), start_point]
    else:
        args += [str(path), branch]
    _run_git(args, repo_root)


def _remove_worktree(repo_root: Path, path: Path) -> None:
    _run_git(["worktree", "remove", "--force", str(path)], repo_root, check=False)
    shutil.rmtree(path, ignore_errors=True)


def _apply_edits(worktree: Path, edits: list[ProposedEdit]) -> tuple[list[str], list[str]]:
    """Returns (applied_file_paths, skip_reasons)."""
    applied: list[str] = []
    skipped: list[str] = []
    for edit in edits:
        target = worktree / edit.file
        if not target.exists():
            skipped.append(f"{edit.file}: file not found in worktree")
            continue
        text = target.read_text()
        count = text.count(edit.old_string)
        if count != 1:
            skipped.append(f"{edit.file}: old_string occurs {count} times (need exactly 1)")
            continue
        target.write_text(text.replace(edit.old_string, edit.new_string, 1))
        applied.append(edit.file)
    return applied, skipped


def _run_tests(worktree: Path, python_bin: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [python_bin, "-m", "tests.test_cortex"], cwd=str(worktree),
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]


def run_cycle(
    repo_root: Path, harness: HarnessSpec, cortex_dir: str = "./cortex_data", python_bin: str = "python3",
) -> CycleResult:
    repo_root = repo_root.resolve()
    branch = lineage_branch(harness)
    _ensure_lineage_branch(repo_root, harness)
    gen_n = _next_generation_number(repo_root, harness)
    data_dir = _data_dir(repo_root, harness)

    report = tracer.build_report(cortex_dir, domain=harness.cortex_domain)
    lineage_history = _load_lineage_history(repo_root, harness)

    allowed_contents = {rel_path: (repo_root / rel_path).read_text() for rel_path in harness.allowed_files}

    plan: SelfEditPlan = propose_plan(harness, report.to_prompt_text(), allowed_contents, lineage_history)

    def finish(status: str, summary: str, **kw) -> CycleResult:
        record = {"generation": gen_n, "timestamp": time.time(), "status": status, "summary": summary, **kw}
        _append_generation(repo_root, harness, record)
        return CycleResult(generation=gen_n, status=status, summary=summary,
                            baseline_score=kw.get("baseline_score"), candidate_score=kw.get("candidate_score"),
                            detail=kw.get("detail", ""), applied_edits=kw.get("applied_edits", []))

    if not plan.edits:
        return finish("skipped", plan.summary or "no edits proposed", detail=plan.parse_error or "")

    baseline_wt = data_dir / "worktrees" / f"gen{gen_n}_baseline"
    candidate_branch = f"selfmod/{harness.name}-gen{gen_n}-candidate"
    candidate_wt = data_dir / "worktrees" / f"gen{gen_n}_candidate"

    keep_candidate_branch = False
    try:
        _add_worktree(repo_root, baseline_wt, branch, branch, new_branch=False)
        _add_worktree(repo_root, candidate_wt, candidate_branch, branch, new_branch=True)

        applied, skipped = _apply_edits(candidate_wt, plan.edits)
        if not applied:
            return finish("rejected", plan.summary, detail="no edits applied: " + "; ".join(skipped))

        _run_git(["add", *applied], candidate_wt)
        commit_msg = f"selfmod[{harness.name}] gen{gen_n}: {plan.summary}\n\n" + "\n".join(
            f"- {e.file}: {e.rationale}" for e in plan.edits if e.file in applied
        )
        _run_git(["commit", "-m", commit_msg], candidate_wt)

        diff_proc = _run_git(["show", "HEAD"], candidate_wt)
        patch_path = data_dir / "proposals" / f"gen{gen_n}.patch"
        patch_path.write_text(diff_proc.stdout)

        tests_ok, test_output = _run_tests(candidate_wt, python_bin)
        if not tests_ok:
            return finish("rejected", plan.summary, applied_edits=applied,
                           detail=f"test suite failed:\n{test_output}")

        baseline_score = harness.benchmark_fn(baseline_wt, python_bin)
        candidate_score = harness.benchmark_fn(candidate_wt, python_bin)

        # Must drop the baseline worktree before force-updating the lineage branch —
        # git refuses to move a branch ref that's checked out in another worktree.
        _remove_worktree(repo_root, baseline_wt)

        if candidate_score.scalar_score > baseline_score.scalar_score:
            _run_git(["branch", "-f", branch, candidate_branch], repo_root)
            keep_candidate_branch = True
            return finish(
                "accepted", plan.summary, applied_edits=applied,
                baseline_score=baseline_score.scalar_score, candidate_score=candidate_score.scalar_score,
                detail=f"baseline:\n{baseline_score.to_prompt_text()}\ncandidate:\n{candidate_score.to_prompt_text()}",
            )
        return finish(
            "rejected", plan.summary, applied_edits=applied,
            baseline_score=baseline_score.scalar_score, candidate_score=candidate_score.scalar_score,
            detail="no improvement over lineage tip",
        )
    finally:
        _remove_worktree(repo_root, baseline_wt)
        _remove_worktree(repo_root, candidate_wt)
        if not keep_candidate_branch:
            _run_git(["branch", "-D", candidate_branch], repo_root, check=False)
