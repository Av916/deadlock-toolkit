"""
analysis.py
===========
High-level deadlock analysis and report generation.

This module ties together the lower-level algorithms into one project-facing
API. It accepts either a system-state matrix or a Resource Allocation Graph and
returns a report that can be printed, serialized, or shown in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from deadlock_detector import BankersAlgorithm, detect_deadlock_multi
from rag import ResourceAllocationGraph


@dataclass(frozen=True)
class DeadlockReport:
    """Complete diagnosis returned by the toolkit."""

    method: str
    diagnosis: str
    deadlock_found: bool
    deadlocked_processes: list[str] = field(default_factory=list)
    deadlocked_resources: list[str] = field(default_factory=list)
    cycle: list[str] = field(default_factory=list)
    is_safe_state: Optional[bool] = None
    safe_sequence: list[str] = field(default_factory=list)
    recommended_strategy: str = "none"
    recommended_action: str = "No recovery action required."
    analysis_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "diagnosis": self.diagnosis,
            "deadlock_found": self.deadlock_found,
            "deadlocked_processes": list(self.deadlocked_processes),
            "deadlocked_resources": list(self.deadlocked_resources),
            "cycle": list(self.cycle),
            "is_safe_state": self.is_safe_state,
            "safe_sequence": list(self.safe_sequence),
            "recommended_strategy": self.recommended_strategy,
            "recommended_action": self.recommended_action,
            "analysis_log": list(self.analysis_log),
        }

    def to_text(self) -> str:
        lines = [
            "Deadlock Analysis Report",
            f"Method: {self.method}",
            f"Diagnosis: {self.diagnosis}",
            f"Deadlock Found: {'YES' if self.deadlock_found else 'NO'}",
        ]

        if self.deadlocked_processes:
            lines.append("Deadlocked Processes: " + ", ".join(self.deadlocked_processes))
        if self.deadlocked_resources:
            lines.append("Deadlocked Resources: " + ", ".join(self.deadlocked_resources))
        if self.cycle:
            lines.append("Cycle: " + " -> ".join(self.cycle))
        if self.is_safe_state is not None:
            lines.append(f"Safe State: {'YES' if self.is_safe_state else 'NO'}")
        if self.safe_sequence:
            lines.append("Safe Sequence: <" + " -> ".join(self.safe_sequence) + ">")

        lines.extend(
            [
                f"Recommended Strategy: {self.recommended_strategy}",
                f"Recommended Action: {self.recommended_action}",
            ]
        )

        if self.analysis_log:
            lines.append("Analysis Log:")
            lines.extend(f"  - {item}" for item in self.analysis_log)

        return "\n".join(lines)


def analyze_system_state(
    allocation: list[list[int]],
    request: list[list[int]],
    available: list[int],
    max_need: Optional[list[list[int]]] = None,
    process_names: Optional[list[str]] = None,
    resource_names: Optional[list[str]] = None,
) -> DeadlockReport:
    """
    Analyze a multi-instance resource state using matrix deadlock detection.

    If ``max_need`` is provided, the report also runs Banker's Algorithm to
    classify the state as safe or unsafe.
    """

    _validate_system_state(allocation, request, available, max_need)
    n = len(allocation)
    m = len(available)
    procs = process_names or [f"P{i}" for i in range(n)]
    ress = resource_names or [f"R{j}" for j in range(m)]

    if len(procs) != n:
        raise ValueError("process_names length must match number of processes")
    if len(ress) != m:
        raise ValueError("resource_names length must match number of resources")

    deadlock_found, deadlocked_ids = detect_deadlock_multi(
        allocation, request, available
    )
    deadlocked_processes = [procs[i] for i in deadlocked_ids]
    deadlocked_resources = [
        ress[j]
        for j in range(m)
        if any(request[i][j] > 0 for i in deadlocked_ids)
    ]

    is_safe_state: Optional[bool] = None
    safe_sequence: list[str] = []
    log: list[str] = [
        f"Processes={n}, resource types={m}, available={available}",
        "Matrix detection completed.",
    ]

    if max_need is not None:
        banker = BankersAlgorithm(n, m, max_need, allocation, available)
        is_safe_state, seq, banker_log = banker.is_safe()
        safe_sequence = [procs[i] for i in seq]
        log.extend(banker_log)

    diagnosis = _matrix_diagnosis(deadlock_found, is_safe_state)
    strategy, action = _recommend_for_matrix_state(
        deadlock_found=deadlock_found,
        deadlocked_count=len(deadlocked_ids),
        total_processes=n,
        is_safe_state=is_safe_state,
    )

    return DeadlockReport(
        method="Multi-instance matrix detection",
        diagnosis=diagnosis,
        deadlock_found=deadlock_found,
        deadlocked_processes=deadlocked_processes,
        deadlocked_resources=deadlocked_resources,
        is_safe_state=is_safe_state,
        safe_sequence=safe_sequence,
        recommended_strategy=strategy,
        recommended_action=action,
        analysis_log=log,
    )


def analyze_resource_allocation_graph(
    graph: ResourceAllocationGraph,
) -> DeadlockReport:
    """
    Analyze a Resource Allocation Graph and return a project-ready report.
    """

    found, cycle = graph.detect_deadlock()
    deadlocked_processes = graph.deadlocked_processes()
    resource_labels = {resource.label for resource in graph.resources}
    deadlocked_resources = [label for label in cycle if label in resource_labels]
    single_instance = all(resource.instances == 1 for resource in graph.resources)

    log = [
        f"Graph has {len(graph.processes)} processes, "
        f"{len(graph.resources)} resources, and {len(graph.edges)} edges.",
        "DFS cycle detection completed.",
    ]

    if found and not single_instance:
        log.append(
            "Cycle found in a multi-instance RAG. Confirm with matrix detection "
            "because a cycle is necessary but not always sufficient."
        )

    if found:
        strategy = "priority_victim"
        action = (
            "Break the cycle by terminating or preempting the lowest-cost "
            "deadlocked process, then re-run detection."
        )
        diagnosis = "Deadlock cycle detected in the resource allocation graph."
    else:
        strategy = "none"
        action = "No recovery needed. Continue monitoring future requests."
        diagnosis = "No cycle detected; current RAG is stable."

    return DeadlockReport(
        method="Resource Allocation Graph DFS",
        diagnosis=diagnosis,
        deadlock_found=found,
        deadlocked_processes=deadlocked_processes,
        deadlocked_resources=deadlocked_resources,
        cycle=cycle,
        recommended_strategy=strategy,
        recommended_action=action,
        analysis_log=log,
    )


def compare_deadlock_methods() -> list[dict[str, str]]:
    """Return a compact OS-theory comparison for reports or README output."""

    return [
        {
            "method": "Prevention",
            "idea": "Break at least one Coffman condition before deadlock can occur.",
            "example": "Resource ordering, no hold-and-wait, preemption.",
            "tradeoff": "Simple guarantee, but lower resource utilization.",
        },
        {
            "method": "Avoidance",
            "idea": "Grant requests only when the resulting state remains safe.",
            "example": "Banker's Algorithm.",
            "tradeoff": "Better utilization, but requires maximum claims in advance.",
        },
        {
            "method": "Detection and Recovery",
            "idea": "Allow deadlocks, detect them, then recover.",
            "example": "RAG cycle detection, matrix detection, victim selection.",
            "tradeoff": "Flexible and realistic, but deadlocks exist until detected.",
        },
    ]


def _validate_system_state(
    allocation: list[list[int]],
    request: list[list[int]],
    available: list[int],
    max_need: Optional[list[list[int]]],
) -> None:
    if not allocation:
        raise ValueError("allocation matrix must contain at least one process")
    if not available:
        raise ValueError("available vector must contain at least one resource")

    rows = len(allocation)
    cols = len(available)
    _validate_matrix("allocation", allocation, rows, cols)
    _validate_matrix("request", request, rows, cols)
    _validate_vector("available", available)

    if max_need is not None:
        _validate_matrix("max_need", max_need, rows, cols)
        for i in range(rows):
            for j in range(cols):
                if allocation[i][j] > max_need[i][j]:
                    raise ValueError(
                        f"allocation[{i}][{j}] exceeds max_need[{i}][{j}]"
                    )


def _validate_matrix(
    name: str,
    matrix: list[list[int]],
    rows: int,
    cols: int,
) -> None:
    if len(matrix) != rows:
        raise ValueError(f"{name} must have {rows} rows")
    for i, row in enumerate(matrix):
        if len(row) != cols:
            raise ValueError(f"{name}[{i}] must have {cols} columns")
        _validate_vector(f"{name}[{i}]", row)


def _validate_vector(name: str, vector: list[int]) -> None:
    for value in vector:
        if not isinstance(value, int):
            raise ValueError(f"{name} values must be integers")
        if value < 0:
            raise ValueError(f"{name} values must be non-negative")


def _matrix_diagnosis(
    deadlock_found: bool,
    is_safe_state: Optional[bool],
) -> str:
    if deadlock_found:
        return "Deadlock detected: one or more processes cannot finish."
    if is_safe_state is False:
        return "No current deadlock, but the state is unsafe."
    if is_safe_state is True:
        return "No deadlock detected and the state is safe."
    return "No deadlock detected by matrix analysis."


def _recommend_for_matrix_state(
    deadlock_found: bool,
    deadlocked_count: int,
    total_processes: int,
    is_safe_state: Optional[bool],
) -> tuple[str, str]:
    if deadlock_found:
        if deadlocked_count == total_processes:
            return (
                "priority_victim",
                "Select the lowest-cost victim by priority, resources held, "
                "and age; terminate or preempt it, then re-run detection.",
            )
        return (
            "terminate_one",
            "Terminate the cheapest deadlocked process first, release its "
            "resources, and repeat detection until the system is stable.",
        )

    if is_safe_state is False:
        return (
            "banker_avoidance",
            "Do not grant additional risky requests. Use Banker's Algorithm "
            "to wait until a safe sequence exists.",
        )

    return ("none", "No recovery action required.")
