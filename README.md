# Deadlock Detection & Recovery Toolkit
**Operating Systems Project**

## Project Structure

```
deadlock_toolkit/
├── deadlock_detector.py   # Core algorithms: WFG DFS, multi-instance, Banker's
├── rag.py                 # Resource Allocation Graph model & cycle detection
├── recovery.py            # 7 recovery strategies
├── test_all.py            # Complete test suite (run this to verify)
└── index.html             # Interactive visual toolkit (open in browser)
```

## Setup (Python 3.10+)

```bash
# No external packages needed — pure stdlib
python test_all.py
```

## Quick Usage

```python
# Banker's Algorithm
from deadlock_detector import BankersAlgorithm
b = BankersAlgorithm(5, 3,
    max_need   = [[7,5,3],[3,2,2],[9,0,2],[2,2,2],[4,3,3]],
    allocation = [[0,1,0],[2,0,0],[3,0,2],[2,1,1],[0,0,2]],
    available  = [3,3,2])
safe, seq, log = b.is_safe()
print("Safe:", safe, "| Sequence:", [f"P{p}" for p in seq])
```

```python
# Wait-For Graph cycle detection
from deadlock_detector import WaitForGraph
g = WaitForGraph(3)
g.add_edge(0,1); g.add_edge(1,2); g.add_edge(2,0)
found, deadlocked = g.detect_cycle()
print("Deadlock:", found, "| Procs:", deadlocked)
```

```python
# Recovery
import time
from recovery import Process, Resource, apply_recovery
procs = [
    Process(1,'P1',priority=3,timestamp=time.time()-30,holds=[1],wants=[2]),
    Process(2,'P2',priority=2,timestamp=time.time()-20,holds=[2],wants=[1]),
]
ress = [Resource(1,'R1',1,0), Resource(2,'R2',1,0)]
_, _, log = apply_recovery('wait_die', procs, ress, [1,2])
print('\n'.join(log))
```

## Open the UI

Just open `index.html` in any browser — no server required.

## Algorithms

| Algorithm | File | Complexity |
|---|---|---|
| DFS Cycle Detection (WFG) | deadlock_detector.py | O(V+E) |
| Multi-Instance Detection | deadlock_detector.py | O(n²m) |
| Banker's Safety Algorithm | deadlock_detector.py | O(n²m) |
| RAG Cycle Detection | rag.py | O(V+E) |
| WFG Projection from RAG | rag.py | O(E²) |

## Recovery Strategies

| Key | Strategy |
|---|---|
| `terminate_all` | Kill all deadlocked processes |
| `terminate_one` | Kill one at a time (min-cost victim) |
| `preemption` | Forcibly take resources from victim |
| `rollback` | Checkpoint rollback |
| `wait_die` | Timestamp: older waits, younger dies |
| `wound_wait` | Timestamp: older wounds younger |
| `priority_victim` | Cost-function victim selection |
