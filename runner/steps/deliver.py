"""Delivering a finished deck, and asking for changes to it once it is delivered.

What a caller needs to know
---------------------------
    record = deliver.deliver(root, run, slides, space=None)   # deliver.json, README, index
    made = deliver.upload(root, run, slides)                   # the same in two: the upload,
    record = deliver.record(root, run, made, space)            #   then what is written
    run = deliver.again(root, run, slides, note)               # reopen gate:build with a note

- Output 'google' puts the rendered deck into Google Drive as Google Slides, always as a
  new file: an earlier revision's file is never written over, so one that is gone is no
  matter. When Google cannot be reached the deck is delivered as a PowerPoint file
  instead, and deliver.json says so in `notice` (NOT_CONNECTED). Output 'pptx' keeps the
  deck under work/, which is never shared, for the page to offer as a download.
- deliver.json (decks.DELIVER) is {'output', 'url', 'fileId', 'pptx', 'revision', 'at'},
  with 'notice' when the deck was not delivered as asked. `revision` counts deliveries:
  each is added to run['revisions'] as {'revision', 'at', 'url' or 'pptx'}. The deck's
  README.md and the workspace's index are written again from it.
- `space` is the workspace, for its index. Without it, the deck's folder is taken to be
  in the workspace's own folder, as it always is.
- `again` reopens gate:build with the person's note, as `stages.reopen` does, and has
  every section drawn again with it. deliver.json is set aside, so the deck is no longer
  finished; the earlier link stays in run['revisions']. Returns the run as it now is.
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import home
from workspace import WorkspaceError, write_atomic

from runner import decks, stages
from runner.steps import build

GATE = 'gate:build'
NOT_CONNECTED = "Google isn't connected, so this deck was made as a PowerPoint file."
NOTE = 4000


def _title(run: dict, revision: int) -> str:
    title = run.get('title') or (run.get('form') or {}).get('title') or 'Deck'
    return title if revision == 1 else f'{title} (revision {revision})'


def _rewrite(root: Path, run: dict, record: dict | None, space) -> None:
    write_atomic(root / 'README.md', decks.readme(run, record))
    decks.write_index(space or types.SimpleNamespace(root=root.parent))


def deliver(root, run: dict, slides, space=None) -> dict:
    """Deliver the rendered deck as the form asked: to Google Slides, or as a PowerPoint
    file. Returns what deliver.json records. A caller that must not hold its lock through
    the upload calls `upload`, then `record` under its lock."""
    return record(root, run, upload(root, run, slides), space)


def upload(root, run: dict, slides) -> dict:
    """Put the rendered deck where the form asked, and say what deliver.json will record.
    Nothing in the deck's folder is written."""
    root = Path(root)
    deck = build.delivered_deck(root, run)
    revision, at = len(run.get('revisions') or []) + 1, home.now()
    output = (run.get('form') or {}).get('output') or 'google'
    record = {'output': output, 'url': None, 'fileId': None, 'pptx': None,
              'revision': revision, 'at': at}
    if output == 'google':
        if slides.drive_check():
            made = slides.drive_import(deck, _title(run, revision))
            record.update(url=made.get('url'), fileId=made.get('id'))
        else:
            record.update(output='pptx', notice=NOT_CONNECTED)
    if record['output'] == 'pptx':
        record['pptx'] = deck.relative_to(root).as_posix()
    return record


def record(root, run: dict, made: dict, space=None) -> dict:
    """Write deliver.json from what `upload` made, add the revision to the run, and write
    the deck's README and the workspace's index again. Returns what deliver.json holds."""
    root = Path(root)
    revisions = run.setdefault('revisions', [])
    revision, at = len(revisions) + 1, made['at']
    record = {**made, 'revision': revision}
    write_atomic(root / decks.DELIVER, json.dumps(record, indent=2, ensure_ascii=False)
                 + '\n')
    where = {'url': record['url']} if record['url'] else {'pptx': record['pptx']}
    revisions.append({'revision': revision, 'at': at, **where})
    decks.write_run(root, run)
    _rewrite(root, run, record, space)
    return record


def again(root, run: dict, slides, note: str, space=None) -> dict:
    """"Ask for changes" on a delivered deck: gate:build is reopened with the person's note,
    and the deck is built again from there. Returns the run as it now is."""
    root = Path(root)
    note = note.strip() if isinstance(note, str) else ''
    if not note:
        raise WorkspaceError('Say what should change.')
    if len(note) > NOTE:
        raise WorkspaceError(f'Say it in at most {NOTE} characters.')
    if decks.delivered(root) is None:
        raise WorkspaceError('This deck has not been delivered yet, so there is nothing '
                             'to change after delivery.')
    run.setdefault('gates', {})[GATE] = {**run['gates'].get(GATE, {}), 'state': 'changes',
                                         'note': note, 'at': home.now(), 'by': 'page'}
    run = stages.reopen(run, GATE)
    state = build.read_state(root)
    if state.get('start'):
        state.update(asked={'note': note, 'sections': [
            entry['id'] for entry in state['start']['sections']], 'at': home.now()},
            repaired=0)
        build.write_state(root, state)
    (root / decks.DELIVER).unlink(missing_ok=True)
    decks.write_run(root, run)
    _rewrite(root, run, None, space)
    return run
