"""
recovery.py
===========
Deadlock recovery strategies.

Strategies implemented:
  1.  TerminateAll       — kill every deadlocked process at once
  2.  TerminateOneByOne  — kill one, re-detect, repeat
  3.  ResourcePreemption — steal resources from a victim
  4.  CheckpointRollback — roll process back to last checkpoint
  5.  WaitDie            — timestamp-based (older waits, younger aborts)
  6.  WoundWait          — timestamp-based (older preempts, younger waits)
  7.  PriorityVictim     — select victim by minimum-cost heuristic
"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable
import time


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Process:
    pid:        int
    name:       str
    priority:   int          # higher = more important
    timestamp:  float        # creation / admission time
    holds:      List[int] = field(default_factory=list)   # resource ids held
    wants:      List[int] = field(default_factory=list)   # resource ids wanted
    checkpoint: Optional[dict] = None                     # last saved state
    status:     str = "running"                           # running|blocked|killed|waiting

    def __repr__(self):
        return (f"Process(pid={self.pid}, name={self.name!r}, "
                f"priority={self.priority}, status={self.status})")


@dataclass
class Resource:
    rid:       int
    name:      str
    instances: int
    available: int

    def __repr__(self):
        return f"Resource(rid={self.rid}, name={self.name!r}, avail={self.available}/{self.instances})"


# ──────────────────────────────────────────────────────────────────────────────
# Recovery base class
# ──────────────────────────────────────────────────────────────────────────────

class RecoveryStrategy:
    """Abstract base — all strategies inherit from this."""

    name: str = "Base"

    def recover(
        self,
        processes:  List[Process],
        resources:  List[Resource],
        deadlocked: List[int],           # pids of deadlocked processes
    ) -> tuple[List[Process], List[Resource], List[str]]:
        """
        Apply recovery.

        Returns
        -------
        (updated_processes, updated_resources, event_log)
        """
        raise NotImplementedError

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _release(proc: Process, resources: List[Resource]) -> List[str]:
        """Release all resources held by a process."""
        log = []
        for rid in list(proc.holds):
            for r in resources:
                if r.rid == rid:
                    r.available = min(r.instances, r.available + 1)
                    log.append(f"  Released {r.name} (rid={rid}) from P{proc.pid}")
        proc.holds.clear()
        proc.wants.clear()
        return log

    @staticmethod
    def _find(lst, key, val):
        return next((x for x in lst if getattr(x, key) == val), None)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Terminate All
# ──────────────────────────────────────────────────────────────────────────────

class TerminateAll(RecoveryStrategy):
    """Abort every deadlocked process simultaneously."""

    name = "Terminate All Deadlocked Processes"

    def recover(self, processes, resources, deadlocked):
        log = [
            "[ACTION] Strategy: Terminate All",
            f"[DETECT] Deadlocked PIDs: {deadlocked}",
        ]
        for pid in deadlocked:
            proc = self._find(processes, "pid", pid)
            if proc:
                log += self._release(proc, resources)
                proc.status = "killed"
                log.append(f"[KILL]   P{pid} ({proc.name}) terminated")

        log.append("[OK]     All deadlocked processes killed. Resources reclaimed.")
        return processes, resources, log


# ──────────────────────────────────────────────────────────────────────────────
# 2. Terminate One-by-One
# ──────────────────────────────────────────────────────────────────────────────

class TerminateOneByOne(RecoveryStrategy):
    """
    Kill cheapest victim, re-run detection, repeat until no deadlock.
    Victim selected by: minimum resources held (least work lost).
    """

    name = "Terminate One-by-One (Minimum Cost)"

    def recover(self, processes, resources, deadlocked):
        log = ["[ACTION] Strategy: Terminate One-by-One"]

        remaining = list(deadlocked)
        round_n = 1

        while remaining:
            log.append(f"\n[ROUND {round_n}] Deadlocked: {remaining}")

            # Pick victim: fewest resources held
            victims = [self._find(processes, "pid", p) for p in remaining]
            victims = [v for v in victims if v]
            victim  = min(victims, key=lambda p: len(p.holds))

            log.append(f"[VICTIM] P{victim.pid} ({victim.name}) — "
                       f"holds {len(victim.holds)} resource(s)")
            log += self._release(victim, resources)
            victim.status = "killed"
            log.append(f"[KILL]   P{victim.pid} terminated")

            remaining.remove(victim.pid)

            # Simulate re-detection: check if remaining can now proceed
            freed = True
            for pid in list(remaining):
                proc = self._find(processes, "pid", pid)
                if proc and all(
                    any(r.rid == rid and r.available > 0 for r in resources)
                    for rid in proc.wants
                ):
                    proc.status = "running"
                    proc.wants.clear()
                    remaining.remove(pid)
                    log.append(f"[UNBLOCK] P{pid} ({proc.name}) can now proceed")

            round_n += 1

        log.append("\n[OK]     Deadlock fully resolved.")
        return processes, resources, log


# ──────────────────────────────────────────────────────────────────────────────
# 3. Resource Preemption
# ──────────────────────────────────────────────────────────────────────────────

class ResourcePreemption(RecoveryStrategy):
    """
    Forcibly take resources from a victim process.
    Victim selected by: lowest priority among deadlocked processes.
    Preempted process is rolled back to waiting state (not killed).
    """

    name = "Resource Preemption (Lowest Priority Victim)"

    def recover(self, processes, resources, deadlocked):
        log = ["[ACTION] Strategy: Resource Preemption"]

        dead_procs = [self._find(processes, "pid", p) for p in deadlocked]
        dead_procs = [p for p in dead_procs if p]

        if not dead_procs:
            log.append("[WARN]   No deadlocked processes found.")
            return processes, resources, log

        # Victim = lowest priority (most expendable)
        victim = min(dead_procs, key=lambda p: p.priority)
        log.append(f"[VICTIM] P{victim.pid} ({victim.name}) — "
                   f"priority={victim.priority}, holds={victim.holds}")

        preempted_resources = list(victim.holds)
        log += self._release(victim, resources)
        victim.status = "waiting"    # not killed — will retry later
        log.append(f"[PREEMPT] Resources {preempted_resources} preempted from P{victim.pid}")

        # Try to unblock other deadlocked processes
        unblocked = []
        for pid in deadlocked:
            if pid == victim.pid:
                continue
            proc = self._find(processes, "pid", pid)
            if proc:
                can_satisfy = all(
                    any(r.rid == rid and r.available > 0 for r in resources)
                    for rid in proc.wants
                )
                if can_satisfy:
                    for rid in proc.wants:
                        for r in resources:
                            if r.rid == rid and r.available > 0:
                                r.available -= 1
                                proc.holds.append(rid)
                                break
                    proc.status = "running"
                    proc.wants.clear()
                    unblocked.append(pid)
                    log.append(f"[ASSIGN] P{pid} ({proc.name}) received preempted resources → running")

        if not unblocked:
            log.append("[INFO]   Resources freed. Will be assigned on next request.")

        log.append(f"\n[NOTE]   P{victim.pid} will be re-scheduled when resources available.")
        log.append("[OK]     Preemption complete.")
        return processes, resources, log


# ──────────────────────────────────────────────────────────────────────────────
# 4. Checkpoint Rollback
# ──────────────────────────────────────────────────────────────────────────────

class CheckpointRollback(RecoveryStrategy):
    """
    Roll each deadlocked process back to its last safe checkpoint.
    Requires processes to have a saved checkpoint state.
    """

    name = "Checkpoint / Rollback"

    def recover(self, processes, resources, deadlocked):
        log = ["[ACTION] Strategy: Checkpoint Rollback"]

        for pid in deadlocked:
            proc = self._find(processes, "pid", pid)
            if not proc:
                continue

            if proc.checkpoint:
                log += self._release(proc, resources)

                # Restore from checkpoint
                saved = proc.checkpoint
                proc.holds  = list(saved.get("holds", []))
                proc.wants  = list(saved.get("wants", []))
                proc.status = "running"

                # Re-allocate checkpoint resources
                for rid in proc.holds:
                    for r in resources:
                        if r.rid == rid and r.available > 0:
                            r.available -= 1

                log.append(f"[ROLLBACK] P{pid} ({proc.name}) restored to "
                           f"checkpoint — holds={proc.holds}, wants={proc.wants}")
            else:
                log += self._release(proc, resources)
                proc.status = "killed"
                log.append(f"[KILL]   P{pid} ({proc.name}) — no checkpoint, terminated")

        log.append("[OK]     Rollback complete. Reissue requests with ordering.")
        return processes, resources, log


# ──────────────────────────────────────────────────────────────────────────────
# 5. Wait-Die
# ──────────────────────────────────────────────────────────────────────────────

class WaitDie(RecoveryStrategy):
    """
    Timestamp-based protocol (non-preemptive).

    If Pi wants a resource held by Pj:
      - Ti < Tj  (Pi is older) → Pi WAITS
      - Ti ≥ Tj  (Pi is younger) → Pi DIES (is aborted and will restart)
    """

    name = "Wait-Die (Timestamp)"

    def recover(self, processes, resources, deadlocked):
        log = [
            "[ACTION] Strategy: Wait-Die",
            "[INFO]   Rule: older waits, younger dies",
        ]

        ts_map = {p.pid: p.timestamp for p in processes}
        for pid in deadlocked:
            log.append(f"  P{pid}: timestamp={ts_map[pid]:.2f}")

        for pid in deadlocked:
            proc = self._find(processes, "pid", pid)
            if not proc:
                continue

            # Find the process holding what `proc` wants
            for wanted_rid in proc.wants:
                holder = next(
                    (p for p in processes if wanted_rid in p.holds and p.pid != pid),
                    None
                )
                if holder is None:
                    continue

                if proc.timestamp < holder.timestamp:
                    # Pi is older — waits
                    proc.status = "waiting"
                    log.append(f"[WAIT]   P{pid} (t={proc.timestamp:.2f}) older than "
                               f"P{holder.pid} (t={holder.timestamp:.2f}) → P{pid} waits")
                else:
                    # Pi is younger — dies, will restart later
                    log += self._release(proc, resources)
                    proc.status = "killed"
                    log.append(f"[DIE]    P{pid} (t={proc.timestamp:.2f}) younger than "
                               f"P{holder.pid} (t={holder.timestamp:.2f}) → P{pid} aborted")
                break

        log.append("[OK]     Wait-Die protocol applied.")
        return processes, resources, log


# ──────────────────────────────────────────────────────────────────────────────
# 6. Wound-Wait
# ──────────────────────────────────────────────────────────────────────────────

class WoundWait(RecoveryStrategy):
    """
    Timestamp-based protocol (preemptive).

    If Pi wants a resource held by Pj:
      - Ti < Tj  (Pi is older) → Pi WOUNDS Pj (Pj is preempted, Pi gets resource)
      - Ti ≥ Tj  (Pi is younger) → Pi WAITS
    """

    name = "Wound-Wait (Timestamp)"

    def recover(self, processes, resources, deadlocked):
        log = [
            "[ACTION] Strategy: Wound-Wait",
            "[INFO]   Rule: older wounds younger, younger waits",
        ]

        for pid in deadlocked:
            proc = self._find(processes, "pid", pid)
            if not proc:
                continue

            for wanted_rid in proc.wants:
                holder = next(
                    (p for p in processes if wanted_rid in p.holds and p.pid != pid),
                    None
                )
                if holder is None:
                    continue

                if proc.timestamp < holder.timestamp:
                    # Pi older → wounds Pj (preempt resource)
                    res = self._find(resources, "rid", wanted_rid)
                    holder.holds.remove(wanted_rid)
                    holder.status = "waiting"
                    holder.wants.insert(0, wanted_rid)
                    if res:
                        res.available += 1

                    # Now give to Pi
                    if res and res.available > 0:
                        res.available -= 1
                        proc.holds.append(wanted_rid)
                    proc.wants.remove(wanted_rid)
                    proc.status = "running"

                    log.append(f"[WOUND]  P{proc.pid} (t={proc.timestamp:.2f}) wounds "
                               f"P{holder.pid} (t={holder.timestamp:.2f}) — "
                               f"R{wanted_rid} preempted")
                else:
                    # Pi younger → waits
                    proc.status = "waiting"
                    log.append(f"[WAIT]   P{proc.pid} (t={proc.timestamp:.2f}) younger → waits")
                break

        log.append("[OK]     Wound-Wait protocol applied.")
        return processes, resources, log


# ──────────────────────────────────────────────────────────────────────────────
# 7. Priority-based Victim Selection
# ──────────────────────────────────────────────────────────────────────────────

class PriorityVictim(RecoveryStrategy):
    """
    Select victim by a cost function that considers:
      - Process priority (lower = cheaper to kill)
      - Resources held (more resources = higher cost to kill)
      - Age (younger = cheaper)
    """

    name = "Priority-Based Victim Selection"

    @staticmethod
    def _cost(proc: Process) -> float:
        """Lower score = better victim (cheaper to kill)."""
        return (
            proc.priority * 10
            + len(proc.holds) * 5
            + (time.time() - proc.timestamp)     # age bonus: older = costlier
        )

    def recover(self, processes, resources, deadlocked):
        log = ["[ACTION] Strategy: Priority-Based Victim Selection"]

        dead_procs = [
            p for p in processes if p.pid in deadlocked
        ]

        costs = {p.pid: self._cost(p) for p in dead_procs}
        log.append("[COSTS]  Victim cost scores:")
        for pid, cost in sorted(costs.items(), key=lambda x: x[1]):
            log.append(f"  P{pid}: cost={cost:.1f}")

        victim = min(dead_procs, key=self._cost)
        log.append(f"\n[VICTIM] P{victim.pid} ({victim.name}) — "
                   f"cost={costs[victim.pid]:.1f} (minimum)")

        log += self._release(victim, resources)
        victim.status = "killed"
        log.append(f"[KILL]   P{victim.pid} terminated")

        # Unblock remaining if possible
        for pid in deadlocked:
            if pid == victim.pid:
                continue
            proc = self._find(processes, "pid", pid)
            if proc:
                can = all(
                    any(r.rid == rid and r.available > 0 for r in resources)
                    for rid in proc.wants
                )
                if can:
                    for rid in proc.wants:
                        for r in resources:
                            if r.rid == rid and r.available > 0:
                                r.available -= 1
                                proc.holds.append(rid)
                                break
                    proc.status = "running"
                    proc.wants.clear()
                    log.append(f"[RESUME] P{pid} ({proc.name}) unblocked and running")

        log.append("[OK]     Priority-based recovery complete.")
        return processes, resources, log


# ──────────────────────────────────────────────────────────────────────────────
# Registry — maps strategy name to class
# ──────────────────────────────────────────────────────────────────────────────

STRATEGIES: dict[str, type[RecoveryStrategy]] = {
    "terminate_all":    TerminateAll,
    "terminate_one":    TerminateOneByOne,
    "preemption":       ResourcePreemption,
    "rollback":         CheckpointRollback,
    "wait_die":         WaitDie,
    "wound_wait":       WoundWait,
    "priority_victim":  PriorityVictim,
}


def apply_recovery(
    strategy_key: str,
    processes:    List[Process],
    resources:    List[Resource],
    deadlocked:   List[int],
) -> tuple[List[Process], List[Resource], List[str]]:
    """
    Public API: apply a named strategy and return updated state + log.
    """
    cls = STRATEGIES.get(strategy_key)
    if cls is None:
        raise ValueError(f"Unknown strategy: {strategy_key!r}. "
                         f"Available: {list(STRATEGIES.keys())}")
    strategy = cls()
    return strategy.recover(processes, resources, deadlocked)
