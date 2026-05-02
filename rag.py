"""
rag.py
======
Resource Allocation Graph (RAG) model and utilities.

The RAG is a bipartite directed graph:
  - Process nodes  (circles)   — one per process
  - Resource nodes (rectangles) — one per resource type, with instance dots

Edge types:
  - Assignment edge  : Resource → Process  (resource is allocated to process)
  - Request edge     : Process  → Resource  (process is waiting for resource)

A deadlock exists iff the graph contains a cycle.
For single-instance resources: cycle ↔ deadlock (exact).
For multi-instance resources:  cycle is necessary but not sufficient.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Nodes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ProcessNode:
    pid:   int
    label: str          # e.g. "P1"
    state: str = "running"  # running | blocked | killed

    def __repr__(self):
        return f"ProcessNode({self.label}, {self.state})"


@dataclass
class ResourceNode:
    rid:       int
    label:     str      # e.g. "R1"
    instances: int      # total instances
    allocated: int = 0  # currently allocated

    @property
    def available(self) -> int:
        return self.instances - self.allocated

    def __repr__(self):
        return f"ResourceNode({self.label}, {self.allocated}/{self.instances})"


# ──────────────────────────────────────────────────────────────────────────────
# Edges
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Edge:
    """
    Directed edge in the RAG.

    type = "assignment" : Resource → Process
    type = "request"    : Process  → Resource
    """
    src:       str    # label of source node
    dst:       str    # label of destination node
    edge_type: str    # "assignment" | "request"

    def __repr__(self):
        arrow = "→" if self.edge_type == "assignment" else "⟶"
        return f"{self.src} {arrow} {self.dst} [{self.edge_type}]"


# ──────────────────────────────────────────────────────────────────────────────
# RAG class
# ──────────────────────────────────────────────────────────────────────────────

class ResourceAllocationGraph:
    """
    Full Resource Allocation Graph with cycle / deadlock detection.
    """

    def __init__(self):
        self.processes: List[ProcessNode]  = []
        self.resources: List[ResourceNode] = []
        self.edges:     List[Edge]         = []

    # ── Node management ──────────────────────────────────────────────────────

    def add_process(self, pid: int, label: Optional[str] = None) -> ProcessNode:
        lbl = label or f"P{pid}"
        node = ProcessNode(pid=pid, label=lbl)
        self.processes.append(node)
        return node

    def add_resource(
        self,
        rid:       int,
        instances: int = 1,
        label:     Optional[str] = None,
    ) -> ResourceNode:
        lbl = label or f"R{rid}"
        node = ResourceNode(rid=rid, label=lbl, instances=instances)
        self.resources.append(node)
        return node

    # ── Edge management ──────────────────────────────────────────────────────

    def allocate(self, resource_label: str, process_label: str) -> bool:
        """
        Allocate one instance of resource to process.
        Returns False if no instances are available.
        """
        r = self._get_resource(resource_label)
        p = self._get_process(process_label)
        if r is None or p is None:
            raise ValueError(f"Unknown node: {resource_label!r} or {process_label!r}")
        if r.available < 1:
            return False

        r.allocated += 1
        p.state = "running"
        self.edges.append(Edge(src=resource_label, dst=process_label, edge_type="assignment"))
        return True

    def request(self, process_label: str, resource_label: str):
        """Process requests a resource (blocks it)."""
        p = self._get_process(process_label)
        if p is None:
            raise ValueError(f"Unknown process: {process_label!r}")
        p.state = "blocked"
        self.edges.append(Edge(src=process_label, dst=resource_label, edge_type="request"))

    def release(self, resource_label: str, process_label: str):
        """Process releases a resource it holds."""
        r = self._get_resource(resource_label)
        if r:
            r.allocated = max(0, r.allocated - 1)
        self.edges = [
            e for e in self.edges
            if not (e.src == resource_label and e.dst == process_label
                    and e.edge_type == "assignment")
        ]

    # ── Cycle / Deadlock Detection ────────────────────────────────────────────

    def detect_deadlock(self) -> Tuple[bool, List[str]]:
        """
        Build combined adjacency over all nodes (processes + resources)
        and run DFS to detect a back-edge (cycle).

        Returns
        -------
        (deadlock_found, list_of_node_labels_in_cycle)
        """
        all_nodes = [p.label for p in self.processes] + \
                    [r.label for r in self.resources]
        idx = {lbl: i for i, lbl in enumerate(all_nodes)}
        n   = len(all_nodes)

        adj: List[List[int]] = [[] for _ in range(n)]
        for e in self.edges:
            if e.src in idx and e.dst in idx:
                adj[idx[e.src]].append(idx[e.dst])

        WHITE, GRAY, BLACK = 0, 1, 2
        color = [WHITE] * n
        cycle_nodes: List[str] = []

        def dfs(u: int, path: List[int]) -> bool:
            color[u] = GRAY
            path.append(u)
            for v in adj[u]:
                if color[v] == GRAY:
                    start = path.index(v)
                    cycle_nodes.extend(all_nodes[node] for node in path[start:])
                    return True
                if color[v] == WHITE:
                    if dfs(v, path):
                        return True
            path.pop()
            color[u] = BLACK
            return False

        for start in range(n):
            if color[start] == WHITE:
                if dfs(start, []):
                    return True, list(dict.fromkeys(cycle_nodes))  # dedup, ordered

        return False, []

    def deadlocked_processes(self) -> List[str]:
        """Return labels of process nodes involved in the deadlock."""
        _, cycle = self.detect_deadlock()
        return [lbl for lbl in cycle
                if any(p.label == lbl for p in self.processes)]

    # ── Wait-For Graph reduction ──────────────────────────────────────────────

    def to_wait_for_graph(self) -> dict[str, List[str]]:
        """
        Project the RAG onto a Wait-For Graph (WFG):
        Pi → Pj exists iff Pi requests a resource that Pj holds.
        """
        wfg: dict[str, List[str]] = {p.label: [] for p in self.processes}

        for req_edge in self.edges:
            if req_edge.edge_type != "request":
                continue
            # req_edge.src = process, req_edge.dst = resource
            resource_label = req_edge.dst
            # Find who holds that resource
            for alloc_edge in self.edges:
                if (alloc_edge.edge_type == "assignment"
                        and alloc_edge.src == resource_label):
                    holder = alloc_edge.dst
                    if holder != req_edge.src and holder not in wfg[req_edge.src]:
                        wfg[req_edge.src].append(holder)

        return wfg

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "processes": [
                {"pid": p.pid, "label": p.label, "state": p.state}
                for p in self.processes
            ],
            "resources": [
                {
                    "rid":       r.rid,
                    "label":     r.label,
                    "instances": r.instances,
                    "allocated": r.allocated,
                    "available": r.available,
                }
                for r in self.resources
            ],
            "edges": [
                {"src": e.src, "dst": e.dst, "type": e.edge_type}
                for e in self.edges
            ],
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_process(self, label: str) -> Optional[ProcessNode]:
        return next((p for p in self.processes if p.label == label), None)

    def _get_resource(self, label: str) -> Optional[ResourceNode]:
        return next((r for r in self.resources if r.label == label), None)

    def __repr__(self):
        return (f"RAG(processes={len(self.processes)}, "
                f"resources={len(self.resources)}, "
                f"edges={len(self.edges)})")


# ──────────────────────────────────────────────────────────────────────────────
# Preset factory functions (match the interactive presets in the UI)
# ──────────────────────────────────────────────────────────────────────────────

def make_deadlock_example() -> ResourceAllocationGraph:
    """Classic 3-process circular deadlock."""
    g = ResourceAllocationGraph()
    g.add_process(1, "P1")
    g.add_process(2, "P2")
    g.add_process(3, "P3")
    g.add_resource(1, instances=2, label="R1")
    g.add_resource(2, instances=1, label="R2")
    g.add_resource(3, instances=1, label="R3")

    # Allocations
    g.allocate("R1", "P2")   # R1 → P2
    g.allocate("R2", "P1")   # R2 → P1
    g.allocate("R3", "P3")   # R3 → P3

    # Requests (forming cycle P1→R1→P2→R3→P3→R2→P1)
    g.request("P1", "R1")
    g.request("P2", "R3")
    g.request("P3", "R2")

    return g


def make_safe_example() -> ResourceAllocationGraph:
    """No deadlock — P2 can finish and release."""
    g = ResourceAllocationGraph()
    g.add_process(1, "P1")
    g.add_process(2, "P2")
    g.add_process(3, "P3")
    g.add_resource(1, instances=2, label="R1")
    g.add_resource(2, instances=2, label="R2")

    g.allocate("R1", "P1")
    g.allocate("R2", "P3")

    g.request("P1", "R2")   # P1 wants R2 but doesn't create a cycle
    # P2 is free; P3 holds R2 and doesn't need anything

    return g
