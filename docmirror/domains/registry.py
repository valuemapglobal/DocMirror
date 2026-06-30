# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small registry for optional domain semantic solvers."""

from __future__ import annotations

from typing import Any, Protocol

from docmirror.domains.base import DomainSolution


class DomainSolver(Protocol):
    domain: str

    def solve(self, *, full_text: str, parse_result: Any = None) -> DomainSolution: ...


_SOLVERS: dict[str, DomainSolver] = {}


def register_solver(solver: DomainSolver) -> None:
    _SOLVERS[solver.domain] = solver


def get_solver(domain: str) -> DomainSolver | None:
    return _SOLVERS.get(domain)


def solve_domain(domain: str, *, full_text: str, parse_result: Any = None) -> DomainSolution | None:
    solver = get_solver(domain)
    if solver is None:
        return None
    return solver.solve(full_text=full_text, parse_result=parse_result)


__all__ = ["DomainSolver", "get_solver", "register_solver", "solve_domain"]
