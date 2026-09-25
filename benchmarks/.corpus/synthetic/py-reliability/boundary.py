import logging
import queue
import threading
from typing import Callable

log = logging.getLogger(__name__)


def run_jobs(jobs: queue.Queue, handler: Callable[[object], None], stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            job = jobs.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            handler(job)
        except Exception:
            log.warning("job handler failed; worker continues", exc_info=True)
        finally:
            jobs.task_done()
