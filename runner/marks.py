"""What a person marks at a stop reviewed item by item, checked, and the note it becomes.

What a caller needs to know
---------------------------
    marked = marks.check(gate, decision, extra, ids)   # the marks, cleaned, or a refusal
    marks.asks(marked)                                 # whether any mark needs a worker
    marks.note(gate, marked, free)                     # the note a worker reads, or None
    marks.title('licensing-cost')                      # 'Licensing cost'
    marks.new_id('What does it cost?', taken)          # 'what-does-it-cost'
    marks.first_sentence(text)

- REVIEWED are the stops reviewed this way. `ids` are what the stop has: its questions, or
  its slides as the person's edit has them. A mark naming anything else is refused.
- gate:research-plan takes {"dropped": [id], "reword": {id: text}, "add": [text]}.
  gate:research takes {"left_out": [id], "again": {id: line}, "add": [text]}; a line to
  research again with may be empty, and `left_out` is the whole set, so an empty one brings
  every finding back. gate:outline takes {"slides": {id: line}}, each line said.
- Approve takes only what needs no worker: drops at the plan and leave-outs at the
  research. Anything else is refused with AS_CHANGES.
- `check` returns only the marks that say something, and `left_out` whenever it was sent.
"""
from __future__ import annotations

import re

import runner  # noqa: F401  puts the core on the import path
from workspace import WorkspaceError

REVIEWED = ('gate:research-plan', 'gate:research', 'gate:outline')
ASKING = ('dropped', 'reword', 'add', 'again', 'slides')   # marks a worker acts on
LINE = 1000             # characters in one line a person writes against an item
ADDED = 10              # questions added at once
WORDS = 5               # words of a question a new ID is made from
ALL_DROPPED = 'Keep at least one question: research needs something to look up.'
ALL_LEFT_OUT = 'Keep at least one finding: the outline is drafted from them.'
AS_CHANGES = ('Rewording, adding, researching again and changing a slide go back to a '
              'worker: send them as changes.')


def _ids(value, ids: list[str], what: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(one, str) for one in value):
        raise WorkspaceError(f'Name each {what} by its ID.')
    unknown = [one for one in value if one not in ids]
    if unknown:
        raise WorkspaceError(f'There is no {what} {unknown[0]} here.')
    return list(dict.fromkeys(value))


def _lines(value, ids: list[str], what: str, needed: bool) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WorkspaceError(f'Give each {what} its line, by its ID.')
    lines = {}
    for ident, line in value.items():
        if ident not in ids:
            raise WorkspaceError(f'There is no {what} {ident} here.')
        if line is not None and not isinstance(line, str):
            raise WorkspaceError(f'What you wrote for {ident} is not text.')
        line = ' '.join((line or '').split())
        if needed and not line:
            raise WorkspaceError(f'Say what should change for {ident}.')
        if len(line) > LINE:
            raise WorkspaceError(f'Say it for {ident} in at most {LINE:,} characters.')
        lines[ident] = line
    return lines


def _texts(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(one, str) for one in value):
        raise WorkspaceError('Send each question to add as text.')
    texts = [' '.join(one.split()) for one in value]
    if any(not one for one in texts):
        raise WorkspaceError('A question to add is empty.')
    if any(len(one) > LINE for one in texts):
        raise WorkspaceError(f'Ask a question to add in at most {LINE:,} characters.')
    if len(texts) > ADDED:
        raise WorkspaceError(f'Add at most {ADDED} questions at once.')
    return texts


def check(gate: str, decision: str, extra: dict | None, ids) -> dict:
    """The marks sent with a decision at `gate`, cleaned. Refuses, in a sentence, one that
    names what the stop does not have, says nothing where it must, or goes with Approve
    when it needs a worker."""
    if gate not in REVIEWED:
        return {}
    ids = list(ids)
    if extra is not None and not isinstance(extra, dict):
        raise WorkspaceError('What comes with a decision was not understood.')
    extra = extra or {}
    if gate == 'gate:research-plan':
        marked = {'dropped': _ids(extra.get('dropped'), ids, 'question'),
                  'reword': _lines(extra.get('reword'), ids, 'question', True),
                  'add': _texts(extra.get('add'))}
        if ids and set(marked['dropped']) >= set(ids):
            raise WorkspaceError(ALL_DROPPED)
        both = [one for one in marked['reword'] if one in marked['dropped']]
        if both:
            raise WorkspaceError(f'{both[0]} is both dropped and reworded: choose one.')
        working = marked['reword'] or marked['add']
    elif gate == 'gate:research':
        marked = {'again': _lines(extra.get('again'), ids, 'question', False),
                  'add': _texts(extra.get('add'))}
        if extra.get('left_out') is not None:
            marked['left_out'] = _ids(extra.get('left_out'), ids, 'question')
            if ids and set(marked['left_out']) >= set(ids):
                raise WorkspaceError(ALL_LEFT_OUT)
            both = [one for one in marked['again'] if one in marked['left_out']]
            if both:
                raise WorkspaceError(f'{both[0]} is both left out and researched again: '
                                     'choose one.')
        working = marked['again'] or marked['add']
    else:
        marked = {'slides': _lines(extra.get('slides'), ids, 'slide', True)}
        working = marked['slides']
    if decision == 'approve' and working:
        raise WorkspaceError(AS_CHANGES)
    return {key: value for key, value in marked.items() if value or key == 'left_out'}


def asks(marked: dict) -> bool:
    """Whether the marks ask a worker for anything."""
    return any((marked or {}).get(key) for key in ASKING)


def note(gate: str, marked: dict, free: str | None) -> str | None:
    """The note a worker reads: one line for each mark, then the person's own words."""
    lines = []
    if gate == 'gate:research-plan':
        lines += [f'Reword `{ident}` as: {text}'
                  for ident, text in (marked.get('reword') or {}).items()]
        lines += [f'Add a question: {text}' for text in marked.get('add') or ()]
        lines += [f'`{ident}` is dropped: leave it out.' for ident in marked.get('dropped') or ()]
    elif gate == 'gate:research':
        lines += [f'Research `{ident}` again' + (f': {line}' if line else '.')
                  for ident, line in (marked.get('again') or {}).items()]
        lines += [f'Add a question: {text}' for text in marked.get('add') or ()]
        lines += [f'Leave out `{ident}`.' for ident in marked.get('left_out') or ()]
    elif gate == 'gate:outline':
        lines += [f'Slide `{ident}`: {line}'
                  for ident, line in (marked.get('slides') or {}).items()]
    said = '\n'.join(f'- {line}' for line in lines)
    if free:
        said = f'{said}\n\n{free}' if said else free
    return said or None


def title(ident: str) -> str:
    """A question's ID as a person reads it: 'licensing-cost' is 'Licensing cost'."""
    words = str(ident).replace('-', ' ').strip()
    return words[:1].upper() + words[1:]


def new_id(question: str, taken) -> str:
    """An ID for a question the person added, from its first words, that no other has."""
    words = re.findall(r'[a-z0-9]+', str(question).lower())[:WORDS]
    base = '-'.join(words)[:40].strip('-') or 'question'
    taken = set(taken)
    ident, number = base, 2
    while ident in taken:
        ident, number = f'{base}-{number}', number + 1
    return ident


def first_sentence(text) -> str:
    """The first sentence of a text, with its spaces made single."""
    said = ' '.join(str(text or '').split())
    return re.split(r'(?<=[.!?])\s', said, maxsplit=1)[0] if said else ''
