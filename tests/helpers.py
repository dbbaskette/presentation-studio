"""Shared test setup: import path, a private data folder and a quiet git."""
import os
import sys
import tempfile
from pathlib import Path

# Nothing a test does may touch the real per-user data folder.
_DATA = tempfile.TemporaryDirectory()
os.environ['PRESENTATION_STUDIO_DATA'] = _DATA.name

# After a commit, a fetch or a push, git starts auto-gc and maintenance in the background. That
# work can still be writing when a test's temporary directory is removed, which fails the
# removal. GIT_CONFIG_COUNT reaches every git a test starts itself, but for a push to a local
# path git drops it before it starts receive-pack, so the receiving repository never reads it.
# GIT_CONFIG_GLOBAL does reach receive-pack, so every gitconfig a test uses carries these too:
# the one below, and each one a test writes through gitconfig().
QUIET_GIT = {'maintenance.auto': 'false', 'gc.auto': '0', 'receive.autogc': 'false'}
for _index, (_key, _value) in enumerate(QUIET_GIT.items()):
    os.environ[f'GIT_CONFIG_KEY_{_index}'] = _key
    os.environ[f'GIT_CONFIG_VALUE_{_index}'] = _value
os.environ['GIT_CONFIG_COUNT'] = str(len(QUIET_GIT))


def gitconfig(path: Path, text: str = '') -> Path:
    """Write a gitconfig for GIT_CONFIG_GLOBAL to name: the text given, then the settings
    that keep git from working in the background."""
    quiet = ''.join(f'[{key.partition(".")[0]}]\n\t{key.partition(".")[2]} = {value}\n'
                    for key, value in QUIET_GIT.items())
    path.write_text(text + quiet, encoding='utf-8')
    return path


# A test that writes no gitconfig of its own uses this one, never the developer's.
_GIT = tempfile.TemporaryDirectory()
os.environ['GIT_CONFIG_GLOBAL'] = str(gitconfig(Path(_GIT.name) / 'gitconfig'))

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / 'skills' / 'presentation-studio'
SCRIPTS = SKILL / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO))
