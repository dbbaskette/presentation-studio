"""The deck pipeline as data: which steps a deck has, where it stands, and how to reopen a gate."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class Step:
    name: str
    stage: str
    kind: Literal['code', 'agent', 'gate']
    label: str
    doing: str


def _s(name, stage, kind, label, doing):
    return Step(name, stage, kind, label, doing)


PIPELINE: tuple[Step, ...] = (
    _s('intake-source', 'intake', 'code', 'Get your starting material',
       'Reading your document or fetching your deck'),
    _s('classify', 'classify', 'agent', 'Read your document',
       'Working out whether your document is a finished script or raw material'),
    _s('inventory', 'classify', 'code', 'Look through your deck',
       'Listing every slide in your deck'),
    _s('gate:classify', 'classify', 'gate', 'Confirm what you gave us',
       'Waiting for you to confirm what kind of material this is'),
    _s('research-plan', 'research', 'agent', 'Plan the research',
       'Deciding what to look up'),
    _s('gate:research-plan', 'research', 'gate', 'Approve the research plan',
       'Waiting for you to approve the research plan'),
    _s('research', 'research', 'agent', 'Do the research',
       'Reading sources and collecting findings'),
    _s('research-report', 'research', 'code', 'Write up the research',
       'Putting the findings into a report'),
    _s('gate:research', 'research', 'gate', 'Approve the research',
       'Waiting for you to approve the research findings'),
    _s('extract', 'outline', 'agent', 'Pull out your outline',
       'Taking the outline straight from your deck'),
    _s('outline', 'outline', 'agent', 'Draft the outline',
       'Drafting the outline of your deck'),
    _s('gate:outline', 'outline', 'gate', 'Approve the outline',
       'Waiting for you to approve the outline'),
    _s('brand', 'look', 'code', 'Load the brand',
       'Loading the brand rules for your deck'),
    _s('look', 'look', 'agent', 'Design the look',
       'Designing how your deck will look'),
    _s('look-preview', 'look', 'code', 'Preview the look',
       'Making sample slides to show the look'),
    _s('gate:look', 'look', 'gate', 'Approve the look',
       'Waiting for you to approve the look'),
    _s('patch', 'build', 'agent', 'Fix the chosen slides',
       'Changing only the slides you picked'),
    _s('build-start', 'build', 'code', 'Set up the build',
       'Getting the deck ready to build'),
    _s('build-sections', 'build', 'agent', 'Build the slides',
       'Building the slides section by section'),
    _s('build-whole', 'build', 'code', 'Join the sections',
       'Putting the sections together into one deck'),
    _s('build-review', 'build', 'agent', 'Check the deck',
       'Reviewing the whole deck for problems'),
    _s('build-repair', 'build', 'agent', 'Fix what the check found',
       'Repairing the slides that need it'),
    _s('build-render', 'build', 'code', 'Render the slides',
       'Rendering the slides so you can see them'),
    _s('gate:build', 'build', 'gate', 'Approve the deck',
       'Waiting for you to approve the deck'),
    _s('deliver', 'deliver', 'code', 'Deliver the deck',
       'Saving the finished deck'),
    _s('rehearse', 'rehearse', 'gate', 'Rehearse (coming later)',
       'Rehearsal is coming later'),
)
BY_NAME = {s.name: s for s in PIPELINE}

_EXISTING_EXTRACT = ('brand-only', 'polish', 'redesign', 'rework')
_RESEARCH = ('research-plan', 'gate:research-plan', 'research', 'research-report', 'gate:research')


def _route(run: dict) -> str:
    return run.get('route') or (run.get('form') or {}).get('route') or ''


def _level(run: dict) -> Optional[str]:
    return (run.get('form') or {}).get('level')


def _has(run: dict, name: str) -> bool:
    route, level = _route(run), _level(run)
    existing = route == 'existing'
    if name == 'gate:classify':
        return route in ('document', 'existing')
    if name in ('intake-source', 'brand', 'build-render', 'gate:build', 'deliver', 'rehearse'):
        return True
    if name in _RESEARCH:
        return bool((run.get('form') or {}).get('research')) and (
            route == 'scratch' or (route == 'document' and run.get('classified') == 'material'))
    if name == 'classify':
        return route == 'document'
    if name == 'inventory':
        return existing
    if name == 'extract':
        return existing and level in _EXISTING_EXTRACT
    if name in ('outline', 'gate:outline'):
        return route in ('scratch', 'document') or (existing and level == 'rework')
    if name in ('look', 'look-preview', 'gate:look'):
        return route in ('scratch', 'document') or (existing and level in ('redesign', 'rework'))
    if name == 'patch':
        return existing and level == 'selected'
    return route in ('scratch', 'document', 'existing') and not (existing and level == 'selected')


def steps(run: dict) -> list[Step]:
    """The steps this deck has, in order."""
    return [s for s in PIPELINE if _has(run, s.name)]


@dataclass
class Survey:
    next: Optional[Step]
    done: list[str]
    waiting: Optional[str]
    halted: Optional[str]


def _state(run: dict, step: Step) -> Optional[str]:
    return ((run.get('gates') or {}).get(step.name) or {}).get('state')


def _is_done(run: dict, step: Step) -> bool:
    if step.kind == 'gate':
        return _state(run, step) == 'approved'
    return bool(((run.get('steps') or {}).get(step.name) or {}).get('done'))


def feeder(run: dict, gate: str) -> str:
    """The name of the step that produces what `gate` asks the person to decide on."""
    route, level = _route(run), _level(run)
    if gate == 'gate:classify':
        return 'inventory' if route == 'existing' else 'classify'
    if gate == 'gate:outline':
        return 'outline'
    if gate == 'gate:build':
        if level == 'selected':
            return 'patch'
        named = ((run.get('gates') or {}).get('gate:build') or {}).get('slides')
        return 'build-repair' if named else 'build-sections'
    return gate.split(':', 1)[1]  # gate:research-plan, gate:research, gate:look


def survey(run: dict) -> Survey:
    listed = steps(run)
    names = {s.name for s in listed}
    done = [s.name for s in listed if _is_done(run, s)]
    nxt: Optional[Step] = None
    waiting: Optional[str] = None
    for s in listed:
        if s.name == 'rehearse' or _is_done(run, s):
            continue
        if s.kind == 'gate':
            state = _state(run, s)
            if state == 'changes':
                back = feeder(run, s.name)
                nxt = BY_NAME[back] if back in names else s
            else:
                nxt = s
                if state == 'waiting':
                    waiting = s.name
        else:
            nxt = s
        break
    halted = run.get('halted')
    why = halted.get('why') if isinstance(halted, dict) else (halted or None)
    return Survey(nxt, done, waiting, why)


def reopen(run: dict, gate: str) -> dict:
    """Send the deck back to the step that feeds `gate`. Returns a mutated deep copy: the
    feeder and every later step become not done, and every later gate loses its approval
    (state 'absent'). The reopened gate keeps its own state and note until the engine re-runs
    the feeder and sets it to 'waiting' again."""
    out = copy.deepcopy(run)
    listed = steps(out)
    names = [s.name for s in listed]
    back = feeder(out, gate)
    if back not in names:
        back = gate
    start = names.index(back)
    out.setdefault('steps', {})
    out.setdefault('gates', {})
    for s in listed[start:]:
        if s.kind == 'gate':
            if s.name != gate:
                out['gates'][s.name] = {**out['gates'].get(s.name, {}), 'state': 'absent'}
        else:
            out['steps'][s.name] = {**out['steps'].get(s.name, {}), 'done': False}
    return out


def timeline(run: dict) -> list[dict]:
    """One row per step for the page: done, current (the next one), upcoming; rehearse is later."""
    current = survey(run).next
    rows, seen_current = [], False
    for s in steps(run):
        if s.name == 'rehearse':
            state = 'later'
        elif _is_done(run, s) and not seen_current:
            state = 'done'
        elif current is not None and s.name == current.name:
            state, seen_current = 'current', True
        else:
            state = 'upcoming'
        rows.append({'name': s.name, 'stage': s.stage, 'label': s.label, 'state': state})
    return rows
