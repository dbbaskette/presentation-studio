"""Writing, extracting and restructuring a deck's outline.

What a caller needs to know
---------------------------
    work = outline.outline_work(root, run, request, error, brand, slides=None)
    work = outline.extract_work(root, run, request, error, brand, slides=None)
    outline.keep_outline(root, run, handed, extracted=False)   # keep a draft, open the gate
    outline.apply_edits(root, run, edited, slides, brand)       # the page's edits, re-checked
    outline.inventory_of(root)                                  # classify.json, or None

- The outline is kept as outline.json (harness-slides outline v1) and outline.md, which is
  the same read as prose: one `## n. Title` a slide.
- `outline_work` picks the brief by route: scratch, a document (a spec or material), or an
  existing deck being reworked. `extract_work` reads an existing deck into an outline and
  holds it to the rules its level has. Both hand back under the name "outline".
- A rule crosses into the worker-tools process, so a rule is a top-level function or a
  functools.partial of one with JSON arguments: `verbatim` and `same_slides`.
- Verbatim covers the words a slide shows (title, subtitle, detail, points' label and text,
  caveat, source line), held to the slide each was read from: the slides its `sources`
  name, or for a slide without sources the one at its place (brand only, polish) or any
  (redesign, rework). Brand only and polish keep each text as a whole text object or a
  whole run of that slide; redesign and rework may take part of one, cut on word
  boundaries. A slide read from slides that show no words at all, a picture alone, needs
  a title all the same, and its title is not compared. `understand` is the worker's own. `notes` are exempt too: the inventory holds
  no speaker notes. The deck's title and each `focal` are not compared.
- `same_slides` holds a slide for each original, in order. A content slide names its
  original as sources ['slide-<n>']; a cover, section or closing slide takes no `sources`
  in the outline format, so it is held to the count and the order only.
"""
from __future__ import annotations

import functools
import json
import re
import secrets
import tempfile
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
from workspace import WorkspaceError, write_atomic

from runner import briefs, decks, documents, slides as slides_tool, stages, worker_tools
from runner.steps import Work

OUTLINE = 'outline.json'
OUTLINE_MD = 'outline.md'
INVENTORY = 'classify.json'
REPORT = Path('research') / 'report.md'
NAME = 'outline'
GATE = 'gate:outline'
LEVELS_COUNTED = ('brand-only', 'polish')


# --- the inventory --------------------------------------------------------------------------

def inventory_of(root) -> dict | None:
    """The inventory of the deck that was given, or None when there is none."""
    try:
        found = json.loads((Path(root) / INVENTORY).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def _norm(text) -> str:
    return ' '.join(text.split()) if isinstance(text, str) else ''


def _runs(item: dict) -> list[str]:
    return [_norm(run) for run in item.get('runs') or () if _norm(run)]


def _whole(slide: dict) -> list[str]:
    """Every whole text a slide shows: its title, and each text object, as it is and with
    its runs joined. A run is a whole text only of an object that has no other."""
    found = []
    for item in slide.get('objects') or ():
        found += [item.get('text'), ' '.join(item.get('runs') or ())]
    return list(dict.fromkeys(_norm(text) for text in [slide.get('title'), *found]
                              if _norm(text)))


def pages_of(inventory: dict) -> dict:
    """Each slide's whole texts, whitespace-normalised, by its number as a string."""
    return {str(slide.get('number')): _whole(slide) for slide in inventory.get('slides') or ()
            if isinstance(slide, dict)}


def parts_of(inventory: dict) -> dict:
    """Each slide's text objects of more than one run, as their runs, by its number."""
    return {str(slide.get('number')): [_runs(item) for item in slide.get('objects') or ()
                                       if len(_runs(item)) > 1]
            for slide in inventory.get('slides') or () if isinstance(slide, dict)}


def _shown(inventory: dict) -> str:
    parts = []
    for slide in inventory.get('slides') or ():
        parts.append(f"## Slide {slide.get('number')}: {slide.get('title') or '(no title)'}")
        for item in slide.get('objects') or ():
            runs = [_norm(run) for run in item.get('runs') or () if _norm(run)]
            if _norm(item.get('text')) or runs:
                parts.append(f"- {_norm(' '.join(item.get('runs') or ())) or _norm(item.get('text'))}")
            if len(runs) > 1:
                parts.extend(f'  - run: {run}' for run in runs)
    return '\n'.join(parts)


# --- the rules ------------------------------------------------------------------------------

def _slides(outline: dict) -> list:
    found = outline.get('slides') if isinstance(outline, dict) else None
    return [slide for slide in found or () if isinstance(slide, dict)]


def _words(slide: dict):
    """(field, text) for every text of a slide the deck must have said as it stands."""
    for key in ('title', 'subtitle', 'detail', 'caveat', 'source'):
        if slide.get(key):
            yield key, slide[key]
    for number, point in enumerate(slide.get('points') or (), start=1):
        if isinstance(point, dict):
            for key in ('label', 'text'):
                if point.get(key):
                    yield f'point {number} {key}', point[key]


def _within(plain: str, kept: str) -> bool:
    """`plain` is in `kept` with nothing of a word cut off at either end."""
    return re.search(r'(?<!\w)' + re.escape(plain) + r'(?!\w)', kept) is not None


def _read_from(slide: dict, number: int, pages: dict, counted: bool) -> list[str]:
    """The numbers of the slides a slide's words come from: those its sources name, else
    the one at its place when the level keeps every slide in order, else any slide."""
    sources = slide.get('sources')
    if isinstance(sources, list) and sources:
        return [str(source)[len('slide-'):] for source in sources]
    return [str(number)] if counted else list(pages)


def _where(numbers: list[str], pages: dict) -> str:
    if set(numbers) == set(pages) and len(numbers) > 1:
        return 'your deck'
    if len(numbers) == 1:
        return f'slide {numbers[0]} of your deck'
    return 'slides ' + ', '.join(numbers[:-1]) + f' and {numbers[-1]} of your deck'


def _in_order(runs: list[str], fields: list[str]) -> bool:
    """Every run, one field each, in their order among the fields."""
    at = 0
    for field in fields:
        if at < len(runs) and field == runs[at]:
            at += 1
    return at == len(runs)


def verbatim(outline: dict, pages: dict, whole: bool = False, counted: bool = False,
             parts: dict | None = None) -> list[str]:
    """A sentence for each word of a slide that is not the deck's own, on the slide it was
    read from. With `whole` (brand only, polish) each text is a whole text of that slide, or
    a run of one when every run of that text is kept, each its own field, in order; without,
    it is a part of one, cut on word boundaries."""
    found = []
    for number, slide in enumerate(_slides(outline), start=1):
        numbers = _read_from(slide, number, pages, counted)
        texts = [text for one in numbers for text in pages.get(one) or ()]
        split = [runs for one in numbers for runs in (parts or {}).get(one) or ()]
        fields = [_norm(text) for _, text in _words(slide)]
        for field, text in _words(slide):
            plain = _norm(text)
            if not plain or (field == 'title' and not texts and all(one in pages
                                                                     for one in numbers)):
                # A slide that shows no words, a picture alone, still needs a title.
                continue
            if whole:
                held = plain in texts
                cut = [runs for runs in split if plain in runs]
                if not held and cut:
                    if not any(_in_order(runs, fields) for runs in cut):
                        found.append(
                            f"Slide {number} ({slide.get('id')}): the {field} \"{plain}\" is "
                            f"part of the text \"{' '.join(cut[0])}\" on "
                            f'{_where(numbers, pages)}. Copy that text whole, or every part '
                            'of it, in order, each part a text of its own.')
                    continue
            else:
                held = any(_within(plain, kept) for kept in texts)
            if not held:
                how = ('as one whole text of it' if whole else 'word for word')
                found.append(f"Slide {number} ({slide.get('id')}): the {field} \"{plain}\" is "
                             f'not on {_where(numbers, pages)} {how}. Copy it exactly from '
                             'there, whitespace aside.')
    return found


def same_slides(outline: dict, count: int) -> list[str]:
    """A slide for each original slide, in order, each content slide naming its original."""
    listed = _slides(outline)
    found = []
    if len(listed) != count:
        found.append(f'The deck has {count} slides and the outline has {len(listed)}. Keep '
                     'every slide, once, in its order.')
    for number, slide in enumerate(listed, start=1):
        sources = slide.get('sources')
        if (slide.get('kind') == 'content' or sources is not None) \
                and sources != [f'slide-{number}']:
            found.append(f"Slide {number} ({slide.get('id')}): its sources are "
                         f"[\"slide-{number}\"], the slide it was read from.")
    return found


def wordless(outline: dict, inventory: dict | None, level: str | None) -> list[str]:
    """The IDs of the slides that, at brand only and polish, stand for an original slide
    that shows no words at all: their title is a label of the worker's, so the build draws
    no words of theirs, and sets each on a template layout that shows no title
    (`build.start`). None at any other level."""
    if level not in LEVELS_COUNTED or not isinstance(inventory, dict):
        return []
    pages = pages_of(inventory)
    return [slide.get('id') for number, slide in enumerate(_slides(outline), start=1)
            if str(number) in pages and not pages[str(number)]]


def verbatim_rule(inventory: dict, level: str | None = None):
    """The rule that every word is the deck's own, from the slide it was read from. Brand
    only and polish keep whole texts, in the deck's order."""
    held = level in LEVELS_COUNTED
    return functools.partial(verbatim, pages=pages_of(inventory), whole=held, counted=held,
                             parts=parts_of(inventory) if held else None)


def count_rule(inventory: dict, level: str):
    """The rule that no slide is added, dropped or moved: brand only and polish. Others get
    None."""
    if level not in LEVELS_COUNTED:
        return None
    return functools.partial(same_slides, count=len(inventory.get('slides') or ()))


# --- the jobs -------------------------------------------------------------------------------

def _document_texts(root) -> dict:
    found = {}
    for entry in documents.listed(root):
        if entry['readable']:
            found[entry.get('title') or entry['name']] = documents.text_of(root, entry)
    return found


def _tail(run: dict, request, error) -> list[str]:
    lines = []
    note = (((run.get('gates') or {}).get(GATE) or {}).get('note')
            or (request or {}).get('note'))
    if note:
        lines.append(f'The person asked for this change to the outline:\n\n{note}')
    if error:
        lines.append(f'An earlier try at this job did not work: {error}\n'
                     'Take care not to end the same way.')
    return lines


def _job(root, run, request, error, brand, slides, brief_kind, level, inputs, rules, intro,
         ask):
    root = Path(root)
    form = run.get('form') or {}
    contract = (slides or slides_tool.Slides()).outline_contract(Path(brand))
    inputs = {'Outline contract': contract, **inputs}
    current = Path(root) / OUTLINE
    if current.exists():
        inputs['The current outline'] = current.read_text(encoding='utf-8')
    lines = [f"Deck title: {run.get('title') or form.get('title') or 'not given'}",
             f"Audience: {form.get('audience') or 'not given'}",
             f"Goal: {form.get('goal') or 'not given'}",
             intro, f'Hand your outline back under the name "{NAME}".',
             'Your inputs: ' + ', '.join(inputs) + '.', *_tail(run, request, error)]
    spec = {'kind': 'outline', 'brand': str(brand), 'rules': [r for r in rules if r]}
    return Work(guidance=briefs.guidance(brief_kind, level=level), task='\n\n'.join(lines),
                profile='write', name=NAME,
                prepared={'inputs': inputs, 'artifacts': {NAME: spec}, 'ask': ask})


def outline_work(root, run: dict, request: dict | None, error: str | None, brand: Path,
                 slides=None) -> Work:
    """The job of writing the outline of a deck from a brief, a document, or the deck there
    is."""
    root = Path(root)
    route = run.get('route') or (run.get('form') or {}).get('route')
    inputs = {}
    form = run.get('form') or {}
    if route == 'scratch':
        kind = 'outline-brief'
        intro = 'Write the outline from the brief above alone.'
    elif route == 'document':
        kind = 'outline-spec' if run.get('classified') == 'spec' else 'outline-material'
        intro = 'Write the outline from the person\'s document.'
        inputs.update(_document_texts(root))
    elif route == 'existing':
        kind = 'restructure'
        intro = 'Rework the story of the deck the person gave.'
        inventory = inventory_of(root)
        if inventory is None:
            raise WorkspaceError('The deck has not been looked through yet.')
        inputs['Inventory'] = _shown(inventory)
    else:
        raise WorkspaceError('This deck has no route to write an outline for.')
    inputs['The brief'] = '\n'.join(f'{label}: {form.get(key) or "not given"}' for label, key in (
        ('Title', 'title'), ('Audience', 'audience'), ('Goal', 'goal'),
        ('Minutes', 'minutes'), ('Notes', 'notes')))
    report = root / REPORT
    if report.exists():
        inputs['Research report'] = report.read_text(encoding='utf-8')
    return _job(root, run, request, error, brand, slides, kind, None, inputs, [], intro, True)


def extract_work(root, run: dict, request: dict | None, error: str | None, brand: Path,
                 slides=None) -> Work:
    """The job of reading the deck there is into an outline, at the level it was given."""
    root = Path(root)
    level = (run.get('form') or {}).get('level')
    if level not in briefs.LEVELS:
        raise WorkspaceError('Say how much of the deck may change first.')
    inventory = inventory_of(root)
    if inventory is None:
        raise WorkspaceError('The deck has not been looked through yet.')
    rules = [verbatim_rule(inventory, level), count_rule(inventory, level)]
    return _job(root, run, request, error, brand, slides, 'extract', level,
                {'Inventory': _shown(inventory)}, rules,
                f'Read the deck into an outline, at the level "{level}".', False)


# --- keeping an outline ---------------------------------------------------------------------

def _render(outline: dict) -> str:
    lines = [f"# {outline.get('title') or 'Outline'}", '']
    for number, slide in enumerate(_slides(outline), start=1):
        lines += [f"## {number}. {slide.get('title') or ''}", '']
        for key in ('subtitle', 'detail'):
            if slide.get(key):
                lines += [slide[key], '']
        if slide.get('understand'):
            lines += [f"Understand: {slide['understand']}", '']
        for point in slide.get('points') or ():
            if isinstance(point, dict):
                label, text = point.get('label'), point.get('text')
                lines.append(f'- **{label}**: {text}' if label and text
                             else f'- {label or text or ""}')
        if slide.get('points'):
            lines.append('')
        for key, name in (('caveat', 'Caveat'), ('source', 'Source'), ('notes', 'Notes')):
            if slide.get(key):
                lines += [f'{name}: {slide[key]}', '']
    return '\n'.join(lines).rstrip() + '\n'


def _write(root, outline: dict) -> None:
    root = Path(root)
    write_atomic(root / OUTLINE, json.dumps(outline, indent=2, ensure_ascii=False) + '\n')
    write_atomic(root / OUTLINE_MD, _render(outline))


def keep_outline(root, run: dict, handed, extracted: bool = False) -> dict:
    """Keep an outline a worker handed back, and put it in front of the person when the deck
    has the gate. `extracted` is a deck read in by `extract`: a later outline step, where the
    deck has one, still has to rework it, so the gate stays closed."""
    outline = json.loads(handed) if isinstance(handed, str) else handed
    _write(root, outline)
    names = [step.name for step in stages.steps(run)]
    if GATE in names and not (extracted and NAME in names):
        gate = (run.setdefault('gates', {})).get(GATE) or {}
        run['gates'][GATE] = {**gate, 'state': 'waiting',
                              'round': int(gate.get('round') or 0) + 1}
    decks.write_run(root, run)
    return run


def apply_edits(root, run: dict, edited: list, slides, brand: Path) -> None:
    """The page's edited outline (reorder, add, remove, retitle) saved back and re-checked.
    Nothing is written when the slides tool, or the outline's own rules, refuse."""
    root = Path(root)
    current = json.loads((root / OUTLINE).read_text(encoding='utf-8'))
    if not isinstance(edited, list) or not all(isinstance(one, dict) for one in edited):
        raise WorkspaceError('The slides are a list, each one an object.')
    outline = {**current, 'slides': edited}
    with tempfile.TemporaryDirectory() as scratch:
        draft = Path(scratch) / f'outline-{secrets.token_hex(4)}.json'
        draft.write_text(json.dumps(outline), encoding='utf-8')
        try:
            report = slides.outline_check(draft, Path(brand))
        except WorkspaceError as refusal:
            raise WorkspaceError(' '.join(worker_tools.said_no(refusal))) from None
    findings = [f"{one.get('slide')}: {one.get('detail') or one.get('code')}"
                for one in report.get('findings') or ()]
    if findings:
        raise WorkspaceError('The outline cannot be saved. ' + ' '.join(findings))
    _write(root, outline)
