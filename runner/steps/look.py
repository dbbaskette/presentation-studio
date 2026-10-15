"""The brand a deck is made in, shown before any slide is designed: the deck's cover drawn in
that brand, so the person can see it is the brand they meant, and choose another if not.

What a caller needs to know
---------------------------
    shown = look.draw_sample(root, run, slides, renderer)   # work/look/sample.png; work/ only
    look.show_sample(root, run)                             # look.md, and the gate waiting
    look.preview_sample(root, run, slides, renderer)        # the two together
    look.rebrand(root, run, brand, variant, brands)         # another brand: the form, brand/
    look.approve(root, run, note=None)                      # the gate approved

- No look is chosen. The sample is the outline's cover, with its approved title and
  subtitle, on the template layout the build gives a cover (`build.layouts`), in the brand's
  own colours (`build.DIRECTION`). An outline with no cover is shown the deck's title on
  one. Nothing is kept from it: when the deck is built, every slide's layout is designed
  from what that slide says.
- `draw_sample` compiles and previews the cover in work/look/ (never shared) and keeps its
  picture as work/look/sample.png (SAMPLE). Previews are taken one at a time, as
  `build.how` says.
- `show_sample` writes look.md (shared), which names the brand, and sets gate:look waiting.
- `rebrand` puts another brand or variant the brand skill lists into the deck's form and
  intake.md, and removes the exported contract in brand/, so the next step that needs the
  brand exports the one chosen. It refuses one the brand skill does not list, and the one
  the deck is made in already.
- `approve` puts the person's words of approval into outline.json (`approval`), takes out a
  `direction` an earlier version of this step put there, so that the build uses the brand's
  own colours, and approves the gate.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import home
from workspace import WorkspaceError, write_atomic

from runner import decks, worker_tools
from runner.steps import build, outline as outline_step

GATE = 'gate:look'
OUTLINE = outline_step.OUTLINE
FOLDER = Path('work') / 'look'
SAMPLE = FOLDER / 'sample.png'
LOOK_MD = 'look.md'
COVER = 'cover'


def _outline(root: Path) -> dict:
    found = home.read_json(root / OUTLINE, None)
    if not isinstance(found, dict):
        raise WorkspaceError('There is no approved outline to draw a sample of.')
    return found


def cover(outline: dict, title: str) -> dict:
    """The slide the sample draws: the outline's cover, or the deck's title on one."""
    found = next((one for one in build.slides_of(outline) if one.get('kind') == COVER), None)
    if found is None:
        return {'id': COVER, 'kind': COVER, 'title': outline.get('title') or title}
    return found


def composition(outline: dict, title: str, listed) -> dict:
    """The sample as the slides tool compiles it: the cover alone, on the template layout a
    cover is given, in the brand's own colours."""
    slide = cover(outline, title)
    laid = {'id': slide.get('id') or COVER, 'title': slide.get('title') or title,
            'layout': build.layouts(listed, [slide])[COVER], 'sources': ['outline'],
            'brief': {'rhythm': 'anchor'}}
    if slide.get('subtitle'):
        laid['subtitle'] = slide['subtitle']
    return {'version': 1, 'title': outline.get('title') or title,
            'direction': dict(build.DIRECTION), 'slides': [laid]}


def draw_sample(root, run: dict, slides, renderer) -> Path:
    """Compile and preview the deck's cover in its brand, in work/look/. Only work/ is
    written. Returns the picture."""
    root = Path(root)
    brand = root / build.CONTRACT
    title = run.get('title') or 'Deck'
    shutil.rmtree(root / FOLDER, ignore_errors=True)
    folder = root / FOLDER
    try:
        folder.mkdir(parents=True)
        made = composition(_outline(root), title, slides.layouts(brand).get('layouts'))
        home.write_json(folder / 'composition.json', made)
        slides.compile(folder / 'composition.json', brand, folder=folder / 'compiled')
        found = worker_tools.render(slides, folder / 'compiled', folder / 'preview',
                                    build.how(root, run, renderer))
        first = (found.get('slides') or [None])[0]
        image = Path(str((first or {}).get('image'))).resolve()
        if (folder / 'preview').resolve() not in image.parents:
            raise WorkspaceError('The renderer drew no picture of it.')
        (root / SAMPLE).write_bytes(worker_tools.picture(image))
    except (WorkspaceError, OSError, KeyError, TypeError, ValueError) as refusal:
        shutil.rmtree(folder, ignore_errors=True)
        raise WorkspaceError(f'Your cover could not be drawn in the brand. {refusal}') \
            from None
    return root / SAMPLE


def _markdown(form: dict) -> str:
    return '\n'.join([
        '# The brand', '',
        f'This deck is made in {decks.brand_words(form)}. Its cover is drawn here in that '
        'brand, so you can see it is the one you meant.', '',
        'No layout is chosen here. When the deck is built, each slide is designed on its own '
        'from what it says.', ''])


def show_sample(root, run: dict) -> None:
    """Write look.md, which names the brand the sample is drawn in, and set the gate
    waiting."""
    root = Path(root)
    write_atomic(root / LOOK_MD, _markdown(run.get('form') or {}))
    gate = (run.setdefault('gates', {})).get(GATE) or {}
    run['gates'][GATE] = {**gate, 'state': 'waiting', 'round': int(gate.get('round') or 0) + 1}
    decks.write_run(root, run)


def preview_sample(root, run: dict, slides, renderer) -> Path:
    """Draw the sample, then show it. A caller that must not hold its lock through the
    drawing calls `draw_sample`, then `show_sample` under its lock."""
    drawn = draw_sample(root, run, slides, renderer)
    show_sample(root, run)
    return drawn


def rebrand(root, run: dict, brand, variant, brands) -> dict:
    """Make the deck in another brand or variant the brand skill lists: the form and
    intake.md name it, and the contract exported for the old one is removed. Returns the
    form."""
    root = Path(root)
    if not isinstance(brand, str) or not brand.strip():
        raise WorkspaceError('Choose the brand to make the deck in.')
    if variant is not None and not isinstance(variant, str):
        raise WorkspaceError('Choose one of the brand\'s variants.')
    form = run.get('form') or {}
    chosen = decks.deck_brand({**form, 'brand': brand.strip(),
                               'variant': (variant or '').strip() or None}, brands, None, None)
    if (chosen['brand'], chosen['variant']) == (form.get('brand'), form.get('variant')):
        raise WorkspaceError(f'This deck is made in {decks.brand_words(chosen)} already.')
    run['form'] = {**form, **chosen}
    decks.name_brand(root, run['form'])
    shutil.rmtree(root / build.BRAND, ignore_errors=True)
    return run['form']


def approve(root, run: dict, note: str | None = None) -> None:
    """Approve the brand: the person's words of approval go into outline.json, without a
    direction of an earlier look, and the gate is approved."""
    root = Path(root)
    at = home.now()
    note = (note or '').strip() or None
    outline = _outline(root)
    said = (((run.get('gates') or {}).get('gate:outline') or {}).get('note'))
    words = [f'Approved on the page, {at}, in {decks.brand_words(run.get("form") or {})}.']
    words += [line for line in (said, note) if line]
    outline.pop('direction', None)
    outline['approval'] = words
    write_atomic(root / OUTLINE, json.dumps(outline, indent=2, ensure_ascii=False) + '\n')
    gate = (run.setdefault('gates', {})).get(GATE) or {}
    run['gates'][GATE] = {**gate, 'state': 'approved', 'at': at, 'by': 'page', 'note': note}
    decks.write_run(root, run)
