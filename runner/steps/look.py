"""The look of a deck: two or three directions a worker proposes, each drawn on the deck's
first content slide, and the one the person chooses.

What a caller needs to know
---------------------------
    work = look.look_work(root, run, request, error, brand, slides=None)   # the job
    look.keep_look(root, run, handed)                    # keep the options: work/look/options.json
    shown = look.preview_options(root, run, slides, renderer)   # [{'name', 'why', 'image'}]
    shown = look.draw_options(root, run, slides, renderer)      # the same in two: work/ only,
    look.show_options(root, run, shown)                          #   then look.md and the gate
    look.choose(root, run, name, note=None)              # look.json, outline.json, gate approved;
                                                         #   name, "Option <n>" or <n>

- The options are handed back as `look`, a kind checked by `check_look` and registered
  here: {"options": [{"name", "direction": {"focal", "neutral", "meanings"?, "motif"?},
  "why", "composition"}]}, two or three of them, with different names and directions.
  `composition` is the outline's first content slide drawn in that direction: one slide in
  the composition format, or a whole composition holding that one slide. The kind is
  registered as drawn, so each option's composition is compiled by the slides tool while
  the worker can still put it right.
- `brand` is the path of the deck's exported brand contract. The direction's colours must
  be colour roles the contract names.
- `preview_options` compiles and previews each option in work/look/<n>/ (never shared) and
  writes look.md (shared), which lists them; it sets gate:look waiting. Previews are taken
  one at a time, as `build.how` says.
- `choose` writes look.json {chosen, direction, why} (shared), puts the direction and the
  person's words of approval into outline.json (`direction`, `approval`), records the name
  in run['look'] and approves gate:look.
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import home
from workspace import WorkspaceError, write_atomic

from runner import briefs, decks, slides as slides_tool, worker_tools
from runner.steps import Work, build, outline as outline_step

NAME = 'look'
GATE = 'gate:look'
OUTLINE = outline_step.OUTLINE
OPTIONS = Path('work') / 'look'
KEPT = OPTIONS / 'options.json'
LOOK_MD = 'look.md'
LOOK_JSON = 'look.json'
FEWEST, MOST = 2, 3
DIRECTION_KEYS = ('focal', 'neutral', 'meanings', 'motif')
READING = ('design guidance', 'composition guidance')


# --- the job ------------------------------------------------------------------------------

def _outline(root: Path) -> dict:
    try:
        found = json.loads((root / OUTLINE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        found = None
    if not isinstance(found, dict):
        raise WorkspaceError('There is no approved outline to design the look of.')
    return found


def first_content(outline: dict) -> dict:
    """The outline's first content slide, which every option is drawn on."""
    slide = next((one for one in build.slides_of(outline) if one.get('kind') == 'content'),
                 None)
    if slide is None:
        raise WorkspaceError('The outline has no content slide to show a look on.')
    return slide


def colours(brand) -> list[str]:
    """The colour roles a brand contract names, or none when it cannot be read."""
    found = home.read_json(Path(brand), {})
    roles = ((found or {}).get('design') or {}).get('colors') if isinstance(found, dict) \
        else None
    return sorted(roles) if isinstance(roles, dict) else []


def look_work(root, run: dict, request: dict | None, error: str | None, brand,
              slides=None) -> Work:
    """The job of proposing two or three looks for the deck, each drawn on its first
    content slide."""
    root, brand = Path(root), Path(brand)
    outline = _outline(root)
    slide = first_content(outline)
    tool = slides or slides_tool.Slides()
    inputs = {'The outline': json.dumps(outline, indent=2, ensure_ascii=False),
              "The brand's composition contract": tool.compose_contract(brand),
              'The layouts': json.dumps(tool.layouts(brand), indent=2)}
    inputs.update({name: text for name, text in tool.reading(brand).items()
                   if name in READING and text.strip()})
    form = run.get('form') or {}
    lines = [f"Deck title: {run.get('title') or form.get('title') or 'not given'}",
             f"Audience: {form.get('audience') or 'not given'}",
             f"Goal: {form.get('goal') or 'not given'}",
             f"Draw each option's composition on the outline's first content slide: "
             f"`{slide.get('id')}`, \"{slide.get('title')}\".",
             f'Hand your options back under the name "{NAME}".',
             'Your inputs: ' + ', '.join(inputs) + '.']
    note = (((run.get('gates') or {}).get(GATE) or {}).get('note')
            or (request or {}).get('note'))
    if note:
        lines.append(f'The person asked for this change to the looks:\n\n{note}')
    if error:
        lines.append(f'An earlier try at this job did not work: {error}\n'
                     'Take care not to end the same way.')
    spec = {'kind': 'look', 'brand': str(brand), 'slide': slide.get('id'),
            'title': outline.get('title') or run.get('title') or 'Deck',
            'colours': colours(brand)}
    return Work(guidance=briefs.guidance('look'), task='\n\n'.join(lines), profile='write',
                name=NAME, prepared={'inputs': inputs, 'artifacts': {NAME: spec},
                                     'ask': False})


# --- what is handed back -------------------------------------------------------------------

def _drawn_slide(composition):
    """The one slide a composition draws: given alone, or as a composition's only slide."""
    if isinstance(composition, dict) and isinstance(composition.get('slides'), list):
        return composition['slides'][0] if len(composition['slides']) == 1 else None
    return composition


def _option(number: int, option, spec: dict) -> list[str]:
    label = f'Option {number}'
    if not isinstance(option, dict):
        return [f'{label} is an object with name, direction, why and composition.']
    problems = []
    if not isinstance(option.get('name'), str) or not option['name'].strip():
        problems.append(f'{label}: "name" is two or three words.')
    if not isinstance(option.get('why'), str) or not option['why'].strip():
        problems.append(f'{label}: "why" says in a sentence or two why this look suits the '
                        'deck.')
    direction, known = option.get('direction'), spec.get('colours') or []
    if not isinstance(direction, dict):
        problems.append(f'{label}: "direction" is an object with "focal" and "neutral".')
    else:
        extra = [key for key in direction if key not in DIRECTION_KEYS]
        if extra:
            problems.append(f'{label}: "direction" takes only ' + ', '.join(DIRECTION_KEYS)
                            + '; leave out ' + ', '.join(extra) + '.')
        for key in ('focal', 'neutral'):
            value = direction.get(key)
            if not isinstance(value, str) or not value:
                problems.append(f'{label}: "direction.{key}" is one of the brand\'s colour '
                                'names.')
            elif known and value not in known:
                problems.append(f'{label}: "{value}" is not a colour the brand names. Use '
                                'one of: ' + ', '.join(known) + '.')
        if direction.get('focal') and direction.get('focal') == direction.get('neutral'):
            problems.append(f'{label}: "focal" and "neutral" are different colours.')
        if 'meanings' in direction and not isinstance(direction['meanings'], dict):
            problems.append(f'{label}: "direction.meanings" maps a colour name to what it '
                            'stands for.')
        if 'motif' in direction and not isinstance(direction['motif'], str):
            problems.append(f'{label}: "direction.motif" is a sentence.')
    slide = _drawn_slide(option.get('composition'))
    if not isinstance(slide, dict) or not slide:
        problems.append(f'{label}: "composition" is the drawing of one slide.')
    elif spec.get('slide') and slide.get('id') != spec['slide']:
        problems.append(f"{label}: the composition draws the slide `{spec['slide']}`, with "
                        'its ID.')
    return problems


def check_look(text: str, spec: dict, slides, scratch: Path):
    """The looks a worker proposed: their shape, and each option's composition compiled by
    the slides tool. Returns problems, the checks that ran, warnings and the text to keep."""
    try:
        given = json.loads(text)
    except ValueError as failure:
        return [f'The looks are not valid JSON ({failure}).'], [], [], text
    options = given.get('options') if isinstance(given, dict) else None
    if not isinstance(options, list):
        problems = ['The looks are one JSON object with the options under "options".']
    elif not FEWEST <= len(options) <= MOST:
        problems = [f'Offer two or three options, not {len(options)}.']
    else:
        problems = [problem for number, option in enumerate(options, start=1)
                    for problem in _option(number, option, spec)]
        # As the page and `choose` call them: whitespace aside, and "Option <n>" for none.
        names = [(' '.join(str(option.get('name') or '').split()) or f'Option {number}')
                 .lower() for number, option in enumerate(options, start=1)
                 if isinstance(option, dict)]
        if len(set(names)) != len(names):
            problems.append('Give each option a name of its own.')
        directions = [json.dumps(option.get('direction'), sort_keys=True)
                      for option in options if isinstance(option, dict)]
        if len(set(directions)) != len(directions):
            problems.append('Each option has a direction of its own.')
    ran = [worker_tools.result('look.options', problems)]
    if problems:
        return problems, ran, [], text
    compiled = []
    for number, option in enumerate(options, start=1):
        draft = Path(scratch) / f'look-{number}-{secrets.token_hex(4)}.json'
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(json.dumps(_composition(option, spec.get('title') or 'Deck')),
                         encoding='utf-8')
        try:
            slides.compile(draft, spec['brand'])
        except WorkspaceError as refusal:
            compiled += [f"Option {number} (\"{option['name']}\") does not compile: {line}"
                         for line in worker_tools.said_no(refusal)]
    ran.append(worker_tools.result('look.compile', compiled))
    return compiled, ran, [], text


worker_tools.register(NAME, check_look, drawn=True)


def keep_look(root, run: dict, handed) -> Path:
    """Keep the options a worker handed back, in work/look/options.json."""
    text = handed if isinstance(handed, str) else json.dumps(handed, ensure_ascii=False)
    path = Path(root) / KEPT
    write_atomic(path, text if text.endswith('\n') else text + '\n')
    return path


def _options(root: Path) -> list[dict]:
    found = home.read_json(root / KEPT, None)
    options = found.get('options') if isinstance(found, dict) else None
    if not isinstance(options, list) or not options:
        raise WorkspaceError('No looks have been proposed yet.')
    return options


# --- seeing them ---------------------------------------------------------------------------

def _composition(option: dict, title: str) -> dict:
    composition, direction = option['composition'], option['direction']
    if isinstance(composition.get('slides'), list):
        return {'version': 1, 'title': title, **composition, 'direction': direction}
    return {'version': 1, 'title': title, 'direction': direction, 'slides': [composition]}


def _markdown(shown: list[dict], options: list[dict]) -> str:
    lines = ['# The look', '', 'Choose one of these for the whole deck. Each is drawn on '
             "the deck's first content slide.", '']
    for number, (one, option) in enumerate(zip(shown, options), start=1):
        direction = option['direction']
        lines += [f"## {number}. {one['name']}", '', one['why'], '',
                  f"Colours: {direction['focal']} draws the eye, on {direction['neutral']}."]
        if direction.get('motif'):
            lines.append(f"Returning on every slide: {direction['motif']}")
        for role, meaning in (direction.get('meanings') or {}).items():
            lines.append(f'{role} stands for {meaning}.')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def preview_options(root, run: dict, slides, renderer) -> list[dict]:
    """Draw each option: compile and preview it in work/look/<n>/. Writes look.md, which
    lists them, and sets the gate waiting. Returns [{'name', 'why', 'image'}]. A caller
    that must not hold its lock through the drawing calls `draw_options`, then
    `show_options` under its lock."""
    return show_options(root, run, draw_options(root, run, slides, renderer))


def draw_options(root, run: dict, slides, renderer) -> list[dict]:
    """Compile and preview each option in work/look/<n>/. Only work/ is written. Returns
    [{'name', 'why', 'image'}]."""
    root = Path(root)
    options, outline = _options(root), _outline(root)
    brand = root / build.CONTRACT
    title = outline.get('title') or run.get('title') or 'Deck'
    for old in (root / OPTIONS).iterdir() if (root / OPTIONS).is_dir() else ():
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
    shown, settings = [], build.how(root, run, renderer)
    for number, option in enumerate(options, start=1):
        folder = root / OPTIONS / str(number)
        try:
            folder.mkdir(parents=True)
            home.write_json(folder / 'composition.json', _composition(option, title))
            slides.compile(folder / 'composition.json', brand, folder=folder / 'compiled')
            found = worker_tools.render(slides, folder / 'compiled', folder / 'preview',
                                        settings)
            first = (found.get('slides') or [None])[0]
            image = Path(str((first or {}).get('image'))).resolve()
            if (folder / 'preview').resolve() not in image.parents:
                raise WorkspaceError('The renderer drew no picture of it.')
            (folder / 'picture.png').write_bytes(worker_tools.picture(image))
        except (WorkspaceError, OSError, KeyError, TypeError, ValueError) as refusal:
            shutil.rmtree(folder, ignore_errors=True)
            raise WorkspaceError(f"The look \"{option.get('name')}\" could not be drawn. "
                                 f'{refusal}') from None
        shown.append({'name': option['name'], 'why': option['why'],
                      'image': str(folder / 'picture.png')})
    return shown


def show_options(root, run: dict, shown: list[dict]) -> list[dict]:
    """Write look.md, which lists the drawn options, and set the gate waiting."""
    root = Path(root)
    write_atomic(root / LOOK_MD, _markdown(shown, _options(root)))
    gate = (run.setdefault('gates', {})).get(GATE) or {}
    run['gates'][GATE] = {**gate, 'state': 'waiting', 'round': int(gate.get('round') or 0) + 1}
    decks.write_run(root, run)
    return shown


# --- the choice ----------------------------------------------------------------------------

def choose(root, run: dict, name: str, note: str | None = None) -> None:
    """Record the look the person chose: look.json, and its direction and their words of
    approval in outline.json. The gate is approved."""
    root = Path(root)
    options = _options(root)
    # The page calls a look with no name "Option <n>", so that, or the number alone, is the
    # look at that place.
    called = [' '.join(str(one.get('name') or '').split()) or f'Option {number}'
              for number, one in enumerate(options, start=1)]
    wanted = ' '.join(str(name or '').split()).lower()
    numbered = re.fullmatch(r'(?:option )?(\d+)', wanted)
    place = next((number for number, said in enumerate(called) if said.lower() == wanted),
                 None)
    if place is None and numbered and 1 <= int(numbered[1]) <= len(options):
        place = int(numbered[1]) - 1
    if place is None:
        raise WorkspaceError('Choose one of the looks shown: '
                             + ', '.join(f'"{said}"' for said in called) + '.')
    option = {**options[place], 'name': called[place]}
    at = home.now()
    note = (note or '').strip() or None
    write_atomic(root / LOOK_JSON, json.dumps(
        {'chosen': option['name'], 'direction': option['direction'], 'why': option['why']},
        indent=2, ensure_ascii=False) + '\n')
    outline = _outline(root)
    said = (((run.get('gates') or {}).get('gate:outline') or {}).get('note'))
    words = [f"Approved on the page, {at}, with the look \"{option['name']}\"."]
    words += [line for line in (said, note) if line]
    outline.update(direction=option['direction'], approval=words)
    write_atomic(root / OUTLINE, json.dumps(outline, indent=2, ensure_ascii=False) + '\n')
    gate = (run.setdefault('gates', {})).get(GATE) or {}
    run['gates'][GATE] = {**gate, 'state': 'approved', 'at': at, 'by': 'page',
                          'note': note}
    run['look'] = option['name']
    decks.write_run(root, run)
