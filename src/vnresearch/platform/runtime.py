"""A bounded SQLite dispatcher. Running attempts are never replayed on restart."""
import threading
import time
import uuid
import sqlite3

from vnresearch.platform.jobs import StateConflict


class JobCancelled(RuntimeError):
    pass


class Dispatcher:
    def __init__(self, store, workers, execute, *, maintenance=None, maintenance_interval=60):
        if maintenance_interval <= 0:
            raise ValueError("Khoảng thời gian bảo trì phải dương")
        self.store, self.execute = store, execute
        self.maintenance, self.maintenance_interval = maintenance, maintenance_interval
        self.maintenance_healthy = True
        self.instance_id = uuid.uuid4().hex
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.threads = [threading.Thread(target=self._work, name=f"vnresearch-worker-{i}", daemon=True)
                        for i in range(workers)]
        if maintenance:
            self.threads.append(threading.Thread(target=self._maintain, name="vnresearch-maintenance", daemon=True))
        self.last_poll = time.monotonic()

    def start(self):
        for thread in self.threads:
            thread.start()

    def notify(self):
        self.wake_event.set()

    def _work(self):
        while not self.stop_event.is_set():
            try:
                job = self.store.claim_next(self.instance_id)
                self.last_poll = time.monotonic()
                if job:
                    self.execute(job, self.instance_id, self.stop_event)
                    continue
            except (OSError, RuntimeError, sqlite3.Error):
                if self.stop_event.wait(0.2):
                    break
            self.wake_event.wait(0.2)
            self.wake_event.clear()

    def _maintain(self):
        while not self.stop_event.wait(self.maintenance_interval):
            try:
                self.maintenance()
                self.maintenance_healthy = True
            except (OSError, RuntimeError, sqlite3.Error):
                self.maintenance_healthy = False

    def close(self, timeout=30):
        self.stop_event.set()
        self.wake_event.set()
        deadline = time.monotonic() + timeout
        for thread in self.threads:
            thread.join(max(0, deadline - time.monotonic()))
        return not any(thread.is_alive() for thread in self.threads)

    @property
    def ready(self):
        return (bool(self.threads) and all(thread.is_alive() for thread in self.threads)
                and self.maintenance_healthy and not self.stop_event.is_set())


def progress_callback(store, job_id, worker_id, stop_event):
    def progress(phase, percent):
        if stop_event.is_set() or store.cancellation_requested(job_id):
            raise JobCancelled("Tác vụ dừng tại ranh giới giai đoạn")
        try:
            store.update(job_id, "running", phase, percent, worker_id=worker_id)
        except StateConflict as exc:
            raise JobCancelled("Tác vụ không còn thuộc worker") from exc
    return progress
