"""Building a deck: the brand it is drawn in, its sections and their composers, the whole
deck put together and reviewed, the sections a review sends back, and the deck rendered.

What a caller needs to know
---------------------------
    contract = build.export_brand(root, run, brand_skill)   # brand/brand-contract.json
    start = build.start(root, run, slides, contract)          # split into sections
    build.to_draw(root)                                       # the sections still to draw
    work = build.section_work(root, run, section, request, error, renderer='local')
    build.keep_section(root, run, section, handed)            # what its composer handed in
    made = build.whole(root, run, slides, renderer)           # merged, compiled, previewed
    made = build.draw_whole(root, run, slides, renderer)      # the same, work/ only; then
    build.share_sheet(root)                                   #   contact-sheet.png
    work = build.review_work(root, run)                       # by a worker that drew none
    found = build.keep_review(root, run, handed)              # the findings, each with its section
    build.repair_sections(found)                              # the sections they send back
    deck = build.render(root, run, slides, brand=None, renderer='local')   # work/deck.pptx
    shown = build.gate_view(root, run)                        # what gate:build shows
    build.picture_deck(root, run, deck, folder, slides, renderer)    # any deck, pictured

    spec = build.fixed(whole, ids, number)      # what a section's composer may not change
    build.kept(section, spec)                   # what the runner refuses in a section
    build.checked(finding, slides)              # one finding of a review, or why it is wrong
    build.slides_of(outline)                    # an outline's slides
    build.plain(text)                           # text as it is compared

- Shared with the team: brand/ (brand-contract.json, DESIGN.md, VOICE.md, version.txt, the
  contract's revision), contact-sheet.png and reviews/build-<n>.md, one for each round's
  review. Everything else is under work/build/ and never shared: the start the slides tool
  split the deck into, what each composer drew, each round's build and its pictures, and
  state.json, which records them. work/build/preview/ holds the pictures of the last round,
  <n>.png, with shots.json ({"slides": [{"number", "image"}]}) for `existing.pairs`.
- The brand is exported once. A later export finds it there and has the brand skill check
  it; a brand that changed since stops the deck with BRAND_CHANGED (run['halted']).
- `start` takes the approved outline with its direction (the chosen look's, or DIRECTION),
  the template layout for each lead slide, the house rules and the person's words of
  approval. An existing deck at brand-only, polish or redesign has one line more in its
  house rules, FREEDOM[level], which says how far its slides may move.
- At brand-only and polish, a slide whose original shows no words (`outline.wordless`) is
  set by the runner, not its composer, on a template layout that shows no title
  (`bare_layout`, from `compose layouts`), with the original's picture in the layout's
  slot (`existing.original_picture`). That is done only when both the picture can be
  carried and the template has such a layout with a picture slot: a slide is never left
  blank. The start records them as 'wordless'; the composer hands each in as given, and
  `kept` refuses any other layout, picture or drawing on it. Any other such slide is
  recorded as 'titled': its composer draws it as before, with no words but its approved
  title, and gate:build shows TITLED on it.
- `to_draw` is every section not yet drawn, and every section a review or the person sent
  back that was not drawn again since the last round. A review sends back each section with
  a major or critical finding about how one of its slides is drawn, for at most REPAIRS
  rounds; after that the findings stand for the person.
- `whole` copies the round's contact sheet to contact-sheet.png and records the previewed
  deck and its hash. `render` copies that deck, the one the reviewer looked at, to
  work/deck.pptx once its hash still matches; nothing is rendered afresh. At the 'selected'
  level it makes work/patched.pptx with `existing.apply_patch` and pictures it, under the
  computer's one turn at the renderer and through the deck's one Drive preview file.
  Only the deck `render` recorded is delivered: a new round removes it. With `brand` it runs the
  brand's own audit over the deck, which `gate_view` shows.
- Nothing here starts a worker. A job is a `Work`; what it hands back is given to the
  matching keep function.
- Pure helpers, as Training Studio's runner/deck.py has them: a section keeps every approved
  word: `kept` holds its title, subtitle, detail, sources, caveat, source line and notes to
  the outline's, and looks for each point's words among the text the slide draws. At brand
  only and polish (STRICT) it also refuses drawn text that says anything the slide was not
  approved with. What is drawn, and how, is
  the composer's. A finding is about `drawing` or about `content`. QUESTIONS are the eight
  the slides tool asks of every slide, numbered as it numbers them, in the runner's words.
  The tool's own are not handed to a caller, so a change to them there has to be made here
  too.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import home
from workspace import WorkspaceError, write_atomic

from runner import briefs, decks, slides as slides_tool
from runner.steps import Work

PREVIEWS = 4            # times one composer may render its section
REPAIRS = 2             # rounds of drawing again after a review
DELIVERY = 'reading'    # a deck is read alone as well as presented
DIRECTION = {'focal': 'headingPrimary', 'neutral': 'canvasSecondary'}
SEVERITIES = ('critical', 'major', 'minor')
ABOUT = ('drawing', 'content')
STRICT = ('brand-only', 'polish')    # levels whose slides draw only the approved words
NOTE = 12               # the shortest note the slides tool takes for a finding
QUESTIONS = (
    'After three seconds, is the main point clear, and is it the claim in the title?',
    'Does the eye land first on what carries the point?',
    'Is there exactly one emphasis?',
    'Does everything on the slide support the title?',
    'Is each label inside or right beside what it names?',
    'Is the space balanced, with nothing stranded or crowded?',
    'Is the slide consistent with its neighbours in style, and different from them in '
    'layout unless they are meant to be compared?',
    'Does every picture and icon explain something?',
)
WORD = re.compile(r"[^\W_]+(?:['’.-][^\W_]+)*")


# --- an outline ----------------------------------------------------------------------------

def plain(text) -> str:
    """Text as it is compared: lower case, one space between its words, nothing else."""
    return ' '.join(WORD.findall(text.lower())) if isinstance(text, str) else ''


def _points(slide: dict) -> list[dict]:
    return [point for point in slide.get('points') or () if isinstance(point, dict)]


def slides_of(outline) -> list[dict]:
    """An outline's slides, leaving out anything that is not one."""
    found = outline.get('slides') if isinstance(outline, dict) else None
    return [slide for slide in found or () if isinstance(slide, dict)]


def fixed(whole: dict, ids: list[str], number: int, strict: bool = False,
          bare=(), placed=None) -> dict:
    """What the composer of one section may not change: the deck's title and direction,
    and for each of its slides the title, the subtitle and detail, the sources, the points,
    the caveat, the source line and the notes that were approved. With `strict` (brand only
    and polish) the slide draws no words but those, and a slide in `bare`, whose original
    shows no words, draws none: its title is only a label. Such a slide that `placed` sets
    on a template layout ({id: {'layout', 'picture'?}}, from `start`) keeps that layout and
    picture, which show no title."""
    by_id = {slide.get('id'): slide for slide in slides_of(whole)}
    placed = (placed or {}) if strict else {}
    return {'title': whole.get('title'), 'direction': whole.get('direction') or DIRECTION,
            'prefix': f's{number}_', 'strict': bool(strict),
            'slides': [{'id': ident, 'title': by_id[ident].get('title'),
                        'bare': bool(strict) and ident in bare,
                        **({key: value for key, value in placed[ident].items()
                            if key in ('layout', 'picture')}
                           if ident in bare and ident in placed else {}),
                        'subtitle': by_id[ident].get('subtitle'),
                        'detail': by_id[ident].get('detail'),
                        'focal': by_id[ident].get('focal'),
                        'sources': list(by_id[ident].get('sources') or ()),
                        'points': [{'label': point.get('label'), 'text': point.get('text')}
                                   for point in _points(by_id[ident])],
                        'caveat': by_id[ident].get('caveat'),
                        'source': by_id[ident].get('source'),
                        'notes': by_id[ident].get('notes')} for ident in ids]}


# --- a section, as it is handed in -------------------------------------------------------

def _drawn(node, found: list[str], ids: list[str]) -> None:
    """Every piece of text a drawing shows, in the order it is written, and every ID in it.
    A badge's character is not one of the slide's words."""
    if isinstance(node, list):
        for item in node:
            _drawn(item, found, ids)
    elif isinstance(node, dict):
        if isinstance(node.get('id'), str) and ('type' in node or 'from' in node):
            ids.append(node['id'])
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                _drawn(value, found, ids)
            elif isinstance(value, str) and key in ('text', 'value', 'label', 'title') \
                    and node.get('type') != 'badge':
                found.append(value)


def _same(one, other) -> bool:
    return ' '.join(str(one or '').split()) == ' '.join(str(other or '').split())


def _caveat(slide: dict):
    stated = slide.get('caveat')
    return stated.get('text') if isinstance(stated, dict) else stated


def _approved(slide: dict) -> list:
    """Every text a slide was approved with that it may show."""
    return [None if slide.get('bare') else slide.get('title'), slide.get('subtitle'),
            slide.get('detail'), slide.get('focal'),
            *(point[key] for point in slide['points'] for key in ('label', 'text')),
            slide.get('caveat'), slide.get('source')]


def _only(text: str, approved: list[str]) -> bool:
    """Whether a drawn text says nothing but approved words: whole approved texts, one
    after another, and at most one part of an approved text, cut between words."""
    left = f' {text} '
    for one in sorted(approved, key=len, reverse=True):
        left = left.replace(f' {one} ', ' ')
    left = left.strip()
    return not left or any(f' {left} ' in f' {one} ' for one in approved)


def _set_on_layout(mine: dict, theirs: dict) -> list[str]:
    """What is wrong with a slide the runner set on a template layout that shows no title:
    it keeps that layout and its picture, and draws nothing."""
    ident, problems = theirs['id'], []
    if mine.get('layout') != theirs['layout']:
        problems.append(f"{ident}: `layout` is fixed: {json.dumps(theirs['layout'])}. It "
                        'shows no title, because the slide had no words of its own.')
    if mine.get('picture') != theirs.get('picture'):
        problems.append(f"{ident}: `picture` is fixed: {json.dumps(theirs['picture'])}"
                        if theirs.get('picture') else f'{ident}: the slide has no picture.')
    drawn = [key for key in ('canvas', 'connect', 'subtitle', 'detail', 'caveat', 'source')
             if key in mine]
    if drawn:
        problems.append(f'{ident}: draw nothing on this slide, and write no text on it: it '
                        'had no words of its own. Leave out ' + ', '.join(
                            f'`{key}`' for key in drawn) + '.')
    return problems


def kept(section, spec: dict) -> list[str]:
    """What the runner refuses in a section: anything that was fixed before its composer
    started and is not as it was, and any approved word that is gone."""
    if not isinstance(section, dict):
        return ['A section is one JSON object.']
    problems = []
    if section.get('direction') != spec['direction']:
        problems.append('`direction` is copied unchanged: ' + json.dumps(spec['direction']))
    if section.get('title') != spec['title']:
        problems.append(f"`title` is the deck's title: {json.dumps(spec['title'])}")
    slides = [slide for slide in section.get('slides') or () if isinstance(slide, dict)] \
        if isinstance(section.get('slides'), list) else []
    wanted = [slide['id'] for slide in spec['slides']]
    if [slide.get('id') for slide in slides] != wanted:
        return problems + ['The slides are exactly these, in this order: '
                           + ', '.join(wanted) + '.']
    for mine, theirs in zip(slides, spec['slides']):
        ident = theirs['id']
        if mine.get('title') != theirs['title']:
            problems.append(f"{ident}: the title is fixed: {json.dumps(theirs['title'])}")
        if mine.get('sources') != theirs['sources']:
            problems.append(f"{ident}: `sources` is fixed: {json.dumps(theirs['sources'])}")
        if theirs.get('layout'):
            problems += _set_on_layout(mine, theirs)
        elif 'layout' in mine:
            problems.append(f'{ident}: a slide you draw names no template layout.')
        texts, ids = [], []
        _drawn([mine.get('canvas'), mine.get('connect')], texts, ids)
        wrong = [found for found in ids if not found.startswith(spec['prefix'])]
        if wrong:
            problems.append(f"{ident}: every node and edge ID starts with {spec['prefix']}. "
                            'These do not: ' + ', '.join(wrong[:8]) + '.')
        on_slide = ' ' + ' '.join(plain(text) for text in texts) + ' '
        gone = [text for point in theirs['points'] for text in (point['label'], point['text'])
                if plain(text) and f' {plain(text)} ' not in on_slide]
        problems += [f'{ident}: these approved words are missing or changed: '
                     f'{json.dumps(text)}' for text in gone]
        if spec.get('strict'):
            approved = [plain(text) for text in _approved(theirs) if plain(text)]
            added = [text for text in texts if not _only(plain(text), approved)]
            if added:
                problems.append(f'{ident}: these words were not approved for the slide: '
                                + ', '.join(json.dumps(text) for text in added[:8])
                                + '. Draw only the approved words.')
        for name, got in (('subtitle', mine.get('subtitle')), ('detail', mine.get('detail')),
                          ('caveat', _caveat(mine)), ('source', mine.get('source')),
                          ('notes', mine.get('notes'))):
            if not _same(got, theirs.get(name)):
                problems.append(f'{ident}: `{name}` stays exactly as it was approved'
                                + (f': {json.dumps(theirs.get(name))}' if theirs.get(name)
                                   and name != 'notes' else '.' if theirs.get(name)
                                   else ': the slide has none.'))
    return problems


# --- what a review finds -----------------------------------------------------------------

def checked(finding, slides: list[dict]) -> tuple[dict | None, str | None]:
    """One finding of a review as it is kept, or why it cannot be. `slides` are the
    slides that were looked at, each with its `id` and `number`."""
    if not isinstance(finding, dict):
        return None, 'A finding is an object with slide, question, severity and note.'
    numbers = {slide['id']: slide['number'] for slide in slides}
    ident, question = finding.get('slide'), finding.get('question')
    if ident not in numbers:
        return None, f'{ident!r} is not a slide of this deck. Name a slide by its ID.'
    if type(question) is not int or not 1 <= question <= len(QUESTIONS):
        return None, f'{ident}: `question` is a number from 1 to {len(QUESTIONS)}.'
    if finding.get('severity') not in SEVERITIES:
        return None, f'{ident}: `severity` is one of: ' + ', '.join(SEVERITIES) + '.'
    note = finding.get('note')
    if not isinstance(note, str) or len(note.strip()) < NOTE:
        return None, f'{ident}: `note` is one sentence on what is wrong on the slide.'
    if finding.get('about', ABOUT[0]) not in ABOUT:
        return None, f'{ident}: `about` is one of: ' + ', '.join(ABOUT) + '.'
    fix = finding.get('fix')
    return {'slide': ident, 'number': numbers[ident], 'question': question,
            'severity': finding['severity'], 'about': finding.get('about', ABOUT[0]),
            'note': note.strip(),
            'fix': fix.strip() if isinstance(fix, str) and fix.strip() else None}, None


# --- the brand -----------------------------------------------------------------------------

BRAND = Path('brand')
CONTRACT = BRAND / 'brand-contract.json'
VERSION = BRAND / 'version.txt'
BRAND_CHANGED = ('The brand changed since this deck began, so the deck has stopped: drawn '
                 'on, its slides would not match the ones made before. {said}')


class BrandChanged(WorkspaceError):
    """The brand a deck began with is not the brand as it is now."""


def _halt(root: Path, run: dict, said: str) -> None:
    why = BRAND_CHANGED.format(said=said).strip()
    run['halted'] = {'step': 'brand', 'why': why, 'at': home.now()}
    decks.write_run(root, run)
    raise BrandChanged(why)


def _revision(contract: Path) -> str:
    found = home.read_json(contract, {})
    return str(found.get('revision') or '') if isinstance(found, dict) else ''


def export_brand(root, run: dict, brand_skill) -> Path:
    """The deck's brand contract, exported into brand/ the first time and reused after
    that, once the brand skill has said it still holds. Returns its path."""
    root = Path(root)
    contract, form = root / CONTRACT, run.get('form') or {}
    if contract.is_file():
        try:
            checked = brand_skill.check(contract)
        except WorkspaceError as refusal:
            _halt(root, run, ' '.join(getattr(refusal, 'problems', None) or [str(refusal)]))
        try:
            kept = (root / VERSION).read_text(encoding='utf-8').strip()
        except OSError:
            kept = ''
        now = str(checked.get('revision') or '') if isinstance(checked, dict) else ''
        if kept and now and kept != now:
            _halt(root, run, f'It was revision {kept}, and is now {now}.')
        return contract
    shutil.rmtree(root / BRAND, ignore_errors=True)   # a folder an export left half made
    brand_skill.export(root / BRAND, form.get('brand'), form.get('variant'),
                       delivery=DELIVERY)
    write_atomic(root / VERSION, _revision(contract) + '\n')
    return contract


# --- where a build is kept -----------------------------------------------------------------

BUILD = Path('work') / 'build'
START = BUILD / 'start'
TOLD = BUILD / 'told'
DRAWN = BUILD / 'drawn'
STATE = BUILD / 'state.json'
DECK = Path('work') / 'deck.pptx'
SHEET = 'contact-sheet.png'
REVIEWS = Path('reviews')
SECTION = re.compile(r'^section-[1-9]\d{0,2}$')
PNG = b'\x89PNG\r\n\x1a\n'
PPTX = b'PK\x03\x04'
EMPTY = {'start': None, 'sections': {}, 'rounds': [], 'repair': [], 'asked': None,
         'repaired': 0, 'audit': None, 'auditNote': None, 'deck': None}
COMPOSING = ('design guidance', 'composition guidance', 'gallery')


def _tools():
    """The worker tools, which import this module themselves: so they are imported when
    they are first used, not with this module."""
    from runner import worker_tools
    return worker_tools


def _existing():
    """The existing-deck step, which imports the worker tools: imported when first used."""
    from runner.steps import existing
    return existing


def shots(root) -> Path:
    """Where the pictures of the last round are: existing.AFTER_SHOTS, which `pairs` reads."""
    return Path(root) / _existing().AFTER_SHOTS


def _outline_path(root) -> Path:
    from runner.steps import outline
    return Path(root) / outline.OUTLINE


def read_state(root) -> dict:
    """What this computer has built of a deck: work/build/state.json."""
    found = home.read_json(Path(root) / STATE, {})
    return {**EMPTY, **(found if isinstance(found, dict) else {})}


def write_state(root, state: dict) -> None:
    home.write_json(Path(root) / STATE, state)


def how(root, run: dict, renderer) -> dict:
    """How a deck's previews are taken, as `worker_tools.render` takes it: through
    `renderer` ('local' or 'drive'), one at a time on this computer, and through one
    preview file in Drive for the deck. A dict is taken as it is."""
    if isinstance(renderer, dict):
        return dict(renderer)
    title = run.get('title') or 'deck'
    return {'renderer': renderer, 'lock': str(home.data_root() / 'previews' / 'render.lock'),
            'kept': str(Path(root).resolve() / BUILD / 'drive-preview.json'),
            'named': {'name': f'Preview: {title}', 'deck': title}}


def _level(run: dict):
    return (run.get('form') or {}).get('level')


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return ''


# --- starting the deck ---------------------------------------------------------------------

LEADS = ('cover', 'section', 'closing')
NAMED_LAYOUTS = {'cover': ('title', 'cover'), 'section': ('section', 'divider'),
                 'closing': ('closing', 'end', 'title')}
HOUSE = (
    'Equals share one size and weight. Never set one of several peers larger, bolder or in '
    'another colour.',
    'The focal point is what the title singles out, and never one of several peers. A slide '
    'that lists equals has a focal that is not one of them.',
    'Draw nothing the title does not announce.',
    'Titles and labels are in sentence case. Names and acronyms stay as they are written.',
    'Boxes have square corners.',
    "A caveat and a source line go in the slide's own caveat and source fields, never in "
    'the drawing.',
    'Leave out badges, labels on arrows and small print wherever the slide reads without '
    'them.',
    'An icon is optional. Use one only where it names a recognisable thing, the same icon '
    'for the same thing, never twice on one slide.',
)
FREEDOM = {
    'brand-only': "Keep each slide's composition as close to the original as the brand's "
                  'layouts allow. Add no icons.',
    'polish': 'Keep wording and order; improve spacing, alignment and composition.',
    'redesign': 'Design each slide again from its content; keep its message and '
                'qualifications.',
}
POINTER = re.compile(r'Read `references/[^\n]*')


def house(run: dict) -> list[str]:
    """The house rules a deck is drawn by: the runner's own, and for an existing deck the
    line that says how far its slides may move."""
    level = _level(run) if run.get('route') == 'existing' else None
    return [*HOUSE, *([FREEDOM[level]] if level in FREEDOM else [])]


def layouts(listed, slides: list[dict]) -> dict:
    """The template layout for each kind of lead slide an outline has: one that shows a
    title, has room for the subtitle if there is one and no place for a picture, and is
    named for that kind of slide where the template has such a one."""
    chosen = {}
    listed = [layout for layout in listed or () if isinstance(layout, dict)
              and isinstance(layout.get('name'), str)]
    for kind in LEADS:
        mine = [slide for slide in slides if slide.get('kind') == kind]
        if not mine:
            continue
        need = 1 if any(slide.get('subtitle') for slide in mine) else 0
        fits = [layout for layout in listed
                if layout.get('title') and (layout.get('subtitles') or 0) >= need]
        fits = [layout for layout in fits if not layout.get('pictures')] or fits
        named = [layout for layout in fits
                 if any(word in layout['name'].lower() for word in NAMED_LAYOUTS[kind])] \
            or fits
        exact = [layout for layout in named if (layout.get('subtitles') or 0) == need]
        if not named:
            raise WorkspaceError(
                f"The brand's template has no layout that shows the title of a {kind} "
                'slide' + (' with its subtitle' if need else '') + ', so the deck cannot '
                'be started with this brand.')
        chosen[kind] = (exact or named)[0]['name']
    return chosen


def complete(outline: dict, listed, words: list[str], rules: list[str]) -> dict:
    """An approved outline as the slides tool starts a deck from: with its direction, a
    layout for each kind of lead slide, the house rules, and the person's own words of
    approval."""
    return {**outline, 'delivery': outline.get('delivery') or DELIVERY,
            'direction': dict(outline.get('direction') or DIRECTION),
            'layouts': layouts(listed, slides_of(outline)), 'house': list(rules),
            'approval': list(words)}


def lead(part: dict) -> dict:
    """A lead slide's file as the compiler takes it. A cover has no second line under its
    subtitle: no layout holds one."""
    slides = [{key: value for key, value in slide.items() if key != 'detail'}
              if isinstance(slide, dict) else slide for slide in part.get('slides') or ()]
    return {**part, 'slides': slides}


def _part(text: str, heading: str, body: str, renamed: str | None = None) -> str:
    """A brief with what is under one heading replaced. A heading the brief does not have
    is added at its end."""
    new = f'## {renamed or heading}\n\n{body.strip()}\n'
    pattern = re.compile(rf'^## {re.escape(heading)}[^\n]*\n.*?(?=^## |\Z)', re.S | re.M)
    if pattern.search(text):
        return pattern.sub(lambda found: new + '\n', text, count=1)
    return text.rstrip('\n') + '\n\n' + new


def brief(written: str, whole: dict, previews: int = PREVIEWS) -> str:
    """The brief the slides tool wrote for one section, for a worker with tools and no
    files. Its slides, their order and the direction are kept as written."""
    skeleton = json.dumps({'version': 1, 'title': whole.get('title'),
                           'direction': whole.get('direction') or DIRECTION,
                           'slides': ['your slides, in order']}, ensure_ascii=False)
    text = POINTER.sub('Your instructions say how to work; `list_inputs` shows what you '
                       'can read.', written)
    text = _part(text, 'Paths', f'''
One JSON object, the section, handed in with `submit_section`:

```json
{skeleton}
```

Each slide is `{{"id", "title", "sources", "brief": {{"relation", "focal": the ID of the node that carries the point, "rhythm"}}, "canvas", "connect"?, "caveat"?, "source"?, "notes"}}`. Copy each slide's `id`, `title`, `sources`, caveat, source line and notes exactly as they are given below, and keep every word of every point. The input "composition contract" has the exact format.''',
                 'What you write')
    text = _part(text, 'House style', '\n'.join(
        f'- {line}' for line in whole.get('house') or HOUSE))
    text = _part(text, 'Preview', f'''
`preview_section` renders your whole section and returns a picture of every slide, with what the renderer found. You have {previews} previews. `check_section` is free: use it until the section compiles before you spend a preview.''')
    return _part(text, 'Return', '''
Hand the section in with `submit_section`. It must be the version you last previewed. Say what you changed after looking at the pictures and what still bothers you, naming your weakest slide.''')


def named_in(written: str, whole: dict) -> list[str]:
    """The slides a section's brief gives its worker, by ID, in the outline's order."""
    return [slide['id'] for slide in slides_of(whole)
            if slide.get('kind') == 'content' and f"`{slide.get('id')}`" in written]


def reading_file(name: str) -> str:
    """Where one piece of the slides tool's guidance is kept for a deck's workers."""
    return 'reading/' + re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') + '.txt'


def _approval(root: Path, run: dict, outline: dict) -> list[str]:
    said = [line for line in outline.get('approval') or () if isinstance(line, str)]
    if said:
        return said
    gate = (run.get('gates') or {}).get('gate:outline') or {}
    return [f"Approved on the page, {gate.get('at') or home.now()}.",
            *([gate['note']] if gate.get('note') else [])]


TITLED = ("This slide is drawn with a title because its picture can't be carried onto a "
          'layout without one.')


def bare_layout(listed) -> str | None:
    """The template layout for a slide that had no words and whose picture is carried: one
    that shows no title, has no canvas and has a picture slot; of those, the one with the
    fewest subtitle lines. None when the template has none."""
    fits = [layout for layout in listed or () if isinstance(layout, dict)
            and isinstance(layout.get('name'), str) and not layout.get('title')
            and not layout.get('canvas') and layout.get('pictures')]
    if not fits:
        return None
    return min(fits, key=lambda layout: layout.get('subtitles') or 0)['name']


def wordless_slides(root, run: dict, outline: dict) -> list[str]:
    """The slides of an outline that, at brand only and polish, had no words of their own."""
    if run.get('route') != 'existing' or _level(run) not in STRICT:
        return []
    from runner.steps import outline as outlines   # it reaches build through worker_tools
    return outlines.wordless(outline, outlines.inventory_of(root), _level(run))


def _place_bare(root: Path, outline: dict, bare: list[str], listed,
                folder: Path) -> tuple[dict, list[str]]:
    """Each slide in `bare` whose original picture can be carried, set on a template layout
    that shows no title and has a slot for it: ({id: {'layout', 'picture': {src, alt}}},
    and the IDs of the others, which are drawn with their title)."""
    placed, titled = {}, []
    layout = bare_layout(listed)
    by_id = {slide.get('id'): slide for slide in slides_of(outline)}
    order = list(by_id)
    for ident in bare:
        picture = _existing().original_picture(root, order.index(ident) + 1, folder) \
            if layout else None
        if picture is None:
            titled.append(ident)
            continue
        placed[ident] = {'layout': layout, 'picture': {
            'src': picture['src'], 'alt': picture['alt'] or by_id[ident].get('title')}}
    return placed, titled


def start(root, run: dict, slides, brand) -> dict:
    """Start the deck from its approved outline: add the direction, the layouts for its
    lead slides and the house rules, have the slides tool split it into sections in
    work/build/start/, put the lead slides right, set each slide that had no words (at
    brand only and polish) on a template layout that shows no title, and rewrite each
    section's brief for a worker with tools and no files. Whatever an earlier start built
    is cleared."""
    root, brand = Path(root), Path(brand)
    try:
        outline = json.loads(_outline_path(root).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise WorkspaceError('There is no approved outline to build the deck from.') from None
    bare = wordless_slides(root, run, outline)
    work, folder = root / BUILD, root / START
    for old in (folder, root / TOLD, root / DRAWN, shots(root), *work.glob('whole-*')):
        shutil.rmtree(old, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    source = work / f'outline-{secrets.token_hex(3)}.json'
    try:
        listed = slides.layouts(brand).get('layouts')
        whole = complete(outline, listed, _approval(root, run, outline), house(run))
        home.write_json(source, whole)
        slides.outline_start(source, brand, folder)
        sections = []
        for part in home.read_json(folder / 'parts.json', {})['parts']:
            ident = Path(part).stem
            if not SECTION.match(ident):
                made = json.loads((folder / part).read_text(encoding='utf-8'))
                home.write_json(folder / part, lead(made))
                continue
            written = (folder / 'briefs' / f'{ident}.md').read_text(encoding='utf-8')
            ids = named_in(written, whole)
            if not ids:
                raise WorkspaceError(f'The slides tool gave {ident} no slides.')
            write_atomic(folder / 'given' / f'{ident}.md', brief(written, whole).replace(
                str(folder.resolve()), '.').replace(str(folder), '.').replace(
                str(Path.home()), '~'))
            sections.append({'id': ident, 'file': part, 'slides': ids})
        if not sections:
            raise WorkspaceError('The slides tool split the deck into no sections.')
        placed, titled = _place_bare(root, outline, bare, listed, folder / 'pictures')
        home.write_json(folder / 'given' / 'outline.json', whole)
        told = root / TOLD
        write_atomic(told / 'compose-contract.txt', slides.compose_contract(brand))
        for name, text in slides.reading(brand).items():
            write_atomic(told / reading_file(name), text)
    except (WorkspaceError, OSError, KeyError, ValueError, TypeError) as refusal:
        shutil.rmtree(folder, ignore_errors=True)
        shutil.rmtree(root / TOLD, ignore_errors=True)
        raise WorkspaceError(f'The deck could not be split into sections. {refusal}') from None
    finally:
        source.unlink(missing_ok=True)
    began = {'folder': START.as_posix(), 'brand': str(brand), 'sections': sections,
             'wordless': placed, 'titled': titled, 'at': home.now()}
    write_state(root, {**EMPTY, 'start': began})
    return began


# --- the sections --------------------------------------------------------------------------

def numbered(ident) -> int:
    """A section's number, from its ID: `section-2` is 2."""
    if not isinstance(ident, str) or not SECTION.match(ident):
        raise WorkspaceError('A section is named section-1, section-2 and so on.')
    return int(ident.rpartition('-')[2])


def _started(state: dict) -> dict:
    if not state.get('start'):
        raise WorkspaceError('The deck has not been split into sections yet.')
    return state['start']


def to_draw(root) -> list[str]:
    """The sections still to draw: each not drawn yet, and each a review or the person sent
    back that has not been drawn again since the last round."""
    state = read_state(root)
    if not state.get('start'):
        return []
    rounds, drawn = len(state['rounds']), state['sections']
    back = {*(state.get('repair') or ()), *((state.get('asked') or {}).get('sections') or ())}
    return [entry['id'] for entry in state['start']['sections']
            if entry['id'] not in drawn
            or (entry['id'] in back and drawn[entry['id']].get('round', 0) < rounds)]


def _shown(root: Path, slides: list[dict]) -> list[dict]:
    return [{**{key: slide[key] for key in ('number', 'id', 'title')},
             'image': str(shots(root) / f"{slide['number']}.png")} for slide in slides]


def _note(run: dict, request) -> str | None:
    gate = (run.get('gates') or {}).get('gate:build') or {}
    return (request or {}).get('note') or (gate.get('note') if gate.get('state') == 'changes'
                                           else None)


def section_work(root, run: dict, section: str, request: dict | None, error: str | None,
                 renderer='local') -> Work:
    """The job of drawing one section of the deck, or of drawing it again after a review
    or a request of the person's."""
    root = Path(root)
    state = read_state(root)
    began, number = _started(state), numbered(section)
    entry = next((one for one in began['sections'] if one['id'] == section), None)
    if entry is None:
        raise WorkspaceError(f'The deck has no {section}.')
    folder, ids = root / began['folder'], entry['slides']
    whole = home.read_json(folder / 'given' / 'outline.json', {})
    told = root / TOLD
    inputs = {'brief': _read(folder / 'given' / f'{section}.md'),
              'composition contract': _read(told / 'compose-contract.txt')}
    relations = sorted({slide.get('relation') for slide in slides_of(whole)
                        if slide.get('id') in ids and isinstance(slide.get('relation'), str)})
    for name in (*COMPOSING, *(slides_tool.example(relation) for relation in relations)):
        text = _read(told / reading_file(name))
        if text.strip():
            inputs[name] = text
    title = run.get('title') or whole.get('title') or 'the deck'
    drawn = state['sections'].get(section)
    last = state['rounds'][-1] if state['rounds'] else None
    found = [finding for finding in ((last or {}).get('review') or {}).get('findings') or ()
             if finding['slide'] in ids] if drawn else []
    note, look = _note(run, request), []
    lines = [f'Draw section {number} of "{title}": the slides in your input "brief".']
    if drawn:
        mine = [slide for slide in (last or {}).get('slides') or () if slide['id'] in ids]
        inputs['your earlier section'] = _read(root / drawn['file'])
        look = _shown(root, mine)
        lines = [f'Draw section {number} of "{title}" again. It was drawn and rendered with '
                 'the rest of the deck. Your input "your earlier section" is what was drawn, '
                 'and look_at_slide shows each of its slides as it was rendered. Put right '
                 'what is asked and leave alone what works.']
        if found:
            inputs['what the review found'] = told_findings(found, mine)
            lines.append('Your input "what the review found" lists what a reviewer found '
                         'wrong with how some of its slides are drawn.')
    lines += [f'Your inputs are {", ".join(inputs)}.', 'Hand the section in with '
              'submit_section.']
    if note:
        lines.append(f'The person asked for this change to the deck:\n\n{note}\n\nWhat a '
                     'slide says stays as it was approved: change how it is drawn.')
    if error:
        lines.append(f'An earlier try at this job did not work: {error}\n'
                     'Take care not to end the same way.')
    strict = run.get('route') == 'existing' and _level(run) in STRICT
    bare = wordless_slides(root, run, whole)
    placed = began.get('wordless') or {}
    drawn_bare = [ident for ident in ids if ident in bare and ident not in placed]
    if drawn_bare:
        lines.append('These slides show no words in the deck you were given, so draw no '
                     'text on them: ' + ', '.join(drawn_bare) + '.')
    fixed_spec = fixed(whole, ids, number, strict, bare, placed)
    set_bare = [slide for slide in fixed_spec['slides'] if slide.get('layout')]
    if set_bare:
        lines.append(
            'These slides show no words in the deck you were given, so each is set on a '
            'template layout that shows no title, and you draw nothing on them. Hand each in '
            'exactly as it is here, in its place among your slides, with no canvas, '
            'subtitle, caveat or source:\n\n' + '\n'.join(json.dumps(
                {key: slide[key] for key in ('id', 'title', 'sources', 'layout', 'picture',
                                             'notes') if slide.get(key)},
                ensure_ascii=False) for slide in set_bare))
    spec = {'kind': 'section', 'brand': began['brand'], **fixed_spec,
            'previews': PREVIEWS, **how(root, run, renderer)}
    return Work(guidance=briefs.guidance('section', repair=bool(found)),
                task='\n\n'.join(lines), profile='write', name='section',
                prepared={'inputs': inputs, 'ask': False, 'look': look,
                          'artifacts': {'section': spec}})


def keep_section(root, run: dict, section: str, handed) -> Path:
    """Keep what a section's composer handed in: the section as it was last previewed,
    and what it said of it. `handed` is what `worker_tools.collect` returned, or the
    section's text."""
    root = Path(root)
    state = read_state(root)
    _started(state)
    numbered(section)
    notes = None
    if isinstance(handed, dict):
        notes = (handed.get('review') or '').strip() or None
        handed = handed['artifacts']['section']['text']
    turn = len(state['rounds'])
    file = DRAWN / f'{section}-{turn}.json'
    write_atomic(root / file, handed if handed.endswith('\n') else handed + '\n')
    state['sections'][section] = {'file': file.as_posix(), 'round': turn, 'notes': notes,
                                  'at': home.now()}
    write_state(root, state)
    return root / file


# --- the whole deck ------------------------------------------------------------------------

def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def whole(root, run: dict, slides, renderer) -> dict:
    """Merge the drawn sections with the lead slides, compile the whole deck and preview
    it. Its pictures go to work/build/preview/, and its contact sheet to the shared
    contact-sheet.png. Only the last round's build is kept, and a try that fails leaves
    nothing. Returns the round. A caller that must not hold its lock through the drawing
    calls `draw_whole`, then `share_sheet` under its lock."""
    made = draw_whole(root, run, slides, renderer)
    share_sheet(root)
    return made


def share_sheet(root) -> None:
    """Copy the last round's contact sheet to the shared contact-sheet.png."""
    root = Path(root)
    state = read_state(root)
    sheet = (state['rounds'][-1].get('sheet') if state['rounds'] else None)
    if sheet and (root / sheet).is_file():
        shutil.copyfile(root / sheet, root / SHEET)


def draw_whole(root, run: dict, slides, renderer) -> dict:
    """`whole`, writing nothing outside work/: the contact sheet waits in the round's
    folder, as its `sheet`, for `share_sheet`."""
    root = Path(root)
    state = read_state(root)
    began = _started(state)
    left = to_draw(root)
    if left:
        raise WorkspaceError('These sections are not drawn yet: ' + ', '.join(left) + '.')
    start_folder, work = root / began['folder'], root / BUILD
    folder, pictures = work / f'whole-{secrets.token_hex(3)}', shots(root)
    drawn = state['sections']
    try:
        folder.mkdir(parents=True)
        shutil.copyfile(start_folder / 'parts.json', folder / 'parts.json')
        for part in home.read_json(start_folder / 'parts.json', {})['parts']:
            made = drawn.get(Path(part).stem)
            (folder / part).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / made['file'] if made else start_folder / part,
                            folder / part)
        slides.merge(folder / 'parts.json', folder / 'composition.json')
        slides.compile(folder / 'composition.json', Path(began['brand']),
                       folder=folder / 'compiled')
        shown = _tools().render(slides, folder / 'compiled', folder / 'preview',
                                    how(root, run, renderer))
        file = Path(str(shown['deck'])).resolve()
        if (folder / 'preview').resolve() not in file.parents \
                or file.read_bytes()[:4] != PPTX:
            raise WorkspaceError('The renderer did not leave a deck that can be opened.')
        digest = str(shown['deckSha256'])
        if _digest(file) != digest:
            raise WorkspaceError('The deck the renderer left is not the one it pictured.')
        pictured = _tools().pictures(shown, folder / 'preview', pictures)
        sheet = shown.get('contactSheet')
        sheet = Path(str(sheet)).resolve() if sheet else None
        if sheet is not None and ((folder / 'preview').resolve() not in sheet.parents
                                  or sheet.read_bytes()[:8] != PNG):
            sheet = None
    except (WorkspaceError, OSError, KeyError, ValueError, TypeError) as refusal:
        shutil.rmtree(folder, ignore_errors=True)
        shutil.rmtree(pictures, ignore_errors=True)
        raise WorkspaceError(f'The slides could not be put together and rendered. {refusal} '
                             'Nothing of that try was kept.') from None
    (root / DECK).unlink(missing_ok=True)   # a deck rendered from an earlier round
    home.write_json(pictures / _existing().SHOTS, {'slides': [
        {'number': slide['number'], 'image': f"{slide['number']}.png"} for slide in pictured]})
    for old in work.glob('whole-*'):
        if old != folder:
            shutil.rmtree(old, ignore_errors=True)
    before = {slide['number']: slide.get('sha256')
              for slide in (state['rounds'][-1]['slides'] if state['rounds'] else ())}
    slides_kept = [{**slide, 'sha256': _digest(pictures / f"{slide['number']}.png")}
                   for slide in pictured]
    made = {'at': home.now(), 'folder': folder.relative_to(root).as_posix(),
            'preview': (folder / 'preview').relative_to(root).as_posix(),
            'compiled': (folder / 'compiled').relative_to(root).as_posix(),
            'file': file.relative_to(root.resolve()).as_posix(), 'deck': digest,
            'review': None,
            'sheet': sheet.relative_to(root.resolve()).as_posix() if sheet else None,
            'made_from': {ident: entry['file'] for ident, entry in drawn.items()},
            'changed': [slide['number'] for slide in slides_kept
                        if before and before.get(slide['number']) != slide['sha256']],
            'slides': slides_kept}
    state['rounds'].append(made)
    state.update(repair=[], asked=None, deck=None, audit=None, auditNote=None)
    write_state(root, state)
    return made


# --- the review ----------------------------------------------------------------------------

SEVERITY_WORDS = {
    'critical': 'the slide misleads, cannot be read, or its point cannot be found.',
    'major': 'the slide works but is clearly weaker than it should be.',
    'minor': 'a small flaw.'}
GRAVE = SEVERITIES[:2]


def ordered(findings) -> list[dict]:
    """Findings as a person reads them: the gravest first, then in slide order."""
    return sorted(findings or (), key=lambda finding: (
        SEVERITIES.index(finding['severity']), finding['number']))


def grave(findings) -> list[dict]:
    """The findings that keep a deck from being called clear."""
    return [finding for finding in ordered(findings) if finding['severity'] in GRAVE]


def remains(findings) -> str:
    """What a review still finds, counted, in a sentence. A deck is never called clear
    while a major finding remains."""
    left = grave(findings)
    if not left:
        small = len(findings or ())
        return ('The review found nothing major' + (f', and {small} small thing'
                f'{"" if small == 1 else "s"} worth a look.' if small else '.'))
    critical = sum(finding['severity'] == 'critical' for finding in left)
    major = len(left) - critical
    parts = [f'{critical} critical'] if critical else []
    parts += [f'{major} major'] if major else []
    return ('This deck is not clear: the review still finds ' + ' and '.join(parts)
            + f" thing{'' if len(left) == 1 else 's'} wrong.")


def told_findings(findings, slides: list[dict]) -> str:
    """What a review found on some slides, as their composer is told it."""
    lines = ['# What the review found in your section', '',
             'Someone who drew none of these slides looked at each one as it was rendered '
             'and answered the same questions about it. Each "no" is below.', '']
    for slide in slides:
        mine = [finding for finding in ordered(findings) if finding['slide'] == slide['id']]
        if not mine:
            continue
        lines += [f"## Slide {slide['number']}: `{slide['id']}`, \"{slide['title']}\"", '']
        for finding in mine:
            what = ('This is about what the slide says, which is not yours to change: '
                    'leave the words as they are. ' if finding['about'] == ABOUT[1] else '')
            lines.append(f"- **{finding['severity']}**, "
                         f"\"{QUESTIONS[finding['question'] - 1]}\" {what}{finding['note']}"
                         + (f" Suggested: {finding['fix']}" if finding.get('fix') else ''))
        lines.append('')
    return '\n'.join(lines)


def asked(slides: list[dict], earlier=None) -> str:
    """What a reviewer is asked: the questions, how grave a "no" is, the slides, and on a
    later round what was found before."""
    lines = ['# The review', '', '## The questions, asked of every slide', '']
    lines += [f'{number}. {question}' for number, question in enumerate(QUESTIONS, start=1)]
    lines += ['', '## How grave a "no" is', '']
    lines += [f'- `{severity}`: {words}' for severity, words in SEVERITY_WORDS.items()]
    lines += ['', '## The slides', '']
    lines += [f"- {slide['number']}. `{slide['id']}`: \"{slide['title']}\"" for slide in slides]
    if earlier:
        lines += ['', '## What an earlier review found', '',
                  'These slides were drawn again since. Look for each of these, and where '
                  'one is not put right, record it again.', '']
        lines += [f"- Slide `{finding['slide']}`, {finding['severity']}, question "
                  f"{finding['question']}: {finding['note']}" for finding in ordered(earlier)]
    return '\n'.join(lines) + '\n'


def _last(state: dict) -> dict:
    if not state.get('rounds'):
        raise WorkspaceError('The deck has not been put together and rendered yet.')
    return state['rounds'][-1]


def review_work(root, run: dict) -> Work:
    """The job of reviewing the whole deck as it was rendered, by a worker that drew none
    of it. After a round of drawing again it is also told what was found before."""
    root = Path(root)
    state = read_state(root)
    last, rounds = _last(state), state['rounds']
    earlier = (rounds[-2].get('review') or {}).get('findings') if len(rounds) > 1 else None
    slides = _shown(root, last['slides'])
    task = (f"Review \"{run.get('title') or 'the deck'}\" as it was rendered: {len(slides)} "
            'slides. Your input "the review" has the questions and the slides. Look at '
            'every slide with look_at_slide, then hand in what you find with '
            'submit_assessment.')
    review = {'preview': str(root / last['preview']), 'deck': last['deck'], 'slides': slides,
              'recorded': str(root / last['folder'] / 'assessment.json')}
    return Work(guidance=briefs.guidance('review'), task=task, profile='write',
                prepared={'inputs': {'the review': asked(slides, earlier)}, 'ask': False,
                          'review': review})


def repair_sections(found) -> list[str]:
    """The sections a review sends back to their composers: each with a major or critical
    finding about how one of its slides is drawn, in section order."""
    named = {finding.get('section') for finding in grave(found)
             if finding.get('about') == ABOUT[0] and finding.get('section')}
    return sorted(named, key=numbered)


def _review_md(number: int, findings: list[dict], slides: list[dict], back: list[str],
               spent: bool) -> str:
    titles = {slide['id']: slide['title'] for slide in slides}
    lines = [f'# Review of the deck, round {number}', '', remains(findings), '']
    for finding in ordered(findings):
        lines.append(f"- Slide {finding['number']} ({titles.get(finding['slide'], '')}), "
                     f"{finding['severity']}, {finding['about']}: {finding['note']}"
                     + (f" Suggested: {finding['fix']}" if finding.get('fix') else ''))
    if findings:
        lines.append('')
    if back:
        lines.append('Drawn again: ' + ', '.join(back).replace('section-', 'section ') + '.')
    elif spent and grave(findings):
        lines.append(f'The slides were drawn again {REPAIRS} times after a review, which is '
                     'as many as a deck is given. What is left is yours to decide.')
    return '\n'.join(lines).rstrip() + '\n'


def keep_review(root, run: dict, handed) -> list[dict]:
    """Keep what the reviewer found in the last round, write it to reviews/build-<n>.md,
    and send back the sections with a major or critical drawing finding, for at most
    REPAIRS rounds. Returns the findings, each with the section its slide is in."""
    root = Path(root)
    state = read_state(root)
    last, began = _last(state), _started(state)
    assessed = handed.get('assessment') if isinstance(handed, dict) \
        and 'findings' not in handed else handed
    if not isinstance(assessed, dict) or not isinstance(assessed.get('findings'), list):
        raise WorkspaceError('The reviewer handed in no assessment.')
    where = {ident: entry['id'] for entry in began['sections'] for ident in entry['slides']}
    findings = [{**finding, 'section': where.get(finding.get('slide'))}
                for finding in assessed['findings']]
    last['review'] = {'findings': findings, 'weakest': list(assessed.get('weakest') or ()),
                      'at': home.now()}
    back = repair_sections(findings)
    spent = state.get('repaired', 0) >= REPAIRS
    if spent:
        back = []
    if back:
        state['repaired'] = state.get('repaired', 0) + 1
    state['repair'] = back
    write_state(root, state)
    number = len(state['rounds'])
    write_atomic(root / REVIEWS / f'build-{number}.md',
                 _review_md(number, findings, last['slides'], back, spent))
    return findings


# --- the deck ------------------------------------------------------------------------------

def _drawer(renderer) -> str:
    named = renderer.get('renderer') if isinstance(renderer, dict) else renderer
    return 'google' if named in ('drive', 'google') else 'local'


def audited(report) -> dict:
    """The brand's own audit of a deck, as its gate shows it: the skill's word, how many
    errors and warnings, and what each says."""
    messages = []
    for kind, found in (('error', report.get('blockers')), ('warning', report.get('warnings'))):
        for one in found or ():
            slide = f"Slide {one.get('slide')}: " if one.get('slide') is not None else ''
            messages.append(f"{slide}{one.get('says') or one.get('code')} ({kind})")
    return {'status': report.get('status'), 'errors': len(report.get('blockers') or ()),
            'warnings': len(report.get('warnings') or ()), 'messages': messages}


def picture_deck(root, run: dict, deck: Path, folder: Path, slides, renderer) -> dict:
    """A picture of every slide of `deck`, drawn into the new `folder`, under the computer's
    one turn at the renderer and through the deck's one preview file in Drive, which is
    remembered as `how` says. Returns what the slides tool's `pictures_of` returned."""
    tools, settings = _tools(), how(root, run, renderer)
    kept = Path(settings['kept'])
    with tools.one_at_a_time(Path(settings['lock'])):
        known = home.read_json(kept, {})
        known = known if isinstance(known, dict) else {}
        made = slides.pictures_of(deck, folder, _drawer(settings), file_id=known.get('id'))
        if made.get('fileId') and made['fileId'] != known.get('id'):
            home.write_json(kept, {**(settings.get('named') or {}),
                                   'id': made['fileId'], 'url': made.get('url')})
    return made


def _patched_pictures(root: Path, run: dict, deck: Path, slides, renderer) -> None:
    """Picture the patched deck into the last round's folder, under the computer's one turn
    at the renderer and through the deck's one preview file in Drive."""
    tools = _tools()
    folder, scratch = shots(root), root / BUILD / f'patched-{secrets.token_hex(3)}'
    shutil.rmtree(folder, ignore_errors=True)
    try:
        made = picture_deck(root, run, deck, scratch, slides, renderer)
        folder.mkdir(parents=True)
        listed = []
        for one in made['slides']:
            (folder / f"{one['number']}.png").write_bytes(tools.picture(Path(one['image'])))
            listed.append({'number': one['number'], 'image': f"{one['number']}.png"})
        home.write_json(folder / _existing().SHOTS, {'slides': listed})
        sheet = made.get('contactSheet')
        if sheet and Path(sheet).is_file() and Path(sheet).read_bytes()[:8] == PNG:
            shutil.copyfile(sheet, root / SHEET)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        deck.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def render(root, run: dict, slides, brand=None, renderer='local') -> Path:
    """The deck to deliver: work/deck.pptx, a copy of the deck the last round previewed and
    its reviewer looked at, once its hash is the one that round recorded; at the 'selected'
    level, work/patched.pptx with only the planned changes, pictured. With `brand`, the
    brand's own audit is run over it for the gate."""
    root = Path(root)
    state = read_state(root)
    if _level(run) == 'selected':
        deck = _existing().apply_patch(root, run, slides)
        _patched_pictures(root, run, deck, slides, renderer)
    else:
        last = _last(state)
        seen, deck = root / str(last.get('file')), root / DECK
        deck.unlink(missing_ok=True)
        if not last.get('file') or not seen.is_file() or _digest(seen) != last['deck']:
            raise WorkspaceError('The deck that was previewed and reviewed is not here as it '
                                 'was, so it is not delivered. Put the deck together again.')
        shutil.copyfile(seen, deck)
    audit, note = None, None
    form = run.get('form') or {}
    if brand is None:
        note = 'The brand skill was not there to check this deck.'
    else:
        try:
            audit = audited(brand.audit(deck, form.get('brand'), form.get('variant')))
        except WorkspaceError as refusal:
            note = f"The brand's check of this deck could not be run. {refusal}"
    state = read_state(root)
    state.update(deck=deck.relative_to(root).as_posix(), audit=audit, auditNote=note)
    write_state(root, state)
    return deck


def delivered_deck(root, run: dict) -> Path:
    """The deck to deliver: the one `render` made for the last round, and nothing else."""
    root = Path(root)
    kept = read_state(root).get('deck')
    deck = root / kept if kept else None
    if deck is None or not deck.is_file():
        raise WorkspaceError('The deck has not been rendered yet.')
    return deck


def _titles(root: Path) -> dict:
    found = home.read_json(root / 'classify.json', {})
    return {slide.get('number'): slide.get('title') or ''
            for slide in (found or {}).get('slides') or () if isinstance(slide, dict)}


def gate_view(root, run: dict) -> dict:
    """What gate:build shows: each slide's picture and what the review found on it, the
    contact sheet, the before and after of an existing deck, the slides that changed since
    the round before, and the brand's audit. The gate is set waiting."""
    existing = _existing()
    root = Path(root)
    state = read_state(root)
    if state['rounds']:
        last = state['rounds'][-1]
        found = ((last.get('review') or {}).get('findings')) or []
        titled = set((state.get('start') or {}).get('titled') or ())
        listed = [{'number': slide['number'], 'title': slide['title'],
                   'image': str(shots(root) / f"{slide['number']}.png"),
                   **({'note': TITLED} if slide.get('id') in titled else {}),
                   'findings': [{key: finding.get(key) for key in (
                       'severity', 'about', 'question', 'note', 'fix')}
                       for finding in ordered(found) if finding['slide'] == slide['id']]}
                  for slide in last['slides']]
        changed = list(last.get('changed') or ())
    else:
        titles = _titles(root)
        pictured = home.read_json(shots(root) / _existing().SHOTS, {}) or {}
        listed = [{'number': one['number'], 'title': titles.get(one['number'], ''),
                   'image': str(shots(root) / one['image']), 'findings': []}
                  for one in pictured.get('slides') or ()]
        changed = []
    sheet = root / SHEET
    gate = (run.setdefault('gates', {})).get('gate:build') or {}
    if gate.get('state') != 'waiting':
        run['gates']['gate:build'] = {**gate, 'state': 'waiting',
                                      'round': int(gate.get('round') or 0) + 1}
        decks.write_run(root, run)
    return {'slides': listed, 'contactSheet': str(sheet) if sheet.is_file() else None,
            'pairs': existing.pairs(root, run), 'changed': changed,
            'audit': state.get('audit'),
            'auditNote': state.get('auditNote') if state.get('audit') is None else None,
            'round': len(state['rounds'])}
