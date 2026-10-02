"""Background loop: starts scheduled campaigns, sends queued messages at a safe pace, runs the automatic
campaigns, and marks customers dormant daily."""

import logging
import threading
import time

from app.automations import run_automations
from app.campaigns import process_batch, start_due
from app.config import get_settings
from app.db import SessionLocal
from app.status import sweep_dormant

log = logging.getLogger("kgl.worker")
TICK_SECONDS = 2.0


class Worker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="kgl-worker", daemon=True)
        self._last_sweep_day: str | None = None
        self._last_automation_run = 0.0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def tick(self) -> None:
        settings = get_settings()
        batch = max(1, int(settings.send_rate_per_second * TICK_SECONDS))
        with SessionLocal() as db:
            start_due(db)
            today = time.strftime("%Y-%m-%d")
            if self._last_sweep_day != today:
                changed = sweep_dormant(db)
                self._last_sweep_day = today
                if changed:
                    log.info("Marked %s customers dormant", changed)
            if time.monotonic() - self._last_automation_run >= settings.automation_interval_seconds:
                self._last_automation_run = time.monotonic()
                queued = run_automations(db)
                if queued:
                    log.info("Automations queued %s messages", queued)
            process_batch(db, limit=batch)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # keep the loop alive; one bad row must not stop all sending
                log.exception("Worker tick failed")
            self._stop.wait(TICK_SECONDS)
