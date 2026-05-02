"""
deadlock_detector.py
====================
Core deadlock detection algorithms.

Algorithms implemented:
  1. DFS-based cycle detection on Wait-For Graph (single-instance resources)
  2. Multi-instance deadlock detection (Coffman matrix algorithm)
  3. Banker's Algorithm safety check (for avoidance)

Author : OS Project
"""

from typing import List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# 1. Wait-For Graph (WFG) – DFS Cycle Detection
#    Time  : O(V + E)
#    Space : O(V)
#    Use   : Single-instance resources only
# ──────────────────────────────────────────────────────────────────────────────

class WaitForGraph:
    """
    Directed graph where an edge Pi → Pj means
    'Pi is waiting for a resource currently held by Pj'.

    A cycle in this graph ↔ deadlock.
    """

    def __init__(self, num_processes: int):
        self.n = num_processes
        # adjacency list: process index → list of process indices
        self.adj: List[List[int]] = [[] for _ in range(num_processes)]

    def add_edge(self, pi: int, pj: int):
        """Pi waits for Pj."""
        if pj not in self.adj[pi]:
            self.adj[pi].append(pj)

    def remove_edge(self, pi: int, pj: int):
        if pj in self.adj[pi]:
            self.adj[pi].remove(pj)

    def detect_cycle(self) -> tuple[bool, List[int]]:
        """
        Run iterative DFS to find a back-edge (cycle).

        Returns
        -------
        (deadlock_found, deadlocked_processes)
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color = [WHITE] * self.n
        deadlocked: List[int] = []

        def dfs(u: int, path: List[int]) -> bool:
            color[u] = GRAY
            path.append(u)

            for v in self.adj[u]:
                if color[v] == GRAY:          # back-edge → cycle
                    # extract the cycle portion
                    cycle_start = path.index(v)
                    deadlocked.extend(path[cycle_start:])
                    return True
                if color[v] == WHITE:
                    if dfs(v, path):
                        return True

            path.pop()
            color[u] = BLACK
            return False

        for start in range(self.n):
            if color[start] == WHITE:
                if dfs(start, []):
                    return True, list(set(deadlocked))

        return False, []

    def get_adjacency(self) -> List[List[int]]:
        return [list(neighbors) for neighbors in self.adj]


# ──────────────────────────────────────────────────────────────────────────────
# 2. Multi-Instance Deadlock Detection
#    Time  : O(n² × m)   n = processes, m = resource types
#    Space : O(n × m)
#    Use   : Multiple instances per resource type
# ──────────────────────────────────────────────────────────────────────────────

def detect_deadlock_multi(
    allocation: List[List[int]],
    request:    List[List[int]],
    available:  List[int],
) -> tuple[bool, List[int]]:
    """
    Coffman's matrix-based detection algorithm.

    Parameters
    ----------
    allocation : n×m  — resources currently allocated to each process
    request    : n×m  — resources each process is still requesting
    available  : m    — currently available instances of each resource type

    Returns
    -------
    (deadlock_found, list_of_deadlocked_process_indices)
    """
    n = len(allocation)
    m = len(available)

    work   = list(available)          # copy; modified as processes finish
    finish = [False] * n
    log: List[str] = []

    # Processes with no outstanding requests can complete immediately;
    # release their allocations into work so others may proceed.
    for i in range(n):
        if all(request[i][j] == 0 for j in range(m)):
            finish[i] = True
            for j in range(m):
                work[j] += allocation[i][j]   # release their resources
            log.append(f"P{i}: no outstanding requests — marked finished, releases {allocation[i]}")

    changed = True
    while changed:
        changed = False
        for i in range(n):
            if not finish[i]:
                can_run = all(request[i][j] <= work[j] for j in range(m))
                if can_run:
                    # Simulate process completing and releasing resources
                    for j in range(m):
                        work[j] += allocation[i][j]
                    finish[i] = True
                    changed   = True
                    log.append(
                        f"P{i}: needs {request[i]} ≤ work {work} → can run → "
                        f"work becomes {work}"
                    )

    deadlocked = [i for i in range(n) if not finish[i]]

    for d in deadlocked:
        log.append(f"P{d}: DEADLOCKED (finish=False)")

    return (len(deadlocked) > 0), deadlocked


# ──────────────────────────────────────────────────────────────────────────────
# 3. Banker's Algorithm — Safety Check (Avoidance)
#    Time  : O(n² × m)
#    Space : O(n × m)
# ──────────────────────────────────────────────────────────────────────────────

class BankersAlgorithm:
    """
    Dijkstra's Banker's Algorithm for deadlock avoidance.

    The system is in a SAFE state if there exists at least one
    safe sequence <P₁, P₂, …, Pₙ> such that every process can
    eventually finish.
    """

    def __init__(
        self,
        num_processes:  int,
        num_resources:  int,
        max_need:       List[List[int]],
        allocation:     List[List[int]],
        available:      List[int],
    ):
        self.n   = num_processes
        self.m   = num_resources
        self.max = max_need
        self.alloc = allocation
        self.avail = list(available)

        # need[i][j] = max[i][j] – alloc[i][j]
        self.need = [
            [max_need[i][j] - allocation[i][j] for j in range(num_resources)]
            for i in range(num_processes)
        ]

    # ── Safety Algorithm ──────────────────────────────────────────────────────

    def is_safe(self) -> tuple[bool, List[int], List[str]]:
        """
        Run the safety algorithm.

        Returns
        -------
        (safe, safe_sequence, step_log)
        """
        work   = list(self.avail)
        finish = [False] * self.n
        safe_seq: List[int] = []
        log: List[str] = []

        log.append(f"Available (Work) = {work}")

        changed = True
        while changed and len(safe_seq) < self.n:
            changed = False
            for i in range(self.n):
                if not finish[i]:
                    if all(self.need[i][j] <= work[j] for j in range(self.m)):
                        # Pi can complete; release its resources
                        for j in range(self.m):
                            work[j] += self.alloc[i][j]
                        finish[i] = True
                        safe_seq.append(i)
                        changed = True
                        log.append(
                            f"P{i} executes: need={self.need[i]} ≤ work "
                            f"→ releases {self.alloc[i]} → work={work}"
                        )

        is_safe_state = all(finish)
        if is_safe_state:
            log.append(f"SAFE SEQUENCE: {[f'P{p}' for p in safe_seq]}")
        else:
            stuck = [f"P{i}" for i in range(self.n) if not finish[i]]
            log.append(f"UNSAFE STATE — stuck processes: {stuck}")

        return is_safe_state, safe_seq, log

    # ── Resource Request ──────────────────────────────────────────────────────

    def request_resources(
        self,
        process_id: int,
        request:    List[int],
    ) -> tuple[bool, str]:
        """
        Try to grant a resource request and check if result is still safe.

        Returns (granted, reason_string).
        """
        i = process_id

        # Step 1: request ≤ need?
        if any(request[j] > self.need[i][j] for j in range(self.m)):
            return False, f"P{i} exceeds its maximum declared need"

        # Step 2: request ≤ available?
        if any(request[j] > self.avail[j] for j in range(self.m)):
            return False, f"P{i} must wait — insufficient available resources"

        # Step 3: Tentatively allocate
        for j in range(self.m):
            self.avail[j]     -= request[j]
            self.alloc[i][j]  += request[j]
            self.need[i][j]   -= request[j]

        safe, seq, _ = self.is_safe()

        if safe:
            return True, f"Request granted — safe sequence {[f'P{p}' for p in seq]}"
        else:
            # Roll back
            for j in range(self.m):
                self.avail[j]     += request[j]
                self.alloc[i][j]  -= request[j]
                self.need[i][j]   += request[j]
            return False, "Request denied — would lead to unsafe state"

    def get_state(self) -> dict:
        return {
            "allocation": self.alloc,
            "max":        self.max,
            "need":       self.need,
            "available":  self.avail,
        }
