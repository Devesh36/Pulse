"""Exit a Pulse child if its owning terminal process disappears."""

import os
import signal
import threading
from contextlib import contextmanager


@contextmanager
def parent_guard():
    owner = os.getenv("PULSE_SESSION_OWNER")
    if not owner:
        yield
        return
    expected = int(owner)
    finished = threading.Event()

    def supervise():
        while not finished.wait(1):
            if os.getppid() != expected:
                os.kill(os.getpid(), signal.SIGTERM)
                return

    task = threading.Thread(target=supervise, daemon=True, name="pulse-session-owner")
    task.start()
    try:
        yield
    finally:
        finished.set()
        task.join(timeout=2)
