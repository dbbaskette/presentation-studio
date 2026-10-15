"""What this computer remembers for the runner: the agent to use by default, the limits, and
how a deck's previews are rendered.

What a caller needs to know
---------------------------
    chosen = settings.load()                      # the defaults when nothing is saved
    settings.save(replace(chosen, agent='codex', deck_dollars=10))

- Kept in the per-user data folder as `runner.json`, beside the workspace `gitstate`
  remembers there. Nothing here is written into the repository: two people who share a
  workspace can use different agents and different limits.
- `model` is the model the agent is asked for and `effort` how hard it reasons, its
  reasoning level; None for each is the agent's own choice. A level is one of the words an
  agent takes (EFFORTS): which of them a model takes is what the agent lists. Claude Code
  lists nothing, so its models and their levels are kept in `claude-code-models.json`
  beside this file, and a level its model does not take is refused (`takes`).
- `step_seconds` is how long one worker may run. `deck_dollars` is what one deck
  may spend, where the agent reports spending, before it stops and asks. `parallel` is how
  many decks work at once.
- `previews` is how a deck's slides are rendered to look at: `local`, with LibreOffice on
  this computer, or `drive`, through Google Drive. None until the person chooses.
- `brand_skill` is where the brand skill to use is, when the person named one of those
  found. None for the first that is found.
- `notify` is whether the runner tells the person, through the computer's own
  notifications, that a deck needs a decision while no page is open. Off until they
  turn it on.
- `look_for_updates` is whether the runner asks, at most once a day, which releases of
  Presentation Studio and its companion skills exist. On until they turn it off. See `upkeep`.
- `name` is the person's own name, as set-up shows it and offers to share with every studio;
  None until they give it. git's own identity still signs each commit and each claim.
- `brand` and `variant` are the brand a new deck is offered first, and `output` what it is
  made as: `google` (Google Slides) or `pptx`. A deck's own form says what it is made with.
- A value that makes no sense is refused with a sentence, not corrected silently.
"""
from __future__ import annotations

import functools
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import home
from workspace import WorkspaceError

SCHEMA = 1
AGENTS = ('claude', 'codex')
SECONDS = (60, 7200)        # the shortest and longest time one worker may be given
DOLLARS = 1000              # the most one deck may be allowed to spend
PARALLEL = (1, 8)           # the fewest and most decks that work at once
MODEL = 100                 # characters in a model's name
# The reasoning levels each agent takes: Claude Code's `--effort`, and the words Codex's
# catalog and its service use.
LEVELS = ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra')
EFFORTS = {'claude': ('low', 'medium', 'high', 'xhigh', 'max'), 'codex': LEVELS}
# Claude Code has no list of its models, so the runner keeps one, with its source and date.
CLAUDE_MODELS = Path(__file__).resolve().with_name('claude-code-models.json')
PREVIEWS = ('drive', 'local')   # how a deck's previews are rendered
OUTPUTS = ('google', 'pptx')    # what a new deck is made as
WORD = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')   # a brand's or a variant's name
NAME = 100                  # characters in a person's name


@dataclass(frozen=True)
class Settings:
    """This computer's choices for the runner."""
    agent: str = 'claude'
    model: str | None = None
    effort: str | None = None
    step_seconds: int = 900
    deck_dollars: float = 20.0
    parallel: int = 2
    previews: str | None = None
    brand_skill: str | None = None
    notify: bool = False
    look_for_updates: bool = True
    name: str | None = None
    brand: str = 'tanzu'
    variant: str = 'light'
    output: str = 'google'

    @property
    def limits(self) -> dict:
        return {'step_seconds': self.step_seconds, 'deck_dollars': self.deck_dollars,
                'parallel': self.parallel}


def path():
    return home.data_root() / 'runner.json'


def check_agent(agent) -> str:
    if agent not in AGENTS:
        raise WorkspaceError('The agent is one of: ' + ', '.join(AGENTS) + '.')
    return agent


def check_model(model) -> str | None:
    """A model's name as an agent takes it, or None for the agent's own default."""
    if model is None or model == '':
        return None
    if not isinstance(model, str) or len(model) > MODEL or not model.strip() \
            or model.startswith('-') or any(mark.isspace() for mark in model):
        raise WorkspaceError('The model is the short name the agent knows it by, with no '
                             'spaces, or nothing for the agent\'s own choice.')
    return model


def check_effort(effort, agent: str | None = None, model: str | None = None) -> str | None:
    """A reasoning level the agent and its model take, or None for the agent's own. With
    no agent, any level one of them takes."""
    if effort is None or effort == '':
        return None
    known = takes(agent, model)
    if not isinstance(effort, str) or effort not in known:
        named = claude_models()['named'].get(model) if agent == 'claude' else None
        if named and not known:
            raise WorkspaceError(f'{named} takes no reasoning level: leave it to the agent.')
        raise WorkspaceError((f'{named} takes one of these reasoning levels: ' if named
                              else 'The reasoning level is one of: ') + ', '.join(known)
                             + ', or nothing for the agent\'s own choice.')
    return effort


def takes(agent: str | None, model: str | None = None) -> tuple:
    """The reasoning levels a model takes: those the list of Claude Code's models gives
    it, or for a model that is not listed, every level its agent takes."""
    if agent == 'claude' and model:
        for listed in claude_models()['models']:
            if listed['name'] == model:
                return tuple(listed['levels'])
    return EFFORTS.get(agent, LEVELS)


@functools.lru_cache(maxsize=None)
def claude_models() -> dict:
    """Claude Code's models, read once from the file beside this one. See read_models."""
    return read_models(CLAUDE_MODELS)


def read_models(path: Path) -> dict:
    """A list of Claude Code's models: {'source', 'date', 'models', 'named'}. Each model is
    {'name', 'label', 'family', 'about', 'levels', 'default_level'}, in the file's order,
    and `named` gives each model's short name ("Opus 4.6") by its ID. An alias takes its
    label and its levels from the model it names. A list that is not whole is refused."""
    try:
        kept = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise WorkspaceError(f'The list of Claude Code\'s models in {path} cannot be read.')
    entries = kept.get('models') if isinstance(kept, dict) else None
    if not isinstance(entries, list):
        raise WorkspaceError(f'{path} has no list of models.')
    found: dict[str, dict] = {}
    for entry in entries:
        entry = entry if isinstance(entry, dict) else {}
        name = entry.get('id')
        try:
            check_model(name)
        except WorkspaceError:
            name = None
        if not name:
            raise WorkspaceError(f'{entry.get("id")} is not a model\'s name, in {path}.')
        if name in found:
            raise WorkspaceError(f'{name} is listed twice, in {path}.')
        for part in ('family',) if 'alias' in entry else ('family', 'label'):
            if not isinstance(entry.get(part), str) or not entry[part].strip():
                raise WorkspaceError(f'{name} has no {part}, in {path}.')
        levels = entry.get('levels', [])
        if 'alias' not in entry and (not isinstance(levels, list) or any(
                level not in EFFORTS['claude'] for level in levels)):
            raise WorkspaceError(f'{name} takes a level Claude Code does not, in {path}.')
        found[name] = entry
    models, named = [], {}
    for name, entry in found.items():
        meant = found.get(entry.get('alias')) if 'alias' in entry else entry
        if meant is None or 'alias' in meant:
            raise WorkspaceError(f'{name} names {entry.get("alias")}, which is not a version '
                                 f'listed in {path}.')
        named[name] = meant['label']
        label = (f'{entry["family"]}, always the newest (now {meant["label"]})'
                 if meant is not entry else f'{entry["label"]} ({name})')
        models.append({'name': name, 'label': label, 'family': entry['family'],
                       'about': None, 'levels': list(meant['levels']), 'default_level': None})
    return {'source': kept.get('source'), 'date': kept.get('date'), 'models': models,
            'named': named}


def check_previews(how) -> str | None:
    if how is not None and how not in PREVIEWS:
        raise WorkspaceError('Previews are rendered one of these ways: '
                             + ', '.join(PREVIEWS) + '.')
    return how


def check_place(place) -> str | None:
    if place is not None and (not isinstance(place, str) or not place.strip()
                              or len(place) > 2000 or '\0' in place):
        raise WorkspaceError('Give the brand skill as one of those found on this computer.')
    return place


def check_notify(wanted) -> bool:
    if not isinstance(wanted, bool):
        raise WorkspaceError('Notifications are on or off: give notify as true or false.')
    return wanted


def check_look(wanted) -> bool:
    if not isinstance(wanted, bool):
        raise WorkspaceError('Looking for updates is on or off: give look_for_updates as true '
                             'or false.')
    return wanted


def check_name(name) -> str | None:
    """A person's name as they gave it, or None for none."""
    if name is None or name == '':
        return None
    if not isinstance(name, str) or not name.strip() or len(name) > NAME \
            or any(ord(mark) < 32 for mark in name):
        raise WorkspaceError(f'Give your name as text of at most {NAME} characters.')
    return name.strip()


def check_word(value, label: str) -> str:
    """A brand's or a variant's short name, as the brand skill lists it."""
    if not isinstance(value, str) or not WORD.match(value):
        raise WorkspaceError(f'The {label} is a short name such as tanzu or light.')
    return value


def check_output(output) -> str:
    if output not in OUTPUTS:
        raise WorkspaceError('A deck is made as one of: ' + ', '.join(OUTPUTS) + '.')
    return output


def number(value, label: str, least: float, most: float, whole: bool):
    """A limit a person typed, which must be a number in a sensible range."""
    plain = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not plain or (whole and int(value) != value) or not least <= value <= most:
        kind = 'a whole number' if whole else 'a number'
        raise WorkspaceError(f'{label} is {kind} from {least:g} to {most:g}.')
    return int(value) if whole else float(value)


def check(chosen: Settings) -> Settings:
    """The same settings, once every one of them makes sense."""
    agent = check_agent(chosen.agent)
    return Settings(
        agent=agent, model=check_model(chosen.model),
        effort=check_effort(chosen.effort, agent, chosen.model),
        step_seconds=number(chosen.step_seconds, 'The time for one step, in seconds,',
                            *SECONDS, True),
        deck_dollars=number(chosen.deck_dollars,
                            'What a deck may spend, in dollars,', 0.01, DOLLARS, False),
        parallel=number(chosen.parallel, 'How many decks run at once', *PARALLEL, True),
        previews=check_previews(chosen.previews), brand_skill=check_place(chosen.brand_skill),
        notify=check_notify(chosen.notify),
        look_for_updates=check_look(chosen.look_for_updates),
        name=check_name(chosen.name), brand=check_word(chosen.brand, 'brand'),
        variant=check_word(chosen.variant, 'variant'), output=check_output(chosen.output))


def load() -> Settings:
    """What is saved on this computer. Anything missing or unusable is the default."""
    kept = home.read_json(path(), None)
    if not isinstance(kept, dict) or kept.get('schema') != SCHEMA:
        return Settings()
    known = {name: kept[name] for name in asdict(Settings()) if name in kept}
    try:
        return check(Settings(**known))
    except WorkspaceError:
        return Settings()


def save(chosen: Settings) -> Settings:
    """Remember these settings on this computer."""
    chosen = check(chosen)
    home.write_json(path(), {'schema': SCHEMA, **asdict(chosen)})
    return chosen
