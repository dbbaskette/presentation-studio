"""The deck folder and its run record.

What a caller needs to know
---------------------------
    checked = decks.check_form(sent, brands)   # the form, checked; WorkspaceError says what is wrong
    root = decks.create(workspace, checked)    # makes <root>/<id>/ and commits it
    run = decks.read_run(root)                 # the run record: run.json in the deck's folder
    decks.write_run(root, run)                 # atomic; a reader never sees half a record
    decks.deck_id(workspace, 'My talk')        # 'my-talk', or 'my-talk-2' when that is taken,
                                               # here or on the remote branch as last fetched
    decks.write_index(workspace)               # <root>/README.md: one row per deck

A deck is a folder holding `run.json` (decks.RUN, what marks it), `intake.md` (the form, in
words), and `README.md`. The form keeps only a short reference to the source (its kind and
a name or link); uploaded bytes and pasted text belong to documents.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import home
from workspace import WorkspaceError, write_atomic

from runner import gitstate

ROUTES = ('scratch', 'document', 'existing')
LEVELS = ('brand-only', 'polish', 'redesign', 'rework', 'selected')
OUTPUTS = ('google', 'pptx')
LIMITS = {'title': 120, 'audience': 2000, 'goal': 2000, 'notes': 4000, 'minutes': 240,
          'selected': 4000}
RUN = 'run.json'            # what marks a deck's folder
DELIVER = 'deliver.json'    # written when the deck is delivered
SCHEMA = 1
SOURCES = {'document': ('upload', 'paste', 'google'), 'existing': ('upload', 'google')}


# --- the form ------------------------------------------------------------------------------

def _text(sent: dict, key: str, label: str, required: bool = False) -> str:
    value = sent.get(key)
    if value is None or value == '':
        if required:
            raise WorkspaceError(f'Give the deck a {label}.')
        return ''
    if not isinstance(value, str):
        raise WorkspaceError(f'The {label} must be text.')
    value = value.strip()
    if required and not value:
        raise WorkspaceError(f'Give the deck a {label}.')
    if len(value) > LIMITS[key]:
        raise WorkspaceError(f'The {label} can be at most {LIMITS[key]} characters.')
    return value


def _source(sent: dict, route: str) -> dict:
    source = sent.get('source')
    kinds = SOURCES[route]
    what = 'document to build from' if route == 'document' else 'deck to improve'
    if not isinstance(source, dict) or source.get('kind') not in kinds:
        raise WorkspaceError(f'Say where the {what} comes from: {", ".join(kinds)}.')
    kind = source['kind']
    if kind == 'upload':
        name = source.get('name')
        if not isinstance(name, str) or not name.strip():
            raise WorkspaceError(f'Name the file for the {what}.')
        return {'kind': 'upload', 'name': name.strip()[:200]}
    if kind == 'google':
        link = source.get('link')
        if not isinstance(link, str) or not link.strip():
            raise WorkspaceError(f'Give the Google link for the {what}.')
        return {'kind': 'google', 'link': link.strip()[:500]}
    text = source.get('text')
    if not isinstance(text, str) or not text.strip():
        raise WorkspaceError(f'Paste the text for the {what}.')
    return {'kind': 'paste'}


def check_form(sent: dict, brands: list) -> dict:
    """The form, checked and trimmed. Raises WorkspaceError with one sentence otherwise."""
    if not isinstance(sent, dict):
        raise WorkspaceError('The form was not understood.')
    route = sent.get('route')
    if route not in ROUTES:
        raise WorkspaceError(f'Choose how to start: {", ".join(ROUTES)}.')
    title = _text(sent, 'title', 'title', required=True)
    audience = _text(sent, 'audience', 'audience')
    goal = _text(sent, 'goal', 'goal')
    minutes = sent.get('minutes')
    if minutes in (None, ''):
        minutes = None
    else:
        if isinstance(minutes, bool):
            raise WorkspaceError('The length must be a whole number of minutes.')
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            raise WorkspaceError('The length must be a whole number of minutes.') from None
        if not 1 <= minutes <= LIMITS['minutes']:
            raise WorkspaceError(f'The length must be between 1 and {LIMITS["minutes"]} minutes.')
    brand, variant = sent.get('brand'), sent.get('variant')
    chosen = next((one for one in brands if one.get('brand') == brand), None)
    if chosen is None:
        raise WorkspaceError('That brand is not one this studio has.')
    if variant not in chosen.get('variants', []):
        raise WorkspaceError(f'The {brand} brand has no "{variant}" variant.')
    output = sent.get('output')
    if output not in OUTPUTS:
        raise WorkspaceError(f'Choose an output: {", ".join(OUTPUTS)}.')
    research = bool(sent.get('research'))
    checked = {'route': route, 'title': title, 'audience': audience, 'goal': goal,
               'minutes': minutes, 'brand': brand, 'variant': variant, 'output': output,
               'research': research}
    if route == 'existing':
        if research:
            raise WorkspaceError('Research is not offered when improving an existing deck.')
        level = sent.get('level')
        if level not in LEVELS:
            raise WorkspaceError(f'Choose how much to change: {", ".join(LEVELS)}.')
        checked['level'] = level
        if level == 'selected':
            selected = _text(sent, 'selected', 'selected changes', required=True)
            checked['selected'] = selected
    if route in SOURCES:
        checked['source'] = _source(sent, route)
    return checked


# --- ids -----------------------------------------------------------------------------------

def deck_id(space, title: str) -> str:
    """A slug of the title, numbered when a folder of that name is already here or on the
    remote branch as last fetched."""
    base = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:48].strip('-') or 'deck'
    n, ident = 1, base
    while (space.deck(ident).exists() or gitstate.known(space, space.deck(ident))
           or gitstate.theirs(space, f'{ident}/{RUN}') is not None):
        n += 1
        suffix = f'-{n}'
        ident = base[:48 - len(suffix)].rstrip('-') + suffix
    return ident


# --- the run record ------------------------------------------------------------------------

def read_run(root: Path) -> dict:
    return json.loads((Path(root) / RUN).read_text(encoding='utf-8'))


def write_run(root: Path, run: dict) -> None:
    write_atomic(Path(root) / RUN, json.dumps(run, indent=2, ensure_ascii=False) + '\n')


def _new_run(ident: str, form: dict) -> dict:
    return {'schema': SCHEMA, 'id': ident, 'title': form['title'], 'route': form['route'],
            'form': form, 'created': home.now(), 'driver': None, 'gates': {}, 'steps': {},
            'classified': None, 'look': None, 'revisions': [], 'halted': None,
            'agent': None, 'model': None, 'level_of_effort': None, 'limits': {}}


# --- the files -----------------------------------------------------------------------------

def _source_words(source: dict) -> str:
    if source['kind'] == 'upload':
        return f"uploaded file {source['name']}"
    if source['kind'] == 'google':
        return f"Google link {source['link']}"
    return 'pasted text'


def intake(form: dict) -> str:
    parts = [f"# {form['title']}", '', '## Title', form['title'], '',
             '## Route', form['route']]
    if 'source' in form:
        parts += ['', f'Source: {_source_words(form["source"])}']
    if form['audience']:
        parts += ['', '## Audience', form['audience']]
    if form['goal']:
        parts += ['', '## Goal', form['goal']]
    if form['minutes']:
        parts += ['', '## Length', f"{form['minutes']} minutes"]
    parts += ['', '## Brand', f"{form['brand']} ({form['variant']})",
              '', '## Output', form['output']]
    if form['route'] != 'existing':
        parts += ['', '## Research', 'yes' if form['research'] else 'no']
    if 'level' in form:
        parts += ['', '## Change level', form['level']]
    if 'selected' in form:
        parts += ['', '## Selected changes', form['selected']]
    return '\n'.join(parts) + '\n'


def delivered(root: Path) -> dict | None:
    """What was delivered: deliver.json in the deck's folder, or None."""
    try:
        data = json.loads((Path(root) / DELIVER).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def state(run: dict, root: Path | None = None) -> str:
    """Where a deck stands, in a few words."""
    if root is not None and (Path(root) / DELIVER).is_file():
        return 'finished'
    if run.get('halted'):
        return 'stopped'
    gates = run.get('gates') or {}
    for name, gate in gates.items():
        if gate.get('state') == 'waiting':
            return f'waiting on {name}'
    for name, gate in gates.items():
        if gate.get('state') == 'changes':
            return f'changes asked at {name}'
    return 'in progress'


def _where(deliver: dict) -> str:
    """Where a delivered deck is: its Google Slides link, or the PowerPoint file's name."""
    if deliver.get('output') == 'pptx':
        return str(deliver.get('pptx') or 'PowerPoint file')
    return str(deliver.get('url') or '')


def readme(run: dict, deliver: dict | None) -> str:
    form = run['form']
    lines = [f"# {run['title']}", '', f"Route: {run['route']}",
             f"Brand: {form['brand']} ({form['variant']})", f"Output: {form['output']}",
             f"State: {'finished' if deliver else state(run)}"]
    if deliver:
        where = _where(deliver)
        if where:
            lines += ['', f'Delivered: {where}']
    return '\n'.join(lines) + '\n'


def create(space, form: dict) -> Path:
    """Make the deck's folder, with its intake, run record and README, and commit it."""
    ident = deck_id(space, form['title'])
    root = space.deck(ident)
    root.mkdir(parents=True)
    run = _new_run(ident, form)
    write_atomic(root / 'intake.md', intake(form))
    write_run(root, run)
    write_atomic(root / 'README.md', readme(run, None))
    gitstate.commit(space, f"{form['title']}: start the deck", [ident])
    return root


def index(space) -> str:
    rows = []
    for folder in sorted(space.root.iterdir()) if space.root.is_dir() else []:
        if not (folder / RUN).is_file():
            continue
        try:
            run = read_run(folder)
        except (OSError, ValueError):
            continue
        title = run.get('title', folder.name).replace('|', '\\|')
        link = f"[{folder.name}]({folder.name}/README.md)"
        done = delivered(folder)
        if done and done.get('output') == 'pptx':
            link += ' · PowerPoint file'
        elif done and done.get('url'):
            link += f" · [Google Slides]({done['url']})"
        rows.append(f"| {title} | {run.get('route', '')} | {state(run, folder)} | {link} |")
    return '\n'.join(['# Presentations', '', '| Deck | Route | State | Link |',
                      '| --- | --- | --- | --- |'] + rows) + '\n'


def write_index(space) -> None:
    write_atomic(space.root / 'README.md', index(space))
