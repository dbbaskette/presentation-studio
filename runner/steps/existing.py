"""Bringing in a deck that already exists: fetching it, taking its inventory and pictures,
and planning and making selected changes to it.

What a caller needs to know
---------------------------
    path = existing.fetch(root, source, slides, google_ready)   # sources/original.pptx
    run  = existing.inventory(root, run, slides, renderer)      # classify.json, .md, pictures
    work = existing.patch_work(root, run, request, error)       # the 'selected' level's job
    existing.keep_patch(root, handed)                           # keep the plan: work/patch.json
    out  = existing.apply_patch(root, run, slides)              # work/patched.pptx, compared
    rows = existing.pairs(root, run)                            # before and after, by number

- `source` is the form's: {'kind': 'upload', 'name', 'data': bytes} or {'kind': 'google',
  'link'} (a Slides URL or a bare ID). The deck is kept as sources/original.pptx, which is
  never shared. A file without the PowerPoint signature, or over 100 MB, is refused, and so
  is a Google deck when Google is not ready; in each case nothing is written.
- classify.json is the inventory the outline step reads: the deck's sha256 and source name,
  and for each slide its number, id, title, hidden flag and objects (id, type, text, runs,
  alt, title, contentHash). Boxes and structure hashes are left out. classify.md is the same
  as a table. Pictures of the original go to work/original/, with a shots.json, taken as
  the build's previews are: one at a time on this computer, and through the deck's one
  preview file in Drive.
- The patch is handed back as `patch`, a kind checked by `check_patch` and registered
  here: {"sourceSha256", "operations": [{"slide": number, "object", "expectedHash", and one
  of "text", "runs", "alt", "title"}]}. A slide the person did not name, an unknown object,
  a wrong hash or a wrong deck hash is refused. The slides tool names a slide by its stable
  ID, so `apply_patch` turns each number into its ID, and a change that touches more than
  the plan allows is removed and refused with the tool's own lines.
- `pairs` reads before pictures from work/original/shots.json and after pictures from
  work/build/preview/shots.json: {"slides": [{"number", "image"}]}; an image path may be
  relative to the file that names it.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import gdrive
from workspace import WorkspaceError, write_atomic

from runner import briefs, decks, worker_tools
from runner.steps import Work

SOURCE = 'sources/original.pptx'
SOURCE_NOTE = 'sources/original.json'
INVENTORY = 'classify.json'
INVENTORY_MD = 'classify.md'
ORIGINAL_SHOTS = 'work/original'
AFTER_SHOTS = 'work/build/preview'
SHOTS = 'shots.json'
PATCH = 'work/patch.json'
PLAN = 'work/patch-plan.json'
ALLOW = 'work/patch-allow.json'
PATCHED = 'work/patched.pptx'
NAME = 'patch'
GATE = 'gate:classify'
SIGNATURE = b'PK\x03\x04'
LIMIT = 100 * 1024 * 1024
NOT_READY = ('Sign in to Google on the Check this computer screen, or download the deck as '
             '.pptx and upload it.')
FIELDS = ('text', 'runs', 'alt', 'title')
PAIRED = ('brand-only', 'polish', 'redesign', 'selected')
OBJECT_KEYS = ('id', 'type', 'text', 'runs', 'alt', 'title', 'contentHash')


# --- fetching the deck ----------------------------------------------------------------------

def _keep_source(root: Path, data: bytes) -> Path:
    target = root / SOURCE
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(f'.incoming-{secrets.token_hex(4)}')
    try:
        part.write_bytes(data)
        os.replace(part, target)
    finally:
        part.unlink(missing_ok=True)
    return target


def _note(root: Path, name: str) -> None:
    write_atomic(root / SOURCE_NOTE, json.dumps({'name': name}) + '\n')


def fetch(root, source: dict, slides, google_ready: bool) -> Path:
    """Bring the person's deck into sources/original.pptx and return its path. Nothing is
    written unless the deck is good."""
    root = Path(root)
    kind = source.get('kind') if isinstance(source, dict) else None
    if kind == 'upload':
        data, name = source.get('data'), source.get('name')
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise WorkspaceError('The upload has no file in it. Choose the .pptx again.')
        if len(data) > LIMIT:
            raise WorkspaceError('That deck is over 100 MB, which is more than can be taken '
                                 'in. Save a smaller copy and upload that.')
        if bytes(data[:4]) != SIGNATURE:
            raise WorkspaceError(f'"{name or "That file"}" is not a PowerPoint (.pptx) file. '
                                 'Save the deck as .pptx and upload it again.')
        path = _keep_source(root, bytes(data))
        _note(root, str(name or 'original.pptx'))
        return path
    if kind == 'google':
        if not google_ready:
            raise WorkspaceError(NOT_READY)
        ident = gdrive.file_id(source.get('link'))
        target = root / SOURCE
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(f'.incoming-{secrets.token_hex(4)}.pptx')
        try:
            slides.drive_export(ident, part)
            if part.read_bytes()[:4] != SIGNATURE:
                raise WorkspaceError('Google did not give back a PowerPoint file. Try again, '
                                     'or download the deck as .pptx and upload it.')
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)
        _note(root, f'Google Slides {ident}')
        return target
    raise WorkspaceError('Say where the deck comes from: upload or google.')


# --- the inventory --------------------------------------------------------------------------

def _source_name(root: Path) -> str:
    try:
        return str(json.loads((root / SOURCE_NOTE).read_text(encoding='utf-8'))['name'])
    except (OSError, ValueError, KeyError, TypeError):
        return 'original.pptx'


def _shared(found: dict, name: str) -> dict:
    return {'sha256': found.get('sha256'), 'source': name, 'slides': [
        {'number': slide.get('number'), 'id': slide.get('id'), 'title': slide.get('title'),
         'hidden': bool(slide.get('hidden')),
         'objects': [{key: item.get(key) for key in OBJECT_KEYS}
                     for item in slide.get('objects') or ()]}
        for slide in found.get('slides') or ()]}


def _words(slide: dict) -> int:
    return sum(len((item.get('text') or '').split()) for item in slide['objects'])


def _table(shared: dict) -> str:
    lines = [f"# {shared['source']}", '', '| Slide | Title | Words |', '| --- | --- | --- |']
    for slide in shared['slides']:
        title = (slide.get('title') or '(no title)').replace('|', '/')
        lines.append(f"| {slide['number']} | {title}{' (hidden)' if slide['hidden'] else ''}"
                     f' | {_words(slide)} |')
    return '\n'.join(lines) + '\n'


def _build():
    """The build step, which holds the computer's one way of picturing a deck."""
    from runner.steps import build
    return build


def inventory(root, run: dict, slides, renderer) -> dict:
    """Read the fetched deck: write classify.json and classify.md, draw its slides into
    work/original/, and put the inventory in front of the person. The slides are pictured
    as the build's are: under the computer's one turn at the renderer and through the
    deck's one preview file in Drive (`build.picture_deck`); `renderer` is what
    `build.how` takes."""
    root = Path(root)
    deck = root / SOURCE
    if not deck.is_file():
        raise WorkspaceError('The deck has not been brought in yet.')
    shared = _shared(slides.pptx_inspect(deck), _source_name(root))
    folder = root / ORIGINAL_SHOTS
    if folder.exists():
        shutil.rmtree(folder)
    drawn = _build().picture_deck(root, run, deck, folder, slides, renderer)
    shots = [{'number': one['number'],
              'image': os.path.relpath(one['image'], folder)} for one in drawn['slides']]
    write_atomic(folder / SHOTS, json.dumps({'slides': shots}, indent=2) + '\n')
    write_atomic(root / INVENTORY, json.dumps(shared, indent=2, ensure_ascii=False) + '\n')
    write_atomic(root / INVENTORY_MD, _table(shared))
    gate = (run.setdefault('gates', {})).get(GATE) or {}
    run['gates'][GATE] = {'state': 'waiting', 'round': int(gate.get('round') or 0) + 1}
    decks.write_run(root, run)
    return run


def _inventory(root: Path) -> dict:
    try:
        found = json.loads((root / INVENTORY).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        found = None
    if not isinstance(found, dict):
        raise WorkspaceError('The deck has not been looked through yet.')
    return found


# --- which slides the person named ----------------------------------------------------------

_NUMBER = r'\d+(?:\s*(?:-|–|—|to)\s*\d+)?'
_LIST = rf'{_NUMBER}(?:\s*(?:,|&|and)\s*{_NUMBER})*'
_NAMED = re.compile(rf'\bslides?\s*(?:#|no\.?|numbers?)?\s*({_LIST})', re.IGNORECASE)
_BARE = re.compile(rf'^\W*({_LIST})\W*$', re.IGNORECASE)


def named_slides(selected) -> list[int]:
    """The slide numbers a person's words name, in order: "slide 3", "slides 4 and 7",
    "3, 5-6". Empty when there are none."""
    text = selected if isinstance(selected, str) else ''
    lists = _NAMED.findall(text) or _BARE.findall(text.strip())
    found = []
    for chunk in lists:
        for part in re.split(r'\s*(?:,|&|\band\b)\s*', chunk):
            span = re.split(r'\s*(?:-|–|—|\bto\b)\s*', part.strip())
            low, high = int(span[0]), int(span[-1])
            for number in range(low, min(max(high, low), low + 500) + 1):
                if number not in found:
                    found.append(number)
    return found


def _named_for(run: dict, inventory: dict) -> list[int]:
    wanted = named_slides((run.get('form') or {}).get('selected'))
    if not wanted:
        raise WorkspaceError('Say which slides to change by their numbers, for example '
                             '"slide 3" or "slides 4 and 7", and what to change on them.')
    have = {slide['number'] for slide in inventory.get('slides') or ()}
    missing = [number for number in wanted if number not in have]
    if missing:
        raise WorkspaceError(f"The deck has {len(have)} slides, and no slide "
                             f"{', '.join(map(str, missing))}. Name slides that exist.")
    return wanted


# --- the patch ------------------------------------------------------------------------------

def _shown(inventory: dict, named: list[int]) -> str:
    lines = [f"Deck hash (sourceSha256): {inventory.get('sha256')}"]
    for slide in inventory['slides']:
        if slide['number'] not in named:
            continue
        lines.append(f"\n## Slide {slide['number']}: {slide.get('title') or '(no title)'}")
        for item in slide['objects']:
            lines.append(f"- object {item['id']} ({item.get('type')}), hash "
                         f"{item.get('contentHash')}")
            lines.append(f"  text: {json.dumps(item.get('text'), ensure_ascii=False)}")
            lines.append(f"  runs: {json.dumps(item.get('runs'), ensure_ascii=False)}")
            lines.append(f"  alt: {json.dumps(item.get('alt'), ensure_ascii=False)}, "
                         f"title: {json.dumps(item.get('title'), ensure_ascii=False)}")
    return '\n'.join(lines)


def _spec(inventory: dict, named: list[int]) -> dict:
    return {'sha256': inventory.get('sha256'), 'named': named, 'objects': {
        f"{slide['number']}:{item['id']}": item.get('contentHash')
        for slide in inventory['slides'] if slide['number'] in named
        for item in slide['objects']}}


def patch_work(root, run: dict, request: dict | None, error: str | None) -> Work:
    """The job of planning the changes the person named, on the slides they named."""
    root = Path(root)
    found = _inventory(root)
    selected = (run.get('form') or {}).get('selected')
    named = _named_for(run, found)
    lines = [f"Deck title: {run.get('title') or (run.get('form') or {}).get('title') or 'not given'}",
             f"The slides the person named: {', '.join(map(str, named))}.",
             f'Hand your plan back under the name "{NAME}".',
             'Your inputs: Inventory, Selected changes.']
    if request and request.get('note'):
        lines.append(f"The person added:\n\n{request['note']}")
    if error:
        lines.append(f'An earlier try at this job did not work: {error}\n'
                     'Take care not to end the same way.')
    return Work(guidance=briefs.guidance('patch'), task='\n\n'.join(lines), profile='write',
                name=NAME,
                prepared={'inputs': {'Inventory': _shown(found, named),
                                     'Selected changes': selected},
                          'artifacts': {NAME: {'kind': 'patch', **_spec(found, named)}},
                          'ask': False})


def check_patch(text: str, spec: dict):
    """A patch plan. Returns problems, the checks that ran, warnings and the text to keep."""
    try:
        given = json.loads(text)
    except ValueError as failure:
        return [f'The patch is not valid JSON ({failure}).'], [], [], text
    problems = []
    if not isinstance(given, dict):
        return ['The patch is one JSON object with "sourceSha256" and "operations".'], \
            [], [], text
    if given.get('sourceSha256') != spec.get('sha256'):
        problems.append('"sourceSha256" is not the deck\'s hash. Copy it from the inventory.')
    operations = given.get('operations')
    if not isinstance(operations, list) or not operations:
        problems.append('"operations" is a list with at least one operation.')
        operations = []
    named, objects, seen = spec.get('named') or [], spec.get('objects') or {}, set()
    for position, op in enumerate(operations, start=1):
        label = f'Operation {position}'
        if not isinstance(op, dict):
            problems.append(f'{label} is an object.')
            continue
        slide, ident = op.get('slide'), op.get('object')
        if isinstance(slide, bool) or slide not in named:
            problems.append(f'{label}: slide {slide!r} was not named by the person. Only '
                            f"slides {', '.join(map(str, named))} may change.")
            continue
        key = f'{slide}:{ident}'
        if key not in objects:
            problems.append(f'{label}: slide {slide} has no object {ident!r}.')
            continue
        if op.get('expectedHash') != objects[key]:
            problems.append(f'{label}: "expectedHash" for object {ident} on slide {slide} is '
                            'not its hash in the inventory. Copy it exactly.')
        if key in seen:
            problems.append(f'{label}: object {ident} on slide {slide} is changed twice. Use '
                            'one operation for it.')
        seen.add(key)
        given_fields = [field for field in FIELDS if field in op]
        if len(given_fields) != 1:
            problems.append(f'{label}: give exactly one of text, runs, alt or title.')
        elif given_fields[0] == 'runs':
            runs = op['runs']
            if not isinstance(runs, list) or not runs or not all(
                    isinstance(one, dict) and isinstance(one.get('index'), int)
                    and isinstance(one.get('text'), str) for one in runs):
                problems.append(f'{label}: "runs" is a list of {{"index", "text"}}.')
        elif not isinstance(op[given_fields[0]], str):
            problems.append(f'{label}: "{given_fields[0]}" is a string.')
    return problems, [worker_tools.result('patch.operations', problems)], [], text


worker_tools.register('patch', check_patch)


def keep_patch(root, handed) -> Path:
    """Keep the plan a worker handed back, as the worker wrote it."""
    text = handed if isinstance(handed, str) else json.dumps(handed)
    path = Path(root) / PATCH
    write_atomic(path, text if text.endswith('\n') else text + '\n')
    return path


def apply_patch(root, run: dict, slides) -> Path:
    """Make the planned changes to a copy of the deck, at work/patched.pptx, and check that
    nothing else changed. A copy that changed more than it should is removed and refused."""
    root = Path(root)
    found = _inventory(root)
    try:
        plan = json.loads((root / PATCH).read_text(encoding='utf-8'))
        operations = list(plan['operations'])
    except (OSError, ValueError, KeyError, TypeError):
        raise WorkspaceError('There is no plan for the changes yet.') from None
    ids = {slide['number']: str(slide['id']) for slide in found['slides']}
    numbers = {value: key for key, value in ids.items()}
    tool_ops, allow = [], []
    for op in operations:
        if op.get('slide') not in ids:
            raise WorkspaceError(f"The plan names slide {op.get('slide')}, which the deck "
                                 'does not have.')
        slide = ids[op['slide']]
        tool_ops.append({**op, 'slide': slide})
        allow.append({'slide': slide, 'object': str(op['object']), 'fields': [
            'text' if field == 'runs' else field for field in FIELDS if field in op]})
    work = root / 'work'
    work.mkdir(parents=True, exist_ok=True)
    patched = root / PATCHED
    patched.unlink(missing_ok=True)
    write_atomic(root / PLAN, json.dumps({'sourceSha256': plan.get('sourceSha256'),
                                          'operations': tool_ops}, indent=2) + '\n')
    write_atomic(root / ALLOW, json.dumps(allow, indent=2) + '\n')
    slides.pptx_patch(root / SOURCE, root / PLAN, patched)
    report = slides.pptx_compare(root / SOURCE, patched, root / ALLOW)
    if not report.get('preserved'):
        patched.unlink(missing_ok=True)
        lines = []
        for failure in report.get('failures') or ():
            where = f"slide {numbers.get(str(failure.get('slide')), failure.get('slide'))}" \
                if failure.get('slide') is not None else 'the deck'
            what = f", object {failure['object']}" if failure.get('object') else ''
            lines.append(f"{where}{what}: {failure.get('code') or failure.get('detail')}.")
        raise WorkspaceError('The changed deck is not delivered, because more than the plan '
                             'allows changed. ' + ' '.join(lines))
    return patched


# --- before and after -----------------------------------------------------------------------

def _shots(folder: Path) -> dict:
    try:
        record = json.loads((folder / SHOTS).read_text(encoding='utf-8'))
        found = {}
        for one in record['slides']:
            image = Path(one['image'])
            found[one['number']] = str(image if image.is_absolute() else folder / image)
        return found
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def pairs(root, run: dict) -> list[dict]:
    """The before and after picture of each slide, by number. `after` is None where there is
    no picture of it yet. A rework has no pairs: its slides are not the slides it began
    with."""
    level = (run.get('form') or {}).get('level')
    if level not in PAIRED:
        return []
    root = Path(root)
    before, after = _shots(root / ORIGINAL_SHOTS), _shots(root / AFTER_SHOTS)
    return [{'number': number, 'before': before[number], 'after': after.get(number)}
            for number in sorted(before)]
