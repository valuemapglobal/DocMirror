# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Live console progress for quality gate runs."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Literal

from scripts.release_gate.models import StepResult

StepState = Literal["pending", "running", "pass", "fail", "skip", "cancelled"]


def _format_duration_ms(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    total_s = ms / 1000
    if total_s < 60:
        return f"{total_s:.1f}s"
    minutes = int(total_s // 60)
    seconds = int(total_s % 60)
    return f"{minutes}m {seconds}s"


def _status_label(state: StepState) -> str:
    return {
        "pending": "PENDING",
        "running": "RUNNING",
        "pass": "PASS",
        "fail": "FAIL",
        "skip": "SKIP",
        "cancelled": "CANCELLED",
    }[state]


@dataclass
class ProgressRow:
    step_id: str
    title: str
    phase: str = ""
    state: StepState = "pending"
    duration_ms: int = 0
    detail: str = ""
    started_at: float = 0.0


@dataclass
class QualityGateProgress:
    """Tracks and renders gate / hygiene step progress."""

    profile: str
    rows: list[ProgressRow]
    enabled: bool = True
    _live: object | None = field(default=None, repr=False)
    _started_at: float = field(default_factory=time.perf_counter)
    _sub_rows: list[ProgressRow] = field(default_factory=list)
    _current: int = -1
    _finished: bool = False

    @classmethod
    def for_gate_steps(cls, profile: str, steps: list, *, enabled: bool = True) -> QualityGateProgress:
        rows = [ProgressRow(step_id=s.step_id, title=s.title, phase=s.phase) for s in steps]
        return cls(profile=profile, rows=rows, enabled=enabled)

    @classmethod
    def for_hygiene_checks(cls, check_names: list[str], *, enabled: bool = True) -> QualityGateProgress:
        rows = [ProgressRow(step_id=name, title=name, phase="hygiene") for name in check_names]
        return cls(profile="hygiene", rows=rows, enabled=enabled)

    def __enter__(self) -> QualityGateProgress:
        if not self.enabled:
            return self
        try:
            from rich.live import Live

            self._live = Live(
                self._render_rich(),
                refresh_per_second=4,
                transient=False,
                console=_rich_console(),
            )
            self._live.__enter__()
        except ImportError:
            self._print_plain_header()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._live is not None:
            self._finished = True
            self._live.update(self._render_rich())
            self._live.__exit__(*exc)
            self._live = None
        elif self.enabled:
            self._print_plain_footer()

    def start(self, index: int) -> None:
        if index < 0 or index >= len(self.rows):
            return
        self._current = index
        row = self.rows[index]
        row.state = "running"
        row.started_at = time.perf_counter()
        row.detail = ""
        self._sub_rows = []
        self._refresh()

    def set_substeps(self, names: list[str]) -> None:
        self._sub_rows = [ProgressRow(step_id=n, title=n, phase="check") for n in names]
        if self._sub_rows:
            self._sub_rows[0].state = "running"
            self._sub_rows[0].started_at = time.perf_counter()
        self._refresh()

    def start_substep(self, index: int) -> None:
        if 0 <= index < len(self._sub_rows):
            self._sub_rows[index].state = "running"
            self._sub_rows[index].started_at = time.perf_counter()
            self._refresh()

    def finish_substep(
        self,
        index: int,
        *,
        passed: bool,
        duration_ms: int,
        detail: str = "",
    ) -> None:
        if 0 <= index < len(self._sub_rows):
            row = self._sub_rows[index]
            row.state = "pass" if passed else "fail"
            row.duration_ms = duration_ms
            row.detail = detail
        if index + 1 < len(self._sub_rows):
            self._sub_rows[index + 1].state = "running"
            self._sub_rows[index + 1].started_at = time.perf_counter()
        self._refresh()

    def finish(self, index: int, result: StepResult) -> None:
        if index < 0 or index >= len(self.rows):
            return
        row = self.rows[index]
        if result.skipped:
            row.state = "skip"
        elif result.passed:
            row.state = "pass"
        else:
            row.state = "fail"
        row.duration_ms = result.duration_ms
        row.detail = result.detail
        self._sub_rows = []
        self._refresh()

    def cancel_remaining(self, from_index: int) -> None:
        for row in self.rows[from_index:]:
            if row.state == "pending":
                row.state = "cancelled"
        self._refresh()

    @property
    def completed_count(self) -> int:
        return sum(1 for r in self.rows if r.state in ("pass", "fail", "skip"))

    @property
    def overall_percent(self) -> int:
        if not self.rows:
            return 100
        return int(100 * self.completed_count / len(self.rows))

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._started_at) * 1000)

    def _refresh(self) -> None:
        if not self.enabled:
            return
        if self._live is not None:
            self._live.update(self._render_rich())
        else:
            self._print_plain_progress()

    def _print_plain_header(self) -> None:
        print(f"\nDocMirror Quality Gate — profile={self.profile} ({len(self.rows)} steps)")
        print("-" * 72)

    def _print_plain_footer(self) -> None:
        print("-" * 72)
        done = self.completed_count
        print(
            f"Overall: {self.overall_percent}% ({done}/{len(self.rows)}) elapsed {_format_duration_ms(self.elapsed_ms)}"
        )

    def _print_plain_progress(self) -> None:
        bar_w = 30
        filled = int(bar_w * self.overall_percent / 100)
        bar = "=" * filled + ">" * (1 if filled < bar_w else 0) + " " * max(0, bar_w - filled - 1)
        line = (
            f"\r[{bar}] {self.overall_percent:3d}% "
            f"({self.completed_count}/{len(self.rows)}) "
            f"{_format_duration_ms(self.elapsed_ms)}"
        )
        if self._current >= 0 and self._current < len(self.rows):
            cur = self.rows[self._current]
            if cur.state == "running":
                run_ms = int((time.perf_counter() - cur.started_at) * 1000)
                line += f"  {cur.step_id} ({_format_duration_ms(run_ms)})"
        sys.stdout.write(line)
        sys.stdout.flush()

    def _render_rich(self) -> object:
        from rich.console import Group
        from rich.panel import Panel
        from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
        from rich.table import Table

        done = self.completed_count
        total = len(self.rows)
        pct = self.overall_percent

        header = Progress(
            TextColumn("[bold]Overall[/bold]"),
            BarColumn(bar_width=40),
            TextColumn("{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
        )
        header.add_task("gate", total=total, completed=done)

        table = Table(show_header=True, header_style="bold", expand=True)
        table.add_column("#", justify="right", width=3)
        table.add_column("Phase", width=12)
        table.add_column("Step", width=22)
        table.add_column("Status", width=12, no_wrap=True)
        table.add_column("Time", justify="right", width=8)
        table.add_column("Detail", overflow="fold")

        for i, row in enumerate(self.rows, start=1):
            status_text = _rich_status(row)
            if row.state == "running":
                time_text = _format_duration_ms(int((time.perf_counter() - row.started_at) * 1000))
            elif row.state in ("pass", "fail", "skip"):
                time_text = _format_duration_ms(row.duration_ms)
            else:
                time_text = "—"
            table.add_row(
                str(i),
                row.phase,
                row.step_id,
                status_text,
                time_text,
                row.detail or "",
            )

        parts: list[object] = [
            Panel(
                Group(header),
                title=f"[bold]DocMirror Quality Gate[/bold] — profile={self.profile}",
                subtitle=(f"{done}/{total} steps · {pct}% · elapsed {_format_duration_ms(self.elapsed_ms)}"),
            ),
            table,
        ]

        if self._sub_rows:
            sub = Table(show_header=True, header_style="bold dim", expand=True, box=None)
            sub.add_column("", width=3)
            sub.add_column("Sub-check", width=24)
            sub.add_column("Status", width=12, no_wrap=True)
            sub.add_column("Time", justify="right", width=8)
            parent = self.rows[self._current].step_id if self._current >= 0 else ""
            for j, sub_row in enumerate(self._sub_rows, start=1):
                if sub_row.state == "running":
                    t = _format_duration_ms(int((time.perf_counter() - sub_row.started_at) * 1000))
                elif sub_row.state in ("pass", "fail"):
                    t = _format_duration_ms(sub_row.duration_ms)
                else:
                    t = "—"
                sub.add_row("", sub_row.step_id, _rich_status(sub_row), t)
            parts.append(Panel(sub, title=f"[dim]Sub-checks: {parent}[/dim]", border_style="dim"))

        return Group(*parts)


def _rich_console():
    from rich.console import Console

    return Console()


def _rich_status(row: ProgressRow) -> Text:
    from rich.text import Text

    label = _status_label(row.state)
    styles = {
        "pending": "dim",
        "running": "bold yellow",
        "pass": "bold green",
        "fail": "bold red",
        "skip": "dim cyan",
        "cancelled": "dim",
    }
    icons = {
        "pending": "○",
        "running": "●",
        "pass": "✓",
        "fail": "✗",
        "skip": "−",
        "cancelled": "·",
    }
    return Text(f"{icons[row.state]} {label}", style=styles[row.state])
