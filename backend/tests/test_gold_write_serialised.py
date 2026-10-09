"""Two runs must never write through the writer at the same time.

The writer holds ONE live connection. Four clients recalculated at once
interleaved statements on it: one run's manifest insert was lost to another's
reconnect, so a client's current Gold rows carried a run id with no manifest
(validation 9.7) while its latest run pointed at rows no longer current.
"""
from __future__ import annotations

import threading
import time

from infrastructure.persistence.warehouse_gold import GoldWriter


def test_concurrent_write_runs_do_not_overlap(monkeypatch):
    writer = GoldWriter(connection=object())
    inside = 0
    overlapped = []
    lock = threading.Lock()

    def slow_write(self, payload):
        nonlocal inside
        with lock:
            inside += 1
            overlapped.append(inside > 1)
        time.sleep(0.05)
        with lock:
            inside -= 1
        return {"run": payload["run_id"]}

    monkeypatch.setattr(GoldWriter, "_write_run", slow_write)
    results = []
    threads = [
        threading.Thread(target=lambda i=i: results.append(writer.write_run({"run_id": i})))
        for i in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 4
    assert not any(overlapped), "two runs were inside the writer at once"
