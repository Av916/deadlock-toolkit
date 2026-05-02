"""
test_all.py
===========
Run all tests for the Deadlock Detection & Recovery Toolkit.

Usage:
    python test_all.py
"""

import sys
import time

# ── colour helpers ────────────────────────────────────────────────────────────
GRN  = "\033[92m"
RED  = "\033[91m"
YEL  = "\033[93m"
CYN  = "\033[96m"
BOLD = "\033[1m"
RST  = "\033[0m"

passed = 0
failed = 0

def ok(msg):
    global passed
    passed += 1
    print(f"  {GRN}✓{RST}  {msg}")

def fail(msg, err=""):
    global failed
    failed += 1
    print(f"  {RED}✗{RST}  {msg}")
    if err:
        print(f"     {RED}{err}{RST}")

def header(title):
    print(f"\n{BOLD}{CYN}── {title} {'─'*(52-len(title))}{RST}")

# ══════════════════════════════════════════════════════════════════════════════
# 1. Wait-For Graph
# ══════════════════════════════════════════════════════════════════════════════
header("Wait-For Graph (DFS Cycle Detection)")

from deadlock_detector import WaitForGraph

try:
    g = WaitForGraph(4)
    g.add_edge(0, 1)
    g.add_edge(1, 2)
    g.add_edge(2, 0)     # cycle: 0→1→2→0
    found, dl = g.detect_cycle()
    assert found, "should detect cycle"
    assert set(dl) == {0, 1, 2}, f"expected {{0,1,2}}, got {set(dl)}"
    ok("Cycle detection: 3-node circle (P0→P1→P2→P0)")
except Exception as e:
    fail("Cycle detection: 3-node circle", str(e))

try:
    g2 = WaitForGraph(4)
    g2.add_edge(0, 1)
    g2.add_edge(1, 2)
    g2.add_edge(2, 3)    # linear chain — no cycle
    found2, _ = g2.detect_cycle()
    assert not found2, "should NOT detect cycle"
    ok("No cycle: linear chain P0→P1→P2→P3")
except Exception as e:
    fail("No cycle: linear chain", str(e))

try:
    g3 = WaitForGraph(5)
    g3.add_edge(0, 1); g3.add_edge(1, 2)
    g3.add_edge(3, 4)    # two disconnected components, no cycle
    found3, _ = g3.detect_cycle()
    assert not found3
    ok("No cycle: disconnected components")
except Exception as e:
    fail("No cycle: disconnected components", str(e))

try:
    g4 = WaitForGraph(5)
    g4.add_edge(0, 1); g4.add_edge(1, 2)
    g4.add_edge(3, 4); g4.add_edge(4, 3)   # cycle only in component 2
    found4, dl4 = g4.detect_cycle()
    assert found4
    assert set(dl4) == {3, 4}
    ok("Partial cycle: only one component deadlocked {P3, P4}")
except Exception as e:
    fail("Partial cycle detection", str(e))

# ══════════════════════════════════════════════════════════════════════════════
# 2. Multi-Instance Detection
# ══════════════════════════════════════════════════════════════════════════════
header("Multi-Instance Deadlock Detection")

from deadlock_detector import detect_deadlock_multi

try:
    # Classic Silberschatz example — no deadlock
    alloc    = [[0,1,0],[2,0,0],[3,0,3],[2,1,1],[0,0,2]]
    request  = [[0,0,0],[2,0,2],[0,0,0],[1,0,0],[0,0,2]]
    avail    = [0,0,0]
    found, dl = detect_deadlock_multi(alloc, request, avail)
    assert not found, f"should NOT be deadlocked, got {dl}"
    ok("No deadlock: Silberschatz 5-process example (avail=[0,0,0])")
except Exception as e:
    fail("No deadlock: Silberschatz example", str(e))

try:
    # Force deadlock: every process wants what others hold
    alloc2   = [[1,0],[0,1]]
    request2 = [[0,1],[1,0]]
    avail2   = [0,0]
    found2, dl2 = detect_deadlock_multi(alloc2, request2, avail2)
    assert found2
    assert set(dl2) == {0, 1}
    ok("Deadlock: 2-process, 2-resource circular hold-and-wait")
except Exception as e:
    fail("Deadlock: 2-process circular", str(e))

try:
    alloc3   = [[0,0],[0,0]]
    request3 = [[0,0],[0,0]]
    avail3   = [3,3]
    found3, _ = detect_deadlock_multi(alloc3, request3, avail3)
    assert not found3
    ok("No deadlock: all processes have no outstanding requests")
except Exception as e:
    fail("No deadlock: no outstanding requests", str(e))

# ══════════════════════════════════════════════════════════════════════════════
# 3. Banker's Algorithm
# ══════════════════════════════════════════════════════════════════════════════
header("Banker's Algorithm (Safety Check)")

from deadlock_detector import BankersAlgorithm

try:
    alloc = [[0,1,0],[2,0,0],[3,0,2],[2,1,1],[0,0,2]]
    maxn  = [[7,5,3],[3,2,2],[9,0,2],[2,2,2],[4,3,3]]
    avail = [3,3,2]
    b = BankersAlgorithm(5, 3, maxn, alloc, avail)
    safe, seq, log = b.is_safe()
    assert safe, "should be safe"
    assert len(seq) == 5, "safe sequence should have all 5 processes"
    ok(f"Safe state: sequence = {[f'P{p}' for p in seq]}")
except Exception as e:
    fail("Safe state: classic 5-process example", str(e))

try:
    # Unsafe: reduce available to [0,0,0]
    alloc2 = [[1,0,0],[0,1,0]]
    maxn2  = [[2,2,2],[2,2,2]]
    avail2 = [0,0,0]
    b2     = BankersAlgorithm(2, 3, maxn2, alloc2, avail2)
    safe2, seq2, _ = b2.is_safe()
    assert not safe2
    ok("Unsafe state: insufficient available resources")
except Exception as e:
    fail("Unsafe state detection", str(e))

try:
    # Resource request — granted
    alloc3 = [[0,1,0],[2,0,0],[3,0,2],[2,1,1],[0,0,2]]
    maxn3  = [[7,5,3],[3,2,2],[9,0,2],[2,2,2],[4,3,3]]
    avail3 = [3,3,2]
    b3 = BankersAlgorithm(5, 3, maxn3, alloc3, avail3)
    granted, msg = b3.request_resources(1, [1,0,2])
    assert granted, f"request should be granted: {msg}"
    ok(f"Resource request granted: P1 requests [1,0,2]")
except Exception as e:
    fail("Resource request grant", str(e))

try:
    alloc4 = [[0,1,0],[2,0,0],[3,0,2],[2,1,1],[0,0,2]]
    maxn4  = [[7,5,3],[3,2,2],[9,0,2],[2,2,2],[4,3,3]]
    avail4 = [3,3,2]
    b4 = BankersAlgorithm(5, 3, maxn4, alloc4, avail4)
    granted4, msg4 = b4.request_resources(0, [0,6,0])   # exceeds need
    assert not granted4
    ok("Resource request denied: exceeds maximum need")
except Exception as e:
    fail("Resource request denial", str(e))

# ══════════════════════════════════════════════════════════════════════════════
# 4. Resource Allocation Graph
# ══════════════════════════════════════════════════════════════════════════════
header("Resource Allocation Graph")

from rag import ResourceAllocationGraph, make_deadlock_example, make_safe_example

try:
    g = make_deadlock_example()
    found, cycle = g.detect_deadlock()
    assert found, "should detect deadlock"
    dp = g.deadlocked_processes()
    assert len(dp) > 0
    ok(f"Deadlock preset: cycle detected, deadlocked procs = {dp}")
except Exception as e:
    fail("RAG deadlock preset", str(e))

try:
    g2 = make_safe_example()
    found2, _ = g2.detect_deadlock()
    assert not found2
    ok("Safe preset: no cycle in graph")
except Exception as e:
    fail("RAG safe preset", str(e))

try:
    g3 = ResourceAllocationGraph()
    g3.add_process(1, "P1"); g3.add_process(2, "P2")
    g3.add_resource(1, instances=1, label="R1")
    g3.allocate("R1", "P1")
    g3.request("P2", "R1")     # P2 waits for R1 held by P1
    wfg = g3.to_wait_for_graph()
    # P2 should wait for P1
    assert "P1" in wfg.get("P2", []), f"WFG: P2 should wait for P1, got {wfg}"
    ok("Wait-For Graph projection: P2→P1 correctly derived")
except Exception as e:
    fail("WFG projection", str(e))

try:
    g4 = ResourceAllocationGraph()
    g4.add_process(1,"P1"); g4.add_process(2,"P2")
    g4.add_resource(1, instances=2, label="R1")
    ok1 = g4.allocate("R1","P1")
    ok2 = g4.allocate("R1","P2")
    ok3 = g4.allocate("R1","P2")  # should fail — only 2 instances
    assert ok1 and ok2 and not ok3
    ok("Multi-instance allocation: correctly blocks over-allocation")
except Exception as e:
    fail("Multi-instance over-allocation", str(e))

try:
    g5 = ResourceAllocationGraph()
    g5.add_process(1,"P1"); g5.add_process(2,"P2"); g5.add_process(3,"P3")
    g5.add_resource(1,instances=1,label="R1"); g5.add_resource(2,instances=1,label="R2")
    g5.allocate("R1","P1"); g5.allocate("R2","P2")
    g5.request("P2","R1"); g5.request("P1","R2")
    found5, _ = g5.detect_deadlock()
    assert found5
    ok("RAG manual build: cycle P1⇌P2 detected correctly")
except Exception as e:
    fail("RAG manual cycle", str(e))

try:
    d = g5.to_dict()
    assert 'processes' in d and 'resources' in d and 'edges' in d
    ok("RAG serialization to dict: all keys present")
except Exception as e:
    fail("RAG serialization", str(e))

# ══════════════════════════════════════════════════════════════════════════════
# 5. Recovery Strategies
# ══════════════════════════════════════════════════════════════════════════════
header("Recovery Strategies")

from recovery import (
    Process, Resource, apply_recovery,
    TerminateAll, TerminateOneByOne, ResourcePreemption,
    CheckpointRollback, WaitDie, WoundWait, PriorityVictim,
    STRATEGIES
)

def make_test_procs():
    now = time.time()
    return [
        Process(1, 'DB Writer',    priority=3, timestamp=now-30, holds=[1], wants=[2]),
        Process(2, 'File Handler', priority=2, timestamp=now-20, holds=[2], wants=[3]),
        Process(3, 'Net Daemon',   priority=1, timestamp=now-10, holds=[3], wants=[1]),
        Process(4, 'User Shell',   priority=5, timestamp=now-5,  holds=[4], wants=[]),
    ]

def make_test_resources():
    return [
        Resource(1,'R1',instances=1,available=0),
        Resource(2,'R2',instances=1,available=0),
        Resource(3,'R3',instances=1,available=0),
        Resource(4,'R4',instances=1,available=1),
    ]

for key in STRATEGIES:
    try:
        procs = make_test_procs()
        ress  = make_test_resources()
        p_out, r_out, log = apply_recovery(key, procs, ress, [1,2,3])
        assert isinstance(log, list) and len(log) > 0
        ok(f"Strategy '{key}': returns valid log with {len(log)} entries")
    except Exception as e:
        fail(f"Strategy '{key}'", str(e))

try:
    apply_recovery('nonexistent', [], [], [])
    fail("Unknown strategy: should have raised ValueError")
except ValueError:
    ok("Unknown strategy key raises ValueError correctly")
except Exception as e:
    fail("Unknown strategy error type", str(e))

try:
    procs = make_test_procs()
    procs[0].checkpoint = {'holds': [1], 'wants': []}
    ress  = make_test_resources()
    p_out, r_out, log = apply_recovery('rollback', procs, ress, [1,2,3])
    cp_proc = next(p for p in p_out if p.pid == 1)
    assert cp_proc.status in ('running', 'killed')
    ok("Checkpoint rollback: process with checkpoint is restored correctly")
except Exception as e:
    fail("Checkpoint rollback state", str(e))

try:
    procs = make_test_procs()
    ress  = make_test_resources()
    _, _, log = apply_recovery('terminate_all', procs, ress, [1,2,3])
    killed = [p for p in procs if p.pid in [1,2,3] and p.status=='killed']
    assert len(killed) == 3
    ok("Terminate all: all 3 deadlocked processes killed")
except Exception as e:
    fail("Terminate all: kill count", str(e))

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
total = passed + failed
print(f"\n{'═'*58}")
if failed == 0:
    print(f"{BOLD}{GRN}  ALL {total} TESTS PASSED ✓{RST}")
else:
    print(f"{BOLD}  {GRN}{passed} passed{RST}  {RED}{failed} failed{RST}  of {total} total")
print(f"{'═'*58}\n")

sys.exit(0 if failed == 0 else 1)
