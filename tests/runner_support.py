"""Shared setup for the runner's tests: stand-ins for processes a test started. Later
tasks add the engine's stand-ins here as the runner grows."""
import os
import signal
import time
from pathlib import Path

import helpers  # noqa: F401  puts the core on the import path


# --- processes a test started ------------------------------------------------------------

# A command that leaves a sleep behind holding its output open, writes its own process ID
# and the sleep's to the file it is given, and waits.
LEAVES = ('sleep 300 &\nprintf "%s\\n%s\\n" $$ $! > "$1.part" && mv "$1.part" "$1"\n'
          'sleep 300\n')


def gone(pid: int) -> bool:
    """True when a process has ended, whether or not anything has collected it yet."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:
        state = Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()[0]
    except (OSError, IndexError):
        return False
    return state == 'Z'


def still_running(pids, seconds: float = 5) -> list[int]:
    """Those of `pids` still running after up to `seconds`. Each is killed then, so that
    no test leaves a process behind whatever it finds."""
    deadline = time.monotonic() + seconds
    while True:
        left = [pid for pid in pids if not gone(pid)]
        if not left or time.monotonic() >= deadline:
            break
        time.sleep(0.05)
    for pid in left:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return left


def written(path: Path, seconds: float = 10) -> list[int]:
    """The process IDs a command writes to a file, one a line, once it has written them."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            text = path.read_text()
        except OSError:
            text = ''
        if text.endswith('\n'):
            return [int(line) for line in text.split()]
        time.sleep(0.02)
    raise AssertionError(f'Nothing was written to {path}.')


