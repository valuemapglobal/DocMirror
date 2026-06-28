# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Golden-matrix benchmark CLI command.

Runs the evaluation benchmark suite against the golden test corpus under
``tests/golden``, compares metrics to an optional baseline JSON snapshot, and
prints regression deltas via Rich. Intended for CI and local quality gates
before release.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command("benchmark")
@click.option(
    "--golden-root",
    type=click.Path(exists=True, path_type=Path),
    default=Path("tests/golden"),
    help="Golden test matrix root directory",
)
@click.option(
    "--baseline",
    type=click.Path(path_type=Path),
    default=None,
    help="Previous benchmark JSON for regression delta",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path("output/benchmark/results"),
    help="Directory to write benchmark results",
)
@click.option("--fail-on-regression", is_flag=True, help="Exit 1 if any metric regresses vs baseline")
def benchmark(golden_root: Path, baseline: Path | None, output_dir: Path, fail_on_regression: bool) -> None:
    """Run golden matrix benchmark and report metrics."""

    async def _parse(path: Path):
        from docmirror.input.entry.factory import PerceiveOptions, perceive_document

        return await perceive_document(path, PerceiveOptions(skip_cache=True))

    async def _run():
        from docmirror.eval.benchmark_runner import run_benchmark_matrix, save_benchmark_result

        baseline_path = baseline
        if baseline_path is None:
            existing = sorted(output_dir.glob("benchmark_*.json"))
            if existing:
                baseline_path = existing[-1]

        result = await run_benchmark_matrix(_parse, golden_root=golden_root, baseline_path=baseline_path)
        out = save_benchmark_result(result, output_dir)

        console.print(f"[green]Benchmark complete[/green]: {out}")
        console.print(f"  cases: {result['case_count']}")
        if result.get("summary"):
            for k, v in result["summary"].items():
                console.print(f"  {k}: {v:.4f}")
        if result.get("regression_delta"):
            console.print("[yellow]Regression delta:[/yellow]")
            for k, v in result["regression_delta"].items():
                color = "red" if v < 0 else "green"
                console.print(f"  [{color}]{k}: {v:+.4f}[/{color}]")

        if result.get("failed_cases"):
            console.print(f"[red]Failed cases:[/red] {', '.join(result['failed_cases'])}")

        if fail_on_regression and result.get("regression_delta"):
            regressions = [k for k, v in result["regression_delta"].items() if v < -0.01]
            if regressions:
                raise SystemExit(1)

        return result

    asyncio.run(_run())


if __name__ == "__main__":
    benchmark()
