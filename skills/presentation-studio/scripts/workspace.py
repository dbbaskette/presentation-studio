"""What every part of Presentation Studio shares: the refusal a person reads, and safe writes."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

STATE_DIR = '.presentation-studio'
SKILL_DIR = Path(__file__).resolve().parent.parent
CHECKOUT_MARK = Path('skills') / 'presentation-studio' / 'SKILL.md'


class WorkspaceError(Exception):
    """A refusal or failure, said in one sentence a person can read as it is."""


def write_atomic(path: Path, text: str) -> None:
    """Write text so a reader sees the old file or the new one, never half of either."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            out.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
