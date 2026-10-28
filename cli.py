#!/usr/bin/env python3
"""CLI entrypoint.

    python cli.py "write a function that returns the nth fibonacci number"
    python cli.py --stats              # show Cortex memory stats
"""

import argparse
import os
import sys

from pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task", nargs="?", help="Task description")
    parser.add_argument("--scope", default="default")
    parser.add_argument("--stats", action="store_true", help="Print Cortex memory stats and exit")
    args = parser.parse_args()

    if args.stats:
        from cortex import CortexStore
        store = CortexStore(persist_dir="./cortex_data")
        print(store.stats())
        return

    if not args.task:
        parser.error("task is required unless --stats is passed")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY is not set — running in DRY RUN mode. "
              "Agents will return placeholder text instead of real completions.\n", file=sys.stderr)

    result = run_pipeline(args.task, scope=args.scope)

    print(f"\n{'='*60}")
    print(f"Outcome: {result.episode.outcome.value}")
    print(f"Healer attempts: {result.episode.healer_attempt_count}")
    print(f"Cost: {result.episode.cost_actual.input_tokens} in / {result.episode.cost_actual.output_tokens} out tokens")
    print(f"Workspace: {result.workspace}")
    print(f"{'='*60}\n")
    if result.review:
        print("Reviewer verdict:\n" + result.review)


if __name__ == "__main__":
    main()
