"""Building a deck: the runner's own rules for what a section's composer hands in and for
what a reviewer finds.

What a caller needs to know
---------------------------
    spec = build.fixed(whole, ids, number)      # what a section's composer may not change
    build.kept(section, spec)                   # what the runner refuses in a section
    build.checked(finding, slides)              # one finding of a review, or why it is wrong
    build.slides_of(outline)                    # an outline's slides
    build.plain(text)                           # text as it is compared

- Nothing here starts anything, reads a deck's folder or knows about runs. Each function
  takes text or parsed JSON and gives back parsed JSON or a list of sentences.
- A section keeps every approved word: `kept` holds its title, sources, caveat, source line
  and notes to the outline's, and looks for each point's words among the text the slide
  draws. What is drawn, and how, is the composer's.
- A finding is about `drawing` or about `content`. QUESTIONS are the eight the slides tool
  asks of every slide, numbered as it numbers them, in the runner's words. The tool's own
  are not handed to a caller, so a change to them there has to be made here too.
"""
from __future__ import annotations

import json
import re

PREVIEWS = 4            # times one composer may render its section
DIRECTION = {'focal': 'headingPrimary', 'neutral': 'canvasSecondary'}
SEVERITIES = ('critical', 'major', 'minor')
ABOUT = ('drawing', 'content')
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


def fixed(whole: dict, ids: list[str], number: int) -> dict:
    """What the composer of one section may not change: the deck's title and direction,
    and for each of its slides the title, the sources, the points, the caveat, the source
    line and the notes that were approved."""
    by_id = {slide.get('id'): slide for slide in slides_of(whole)}
    return {'title': whole.get('title'), 'direction': whole.get('direction') or DIRECTION,
            'prefix': f's{number}_',
            'slides': [{'id': ident, 'title': by_id[ident].get('title'),
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
        if 'layout' in mine:
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
        for name, got in (('caveat', _caveat(mine)), ('source', mine.get('source')),
                          ('notes', mine.get('notes'))):
            if not _same(got, theirs[name]):
                problems.append(f'{ident}: `{name}` stays exactly as it was approved'
                                + (f': {json.dumps(theirs[name])}' if theirs[name]
                                   and name != 'notes' else '.' if theirs[name]
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
