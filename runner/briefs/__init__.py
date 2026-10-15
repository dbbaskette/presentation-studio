"""What a worker is told for each kind of job.

What a caller needs to know
---------------------------
    briefs.guidance('classify')                  telling a spec from material
    briefs.guidance('research-plan')             drafting the research questions
    briefs.guidance('research-question')         researching one question
    briefs.guidance('outline-brief')             writing the outline from a brief alone
    briefs.guidance('outline-material')          writing it from material the person gave
    briefs.guidance('outline-spec')              writing it from a spec that lays out slides
    briefs.guidance('extract')                   reading a deck that exists into an outline
    briefs.guidance('extract', level='polish')   and what that level leaves free
    briefs.guidance('restructure')               reworking a deck's story
    briefs.guidance('section')                   drawing one section of a deck
    briefs.guidance('section', repair=True)      drawing it again after a review
    briefs.guidance('review')                    reviewing a deck someone else drew
    briefs.guidance('patch')                     planning selected changes to a deck
    briefs.guidance('change-request')            reading a person's note at a gate

- A brief says how to do a kind of job. What one job is about goes in the task: the name to
  hand a draft back under, the inputs' names, and on a second attempt what went wrong or
  what the person asked for.
- A brief names only the worker tools. It never names a helper command or a file, because
  a worker has neither. Each says what is handed back, and under what name.
- `level` is the freedom an existing deck is given: brand-only, polish, redesign or rework.
  It selects the notes that are added to `extract`.
- `repair=True` with `section` returns the brief for drawing a section again.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
KINDS = ('classify', 'research-plan', 'research-question', 'outline-brief', 'outline-material',
         'outline-spec', 'extract', 'restructure', 'section', 'section-repair',
         'review', 'patch', 'change-request')
LEVELS = ('brand-only', 'polish', 'redesign', 'rework')


def read(name: str) -> str:
    return (HERE / f'{name}.md').read_text(encoding='utf-8')


def guidance(kind: str, level: str | None = None, repair: bool = False) -> str:
    """The guidance for one kind of job, whole."""
    if kind not in KINDS:
        raise ValueError('There is a brief for: ' + ', '.join(KINDS) + '.')
    if repair and kind != 'section':
        raise ValueError('Only a section is drawn again.')
    if level is not None and (kind != 'extract' or level not in LEVELS):
        raise ValueError('Only extract takes a level, one of: ' + ', '.join(LEVELS) + '.')
    if repair:
        kind = 'section-repair'
    text = read(kind)
    if level is not None:
        text += '\n' + read(f'extract-{level}')
    return text
