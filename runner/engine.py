"""The engine: walks each deck's steps, hands jobs to workers and stops at its gates.

What a caller needs to know
---------------------------
    engine = Engine()                        # the real agents, slides tool and brand skill
    engine.resume()                          # pick up every deck in the workspace
    engine.resume(wait=False)                # the same, fetching in the background
    made = engine.start(form, uploads)       # {'path', 'id'}; the run starts at once
    engine.view(path)                        # what the page shows for one deck
    engine.decks()                           # every deck: needs, working, finished, elsewhere
    engine.decide(path, 'gate:outline', 'approve', note, extra)   # the only way a gate moves
    engine.act(path, 'pause')                # or 'resume', 'stop', 'retry', 'undo'
    engine.answer(path, question_id, text)   # a person answers a worker's question
    engine.picture(path, 'build', 3)         # one slide's picture, as PNG bytes
    engine.download(path)                    # (name, bytes) of the rendered .pptx
    engine.deck_needs()                      # what this computer has for making a deck
    engine.share(); engine.fetch()           # with the team's repository
    engine.drive(path, 'take')               # take a deck, or take it over; 'hand-over'
    engine.hold(path)                        # refuse, saying who has it, if it is not ours
    engine.publish(path); engine.published() # numbered revisions, as tags
    engine.leaving(path); engine.delete(path, title)
    engine.bring(folder)                     # copy a deck made elsewhere in, and run it
    engine.standing()                        # the status screen
    engine.serving(); engine.seen(); engine.tell()   # fetch and notify while serving
    engine.close()                           # end every worker; nothing half-made is kept

- The next step is never remembered. Each time, the deck's run record (run.json, which
  decks.py describes) is read and the first step of `stages.steps(run)` that is not done
  is the next: a step is done when its entry says so, a gate when it is approved. RUN maps
  every step of `stages.PIPELINE` to what the engine does for it, which is a call into one
  of the step modules (`runner.steps.*`). Starting the runner again resumes every deck
  where its record says it is.
- The run record holds, besides what decks.py lists: each try at each step with its times,
  cost, outcome and error (`steps[name]['tries']`, and `failed`, the failures in a row);
  a worker's `question` and the person's `answers`; `halted`, why the deck stopped, as
  {'state': 'paused'|'stopped'|'failed', 'step', 'why', 'kept', 'action': 'resume'|'retry'|
  None, 'at'}; `cleared`, what had been spent when the person last said to carry on; which
  research run holds the approved plan (`research`); and what each worker said of its work
  (`said`). It is committed with everything else.
- One try at an agent step, its limits and questions, and what the record holds of tries,
  are runner/jobs.py's (`jobs.Jobs`, a part of the engine); the research steps are
  runner/research_steps.py's. `retry` starts a step that stopped afresh.
- A gate is opened by the step that feeds it, or by the engine when the deck reaches it,
  and the run waits. `decide` is the only way a gate moves: it records the decision on the
  gate ({'state', 'note', 'at', 'by', 'round'}), applies what the gate takes beside it
  (gate:classify {'kind'}, gate:outline {'edited'}, gate:build {'slides'}), commits, shares
  when the workspace shares after each decision, and wakes the run. Asking for changes sets
  the gate to 'changes' first and then reopens it (`stages.reopen`), so the step that feeds
  it runs again with the person's note. Asking for changes at gate:look is choosing another
  brand or variant ({'brand', 'variant'}, with no note needed): the deck's contract is
  exported again for it and its cover drawn again. Asking for changes at gate:build once
  the deck is delivered builds it again (deliver.again).
- At a stop reviewed item by item (`marks.REVIEWED`) the marks are checked, once the stop
  is waiting, before anything is written. Questions dropped at the plan and findings left
  out at the research go with either decision, with no worker. A drop, rewording, new
  question, research-again or slide mark is enough for changes without a note; a leave-out
  is not. The marks, then the person's own words, are the note the stop's worker reads.
- The brand is exported once, with the first step that needs it, and checked before every
  step that uses it: the outline, the sample of the brand, the patch, each step of the
  build and its render. A brand that changed since stops the deck with build's sentence.
- No brand is named here: a deck started with no brand chosen is given, when its brand is
  first exported, the one Settings names where the brand skill has it, else the first the
  brand skill lists. A deck can be started with no brand skill installed; everything that
  does not need the brand is done, and the first step that does stops with NO_BRAND.
- What a deck is made from (sources/) and what its steps make on the way (work/) are never
  shared, so a deck taken over or brought in may lack them. Before its next step, the steps
  whose work is missing here are done again (the build from its start; the brand's sample),
  and a gate they fed that was approved is shown again. A document or deck that was
  uploaded or pasted cannot be fetched again: the deck stops and says so.
- What a deck's slides look like is drawn one picture at a time on this computer, and
  through the deck's one preview file in Google Drive (`build.how`). Pictures are kept
  under the deck's never-shared work/ folder; `picture` serves only those the step modules
  recorded there, and the contact sheet.
- Uploads: `start(form, uploads)` takes the form as the page sent it, with `uploads[name]`
  holding an upload's bytes. Bytes and pasted text are kept out of run.json: they wait
  under the deck's never-shared sources/incoming/ until the intake-source step takes them.
- Everything the engine writes in the workspace is written and committed while it holds
  `engine.files`, so the folder matches its last commit whenever nothing is being written.
- Limits: a worker's time, and what a deck may spend where its agent reports spending. A
  deck that has spent what it may stops and asks; "resume" lets it spend as much again.
- What a person may ask of a run depends on its state: pause while it is working; stop
  while it is working, waiting or paused; resume while it is paused or stopped; try again
  when a problem offers it; undo the last step while nothing is in hand and the last commit
  is this deck's and not shared yet. Anything else is refused in a sentence.
- `background=False` does every step in the caller's thread, which is how the tests drive
  it. `adapters` maps an agent's name to its adapter. `research`, `slides`, `brand` and
  `drive` make the wrappers of harness-research, the slides tool, a brand skill and Google
  Drive; each is replaceable so that no test reaches a real one.
- In a workspace with a shared repository a deck is run from one computer at a time, as
  Training Studio's runner does it: starting a deck takes it, and the claim is pushed
  before any work; `drive` takes, takes over or hands over; a fetch that says a deck this
  computer drove is someone else's stops it, sets what was not shared aside under a ref,
  and says so in `notice`. A delivered deck has no driver: take it to ask for changes.
  Decks take turns, as many at once as the settings allow.
- Two decks of one title started on two computers that could not reach the shared
  repository get one folder name. When this computer next shares, the one shared first
  keeps the folder, and this computer's is moved whole to a folder of its own, numbered as
  `decks.deck_id` numbers it, and carries on there with a `notice` that says so. A start
  whose claim finds the folder taken is refused, naming who has it.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import runner  # noqa: F401  puts the core on the import path
import computer
import home
import hub
from workspace import WorkspaceError, write_atomic

from runner import agents, companion, decks, documents, gitstate, marks, settings, stages
from runner import team, worker_tools
from runner import brand as brand_skill
from runner import research as research_cli
from runner import slides as slides_tool
from runner.jobs import (FED, KEPT_SO_FAR, Gone as _Gone, Halted as _Halted, Jobs,
                         Run as _Run, Slots as _Slots, attempts, first, gate_state,
                         last_error, spent, text_of, tries)
from runner.research_steps import PLAN, PLAN_MD, REPORT, Researching
from runner.steps import build, deliver as delivering, existing, intake
from runner.steps import look as looks
from runner.steps import outline as outlines

AT_ONCE = 3             # research questions, or sections, worked on at the same time
READY_FOR = 60          # seconds a look at an agent is reused
MODELS_FOR = 3600       # seconds a list of an agent's models is reused
MODELS_MISSED = 60      # seconds before a list that could not be made is asked for again
LOOKED_FOR = 300        # seconds a look at what this computer has for a deck is reused
NOTE = 4000             # characters in a person's note at a gate
ACTIONS = ('pause', 'resume', 'stop', 'retry', 'undo')
DECISIONS = ('approve', 'changes')
DRIVING = ('take', 'hand-over')
FETCH_EVERY = 180       # seconds between fetches while the runner serves
TICK = 15               # seconds between looks at whether to notify
PAGE_OPEN = 45          # seconds since a page last asked, while one counts as open
STOP_WAIT = 30          # seconds a run that is being deleted may take to end
IN_HAND = 'work/step.lock'      # written when a step starts, removed when it ends
INCOMING = 'sources/incoming'   # what the form brought, until intake-source takes it
PICTURE_KINDS = ('build', 'look', 'original')
SHEET = 'contact-sheet'

# What the engine does for each step of the pipeline: the name of its method. Every gate is
# opened the same way; rehearse is never next.
RUN = {
    'intake-source': '_intake_source', 'classify': '_classify', 'inventory': '_inventory',
    'gate:classify': '_gate', 'research-plan': '_research_plan',
    'gate:research-plan': '_gate', 'research': '_research',
    'research-report': '_research_report', 'gate:research': '_gate', 'extract': '_extract',
    'outline': '_outline', 'gate:outline': '_gate', 'brand': '_brand_step',
    'look-preview': '_look_preview', 'gate:look': '_gate', 'patch': '_patch',
    'build-start': '_build_start', 'build-sections': '_build_sections',
    'build-whole': '_build_whole', 'build-review': '_build_review',
    'build-repair': '_build_repair', 'build-render': '_build_render', 'gate:build': '_gate',
    'deliver': '_deliver', 'rehearse': None}
# What each gate decides on, as a commit and a sentence say it.
WORDS = {'gate:classify': 'classification', 'gate:research-plan': 'research plan',
         'gate:research': 'research', 'gate:outline': 'outline', 'gate:look': 'brand',
         'gate:build': 'deck'}
# The build's steps, whose work is kept under work/build/ on the computer that did it.
BUILT = ('build-start', 'build-sections', 'build-whole', 'build-review', 'build-repair',
         'build-render')
# Steps that render, and so need what deck_needs says is missing.
RENDERS = ('inventory', 'look-preview', 'build-whole', 'build-repair', 'build-render')
STATES = {'working': 'working', 'waiting': 'waiting for you', 'paused': 'paused',
          'stopped': 'stopped', 'failed': 'stopped on a problem', 'finished': 'finished'}

BACKGROUND = {'fetch': 'The last look for what your team shared did not work: {said}. It '
                       'is tried again every few minutes.',
              'tell': "The last try at telling you through this computer's notifications "
                      'did not work: {said}. It is tried again in a few seconds.'}
NO_DRIVERS = ('This workspace is a folder on this computer, so its decks are not taken or '
              'handed over.')
TAKEN = '{name} took this deck over on {when}. This computer stopped working on it.'
SET_ASIDE = (' What this computer had made and not yet shared is kept on this computer, and '
             'can be brought back.')
THEIRS = '{name} is running this deck from another computer.'
LAST = ' What is here is what was last shared{when}. {then} It may have moved on since.'
BROKEN = ('"{title}" was changed on this computer and on another at the same time, so '
          'nothing here can be shared. One side must take it over. Taking it over here '
          'carries on from the shared version; what this computer made and never shared is '
          'set aside and kept.')
UNREACHED = ('The shared repository could not be reached, so this deck cannot be taken now. '
             'Nothing was changed. Try again when it can be reached.')
CHECKING = ('The runner has just started and is still looking at what your team shared while '
            'it was closed. Nothing was changed. Try again in a moment.')
STALLED = ('Something went wrong while the runner picked its decks up ({failure}), so this '
           'one may not carry on by itself. Close the runner and start it again.')
SAME_TIME = ('{name} started a deck in {folder}/{ident} at the same moment, and theirs was '
             'shared first. Yours was not started. Give it a different title, or look at '
             'theirs.')
NAME_TAKEN = ('{name} already has a deck in {folder}/{ident}, which this computer had not '
              'seen yet, so this one was not brought in. Bring it in again: now it gets a '
              'folder of its own.')
MOVED = ('{name} started a deck in {folder}/{was} while this computer could not reach the '
         'shared repository, and theirs was shared first. Yours is kept whole, and was moved '
         'to {folder}/{ident}.')
GIVEN_ELSEWHERE = ('What this deck was made from was {how} on the computer that started it, '
                  'and is never shared, so this computer does not have it. Carry on with '
                  'this deck on that computer, or start it again here.')
CHANGED_IN_GOOGLE = ('The deck in Google Slides changed since this deck was read from it, so '
                     'what was decided about it no longer fits. Start a new deck from it as it '
                     'is now.')
AGAIN_HERE = ('carry on here: {steps} again, as what was made for them is kept on the '
              'computer that made it')
NOT_WAITING = 'The {it} is not waiting for a decision now.'
NO_NOTE = 'Say what should change.'
NO_BRAND_CHOSEN = 'Choose the brand, and its variant, to make the deck in.'
ON_ITS_WAY = 'This deck is on its way to Google Slides already. Wait for it.'
STILL_NOT_CONNECTED = ("Google still isn't connected on this computer. Sign in with gcloud, "
                       'then deliver it again.')
UNDO_NOT = ('The last step cannot be undone: only the last thing done, when it was this '
            "deck's and is not shared yet, can be.")
NO_PICTURE = 'There is no picture of that slide on this computer.'
NOT_YOURS = ('{name} runs this deck from another computer, so it cannot be deleted from here. '
             'Take it over first if you mean to delete it.')
NOT_TAKEN = ('Nobody is running this deck, so it cannot be deleted from here until someone '
             'takes it. Take it first if you mean to delete it.')
MISTITLED = ('That is not the title of this deck. Nothing was deleted: open the deck again '
             'before you delete it.')
NOT_ENDED = ('It was stopped, but something it started has not ended yet, so it was not '
             'deleted. Try deleting it again in a moment.')
KEPT_BACK = ('{name} took this deck on {when}, before your deletion of it was shared, so it '
             'was not deleted. It is as they shared it.')
WAITS = ('It is gone from this computer. Your team sees it gone the next time the workspace '
         'is shared.')
NOT_CHOSEN = ("How a deck's previews are rendered has not been chosen. Choose Google Drive "
              'or LibreOffice in Settings.')
NO_RENDERER = ('This computer has no way to render previews of slides. Install LibreOffice, '
               'or give it Google access that reaches Drive.')
NO_DRIVE = ('Previews are set to go through Google Drive, and Google access from this '
            'computer does not reach Drive. Sign in to Google with Drive access, or choose '
            'LibreOffice in Settings.')
NO_LOCAL = ('Previews are set to be rendered with LibreOffice, which this computer does not '
            'have. Install it, or choose Google Drive in Settings.')
NO_PICTURES = ('The programs the slides tool uses to turn a render into pictures are not on '
               'this computer.')
CANNOT_DRAW = 'The slides cannot be drawn on this computer yet. {said}'
NO_BRAND = ("Your deck needs your brand from here on, and no brand skill is installed on this "
            "computer: name the brand skill's repository in Settings and install it, then "
            'retry.')
DRIVE_FILES = {'preview': 'Preview presentation', 'slides': 'Google Slides deck'}


# --- what a run record holds ----------------------------------------------------------------

def _refs(repo: Path, branch: str) -> tuple | None:
    """Where a clone's branch and what it knows of the remote's stand, told without starting
    git. None where the refs are not kept in files."""
    folder = repo / '.git'
    if not folder.is_dir() or (folder / 'reftable').exists():
        return None
    stamps: list = [str(repo), branch]
    for name in ('HEAD', f'refs/heads/{branch}', f'refs/remotes/origin/{branch}',
                 'packed-refs'):
        try:
            found = (folder / name).stat()
        except OSError:
            stamps.append(None)
            continue
        stamps.append((found.st_mtime_ns, found.st_size, found.st_ino))
    return tuple(stamps)


class Elsewhere(WorkspaceError):
    """This computer may not change a deck: someone else drives it, or nobody does."""


class Engine(Jobs, Researching):
    """Drives every deck in this computer's workspace."""

    def __init__(self, adapters=None, research=None, slides=None, brand=None, drive=None,
                 background: bool = True, at_once: int = AT_ONCE, notifier=None):
        self.adapters = dict(adapters or agents.AGENTS)
        self.notifier = notifier or team.Notifier()
        self.research = research or research_cli.Research
        self.slides = slides or slides_tool.Slides
        self.brand = brand or brand_skill.Brand
        self.google = drive
        self.background, self.at_once = background, at_once
        self.upkeep = None    # what `studio serve` keeps of the skills here
        self.files = threading.RLock()
        self._lock = threading.RLock()
        self._runs: dict[str, _Run] = {}
        self._slots = _Slots(lambda: settings.load().parallel)
        self._closing = False
        self._ending = threading.Event()
        self._asked: float | None = None
        self._clash: dict[str, str] = {}
        self._serving: threading.Thread | None = None
        self._sharing: threading.Thread | None = None
        self._share_again = False
        self._fetched = 0
        self._as_of: dict[tuple, tuple[int, object]] = {}
        self._tags_unsent = True
        self._looked: tuple[float, dict] | None = None
        self._looking = threading.Lock()
        self._ahead: tuple[tuple, int] | None = None
        self._background: dict[str, dict] = {}
        self._unshared: str | None = None
        self._checking = False
        self._stalled: str | None = None
        self._dropped: set[str] = set()
        self._moved: dict[str, str] = {}    # a deck moved to a folder of its own, and why
        self._woken: list[Path] = []        # moved decks, to carry on after the replay
        self._claiming: str | None = None   # a deck whose claim is on its way: never moved
        self._ready: dict[str, tuple[float, agents.Readiness]] = {}
        self._models: dict[str, tuple[float, dict]] = {}
        self._listing: dict[str, threading.Lock] = {}
        self._sending: set[str] = set()      # decks on their way to Google Slides now

    # --- what is driven ----------------------------------------------------------------------

    @property
    def workspace(self) -> gitstate.Workspace | None:
        return gitstate.current()

    def space(self) -> gitstate.Workspace:
        found = self.workspace
        if found is None:
            raise WorkspaceError('No workspace is set up on this computer yet. Set one up '
                                 'first.')
        return found

    def driven(self, path) -> Path | None:
        """A deck's folder when it is a deck of this workspace, else None."""
        space, root = self.workspace, Path(path)
        if space is None or root.parent != space.root or root.name in ('', '.', '..') \
                or root.is_symlink() or root.resolve().parent != space.root.resolve() \
                or not (root / decks.RUN).is_file():
            return None
        return root

    def every(self) -> list[Path]:
        """Every deck in the workspace. A folder that is a link to somewhere else is not
        one."""
        space = self.workspace
        if space is None or not space.root.is_dir():
            return []
        return [path.parent for path in sorted(space.root.glob(f'*/{decks.RUN}'))
                if self.driven(path.parent) is not None]

    def adapter(self, name: str):
        found = self.adapters.get(name)
        if found is None:
            raise WorkspaceError(f'This runner has no agent called {name}.')
        return found() if isinstance(found, type) else found

    def ready(self, name: str, fresh: bool = False) -> agents.Readiness:
        """Whether an agent can be used now. A look is reused for a minute."""
        seen = self._ready.get(name)
        if fresh or seen is None or time.monotonic() - seen[0] >= READY_FOR:
            seen = self._ready[name] = (time.monotonic(), self.adapter(name).ready())
        return seen[1]

    def models(self, name: str) -> dict:
        """What an agent offers to choose from, as `agents` describes, with `problem`."""
        adapter = self.adapter(name)
        with self._lock:
            listing = self._listing.setdefault(name, threading.Lock())
        with listing:
            seen = self._models.get(name)
            if seen is not None and time.monotonic() - seen[0] < (
                    MODELS_FOR if seen[1]['problem'] is None else MODELS_MISSED):
                return seen[1]
            try:
                if not hasattr(adapter, 'models'):
                    raise WorkspaceError(f'{adapter.title} cannot list its models.')
                found = {'agent': name, **adapter.models(), 'problem': None}
            except WorkspaceError as failure:
                found = {'agent': name, 'models': [], 'levels': [], 'source': None,
                         'problem': str(failure)}
            self._models[name] = (time.monotonic(), found)
            return found

    def _run(self, root: Path) -> _Run:
        with self._lock:
            return self._runs.setdefault(str(root), _Run())

    def _load(self, root: Path) -> dict:
        try:
            record = decks.read_run(root)
        except (OSError, ValueError):
            raise WorkspaceError(f'The run record in {Path(root).name} cannot be read, so the '
                                 'runner will not drive this deck.') from None
        if not isinstance(record, dict) or record.get('schema') != decks.SCHEMA \
                or not isinstance(record.get('steps'), dict):
            raise WorkspaceError(f'The run record in {Path(root).name} cannot be read, so the '
                                 'runner will not drive this deck.')
        for key, value in (('gates', {}), ('answers', {}), ('said', {}), ('question', None),
                           ('halted', None), ('cleared', 0.0), ('research', None),
                           ('revisions', []), ('limits', {})):
            record.setdefault(key, value)
        return record

    def _store(self, root: Path, record: dict) -> None:
        decks.write_run(root, record)

    def _commit(self, root: Path, what: str, also=()) -> None:
        """Commit one deck's folder, and the paths `also` names, saying what happened. Call
        it holding `files`. Nothing is committed for a deck that stopped being this
        computer's while a step was in hand: what the step wrote is put back, and the step
        ends."""
        if self._run(root).gone:
            gitstate.discard(self.space(), root)
            raise _Gone('This deck is no longer run from this computer.')
        title = self._load(root).get('title') or root.name
        gitstate.commit(self.space(), f'{title}: {what}', [root, *also])

    # --- one driver for each deck ------------------------------------------------------------

    def mine(self, path) -> bool:
        """True when this computer may change a deck."""
        root = self.driven(path)
        return root is not None and team.ours(self.workspace, self._load(root))

    def hold(self, path) -> None:
        """Refuse, saying who has it, a change to a deck this computer does not drive, and
        any change while the runner that just started is still looking at what was
        shared."""
        root = self.driven(path)
        if root is None:
            return
        if self._checking:
            raise WorkspaceError(CHECKING)
        why = team.elsewhere(self.workspace, self._load(root))
        if why:
            raise Elsewhere(why)

    def _held(self, path) -> Path:
        root = self.driven(path)
        if root is None:
            raise WorkspaceError('There is no deck there.')
        self.hold(root)
        return root

    def drive(self, path, action: str) -> dict:
        """Take a deck nobody drives, take one over, or hand one over. Returns its view."""
        root = self.driven(path)
        if root is None:
            raise WorkspaceError('There is no deck there.')
        if action not in DRIVING:
            raise WorkspaceError('A deck can be asked to: ' + ', '.join(DRIVING) + '.')
        space = self.space()
        if space.address is None:
            raise WorkspaceError(NO_DRIVERS)
        if action == 'hand-over':
            self._hand(root, space)
            return self.view(root)
        kept = self._take(root, space)
        self.wake(root)
        shown = self.view(root)
        if kept and not shown.get('notice'):
            shown['notice'] = 'This deck carries on from the shared version.' + SET_ASIDE
        return shown

    def _take(self, root: Path, space: gitstate.Workspace) -> str | None:
        """Make a deck this computer's. Returns the ref that keeps what was set aside of
        this computer's own to do it, when anything was."""
        run, kept = self._run(root), (team.kept('taken').get(str(root)) or {}).get('kept')
        with self.files:
            was = (self._load(root).get('driver') or {}).get('computer')
            report = self._step(space, push=False)
            if not report.get('reached'):
                raise WorkspaceError(UNREACHED)
            if root.name in self._clash or (
                    not team.ours(space, self._load(root)) and gitstate.unshared(space, root)):
                kept = gitstate.set_aside(space, root) or kept
                self._as_of.pop(('kept', str(root)), None)
                report = self._step(space, push=False)
            if report.get('conflict'):
                raise WorkspaceError(report['notice'])
            record = self._load(root)
            now = record.get('driver') or None
            if team.ours(space, record):
                self._ours_again(root, run)
                return kept
            if now and now.get('computer') != was:
                raise Elsewhere(f"{now.get('name') or 'Someone'} took this deck on "
                                f"{team.day(now.get('since'))}, after this page last looked. "
                                'Take it over from them if you mean to.')
            mine = team.claim(space)
            record['driver'] = mine
            self._store(root, record)
            run.gone = False
            self._commit(root, f"{mine['name']} takes this deck" + (
                f" over from {now.get('name') or 'someone'}" if now else ''))
            report = self._step(space, push=True)
            record = self._load(root)
            if not team.ours(space, record):   # someone else's claim got there first
                self._forget(root, space)
                raise Elsewhere(self._first_claim(space, record))
            if not report['shared']:
                gitstate.undo(space, root)
                raise WorkspaceError('The shared repository did not take your claim, so this '
                                     'deck was not taken. ' + (report.get('notice') or ''))
            self._ours_again(root, run)
        return kept

    @staticmethod
    def _first_claim(space: gitstate.Workspace, record: dict) -> str:
        who = team.driver(space, record)
        if who is None:
            return 'Someone else changed this deck first, so your claim was dropped. ' \
                + team.NOBODY
        return (f"{who['name']} took this deck first, on {team.day(who['since'])}, so your "
                'claim was dropped. It can be read here. Take it over from them if you mean '
                'to.')

    def _ours_again(self, root: Path, run: _Run) -> None:
        run.gone = False
        run.stop.clear()
        self._clash.pop(root.name, None)
        taken = team.kept('taken')
        if taken.pop(str(root), None) is not None:
            team.keep('taken', taken)

    def _forget(self, root: Path, space: gitstate.Workspace) -> None:
        taken = team.kept('taken')
        lost = taken.pop(str(root), None)
        if lost is not None:
            gitstate.forget(space, lost.get('kept'))
            self._as_of.pop(('kept', str(root)), None)
            team.keep('taken', taken)

    def _hand(self, root: Path, space: gitstate.Workspace) -> None:
        run = self._run(root)
        with self.files:
            record = self._load(root)
            self.hold(root)
            name = (record.get('driver') or {}).get('name') or 'Someone'
            record['driver'] = None
            self._store(root, record)
            self._commit(root, f'{name} hands this deck over')
            run.gone = True     # a step in hand ends, and keeps nothing
            run.stop.set()
            self._step(space, push=True)

    def _aside(self, root: Path, kept: str | None, name: str | None = None,
               when: str | None = None, deleted: bool = False) -> None:
        self._as_of.pop(('kept', str(root)), None)
        taken = team.kept('taken')
        before = taken.get(str(root)) or {}
        taken[str(root)] = {'name': name or before.get('name'),
                            'at': when or before.get('at'),
                            'kept': kept or before.get('kept'),
                            **({'deleted': True} if deleted else {})}
        team.keep('taken', taken)

    def _learn(self, space: gitstate.Workspace, at: str | None = None) -> None:
        """After a fetch, before anything is replayed: stop every deck this computer drove
        that the shared repository now says is someone else's, setting aside what it never
        shared. Call it holding `files`."""
        arrived = gitstate.arrived(space, at)
        for root in self.every():
            try:
                record = decks.read_run(root)
                if not team.ours(space, record) \
                        or gitstate.inside(space, root / decks.RUN) not in arrived:
                    continue
                theirs = json.loads(gitstate.theirs(space, root / decks.RUN, at) or 'null')
            except (WorkspaceError, ValueError, OSError):
                continue
            if not isinstance(theirs, dict) or team.ours(space, theirs):
                continue    # changed on both sides under our name: the replay reports it
            if root.name != self._claiming and gitstate.made_apart(space, root / decks.RUN,
                                                                   at):
                self._move(space, root, theirs, at)    # two decks of one name, made apart
                continue
            run = self._run(root)
            run.gone = True
            run.stop.set()
            who = team.driver(space, theirs)
            by = gitstate.last_by(space, root / decks.RUN, at) or ('Someone', home.now())
            self._aside(root, gitstate.set_aside(space, root, at),
                        who['name'] if who else by[0], who['since'] if who else by[1])
        self._deleted(space, arrived, at)

    def _move(self, space: gitstate.Workspace, root: Path, theirs: dict, at: str) -> None:
        """A teammate started a deck in the same folder as one this computer started while
        the two could not see each other, and theirs was shared first. Theirs keeps the
        folder; this computer's is moved, whole, to a folder of its own and committed there,
        so the replay that follows carries it on top of theirs. Call it holding `files`."""
        record = decks.read_run(root)
        title = record.get('title') or root.name
        run = self._run(root)
        run.gone = True     # a step in hand ends, and keeps nothing
        run.stop.set()
        held = Path(tempfile.mkdtemp(prefix='moving-', dir=agents.staging()
                                     if agents.staging().is_dir() else None))
        try:
            shutil.copytree(root, held / 'deck', symlinks=True)
            gitstate.forget(space, gitstate.set_aside(space, root, at))
            shutil.rmtree(root, ignore_errors=True)
            moved = space.deck(decks.deck_id(space, title))
            shutil.copytree(held / 'deck', moved, symlinks=True)
        finally:
            shutil.rmtree(held, ignore_errors=True)
        record['id'] = moved.name
        decks.write_run(moved, record)
        who = team.driver(space, theirs)
        self._moved[moved.name] = MOVED.format(
            name=who['name'] if who else 'Someone else', folder=space.folder, was=root.name,
            ident=moved.name)
        self._commit(moved, f'move to {space.folder}/{moved.name}, as '
                            f"{who['name'] if who else 'someone else'} started a deck in "
                            f'{space.folder}/{root.name} at the same moment')
        home.forget(root)
        home.remember(moved, title)
        self._woken.append(moved)

    def _deleted(self, space: gitstate.Workspace, arrived: set[str], at: str | None) -> None:
        """What a fetch says about deletions, before anything is replayed. Call it holding
        `files`."""
        names = set()
        for name in arrived:
            parts = PurePosixPath(name).parts
            if len(parts) > 2 and parts[0] == space.folder:
                names.add(parts[1])
        for name in sorted(names):
            root = space.deck(name)
            try:
                if (root / decks.RUN).is_file():
                    if gitstate.theirs(space, root / decks.RUN, at) is None:
                        self._dropped.add(str(root))
                    continue
                # A deck new to this copy was never here to be deleted.
                if not gitstate.known(space, root):
                    continue
                theirs = gitstate.theirs(space, root / decks.RUN, at)
                if theirs is None or not gitstate.unshared(space, root, at):
                    continue
                record = json.loads(theirs)
            except (WorkspaceError, ValueError):
                continue
            who = team.driver(space, record if isinstance(record, dict) else None)
            by = gitstate.last_by(space, root / decks.RUN, at) or ('Someone', home.now())
            self._aside(root, gitstate.set_aside(space, root, at),
                        who['name'] if who else by[0], who['since'] if who else by[1],
                        deleted=True)

    def _clashed(self, space: gitstate.Workspace, report: dict) -> None:
        found = {}
        for name in report.get('conflict') or ():
            parts = PurePosixPath(name).parts
            if len(parts) > 2 and parts[0] == space.folder:
                try:
                    title = decks.read_run(space.deck(parts[1]))['title']
                except (OSError, ValueError, KeyError, TypeError):
                    title = parts[1]
                found[parts[1]] = BROKEN.format(title=title)
        if report.get('reached'):
            self._clash = found

    def _notice(self, root: Path, record: dict | None = None) -> str | None:
        """What a person should know about who drives a deck."""
        if root.name in self._clash:
            return self._clash[root.name]
        if self.mine(root) if record is None else team.ours(self.workspace, record):
            return self._moved.get(root.name) or self._stalled
        lost = team.kept('taken').get(str(root))
        if not lost:
            return None
        if lost.get('deleted'):
            return KEPT_BACK.format(name=lost.get('name') or 'Someone',
                                    when=team.day(lost.get('at')))
        said = TAKEN.format(name=lost.get('name') or 'Someone', when=team.day(lost.get('at'))) \
            if lost.get('name') else ''
        return (said + (SET_ASIDE if lost.get('kept') else '')).strip() or None

    # --- starting and picking up -------------------------------------------------------------

    def start(self, form: dict, uploads: dict | None = None) -> dict:
        """Make a deck from the form as the page sent it, and start its run. `uploads` maps
        an uploaded file's name to its bytes. Returns {'path', 'id'}."""
        space, chosen = self.space(), settings.load()
        gitstate.identity(space.repo)
        checked = decks.check_form(form, self.brands())
        given = self._given(form, checked, uploads or {})
        named = isinstance(form, dict) and form.get('agent') not in (None, '')
        agent = settings.check_agent(form['agent']) if named else chosen.agent
        model = settings.check_model(form.get('model')) if named else chosen.model
        effort = settings.check_effort(form.get('effort') if named else chosen.effort,
                                       agent, model)
        ready = self.ready(agent)
        if not ready.ready:
            raise WorkspaceError(ready.problem)
        source = checked.get('source') or {}
        if checked['route'] == 'existing' and source.get('kind') == 'google' \
                and not self._google_ready():
            raise WorkspaceError(existing.NOT_READY)
        with self.files:
            root = decks.create(space, checked)
            try:
                for name, data in given.items():
                    target = root / INCOMING / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                record = self._load(root)
                record.update(agent=agent, model=model, level_of_effort=effort,
                              driver=team.claim(space),
                              limits={'step_seconds': chosen.step_seconds,
                                      'dollars': chosen.deck_dollars})
                self._store(root, record)
                self._commit(root, 'set up its run' + (
                    f", driven by {record['driver']['name']}" if record['driver'] else ''))
            except BaseException:   # a deck is started whole or not at all
                self._undo_start(space, root)
                raise
            self._claimed(root, space)
            home.remember(root, checked['title'])
        self.wake(root)
        return {'path': str(root), 'id': root.name}

    @staticmethod
    def _given(form: dict, checked: dict, uploads: dict) -> dict:
        """What the form brought besides its words: an upload's bytes or pasted text, by the
        name it waits under in sources/incoming/."""
        source = checked.get('source') or {}
        if source.get('kind') == 'upload':
            data = uploads.get(source['name'])
            if not isinstance(data, (bytes, bytearray)) or not data:
                raise WorkspaceError(f'"{source["name"]}" was not sent with the form. Choose '
                                     'the file again.')
            return {'upload': bytes(data)}
        if source.get('kind') == 'paste':
            return {'pasted.txt': str(form['source']['text']).encode('utf-8')}
        return {}

    def _undo_start(self, space: gitstate.Workspace, root: Path) -> None:
        """Take back a deck that was not started whole: its commits, which were never
        shared, and its folder."""
        gitstate.discard(space, root)
        for _ in range(3):
            if not gitstate.known(space, root) or not gitstate.undo(space, root):
                break
        shutil.rmtree(root, ignore_errors=True)

    def _claimed(self, root: Path, space: gitstate.Workspace, said: str = SAME_TIME) -> None:
        """Share the claim a new deck was committed with, before any work is done for it.
        Someone else's deck of the same name, started at the same moment, stands: this one
        is taken back and refused, naming them. Call it holding `files`."""
        if space.address is None:
            return
        self._claiming = root.name
        try:
            report = self._step(space, push=True)
        finally:
            self._claiming = None
        if root.name in self._clash or not team.ours(space, decks.read_run(root)
                                                     if (root / decks.RUN).is_file() else {}):
            self._clash.pop(root.name, None)
            self._forget(root, space)
            theirs = None
            try:
                theirs = json.loads(gitstate.theirs(space, root / decks.RUN) or 'null')
            except (WorkspaceError, ValueError):
                pass
            who = team.driver(space, theirs if isinstance(theirs, dict) else None)
            if (root / decks.RUN).is_file() and team.ours(space, decks.read_run(root)):
                self._undo_start(space, root)
            self._step(space, push=False)
            raise WorkspaceError(said.format(
                name=who['name'] if who else 'Someone else', folder=space.folder,
                ident=root.name))
        self._unshared = None if report['shared'] else report.get('notice')

    def adopt(self) -> None:
        """Make every deck in the workspace known to this computer's page."""
        known = {entry['path'] for entry in home.decks()}
        for root in self.every():
            if str(root) in known:
                continue
            try:
                home.remember(root, decks.read_run(root).get('title') or root.name)
            except (OSError, ValueError):
                continue

    def resume(self, wait: bool = True) -> None:
        """Pick every deck up where its record says it is. First, in each deck this computer
        drove, what a step left half-made when the runner last ended in the middle of it is
        put back. Then the workspace is fetched, and the decks that are still this
        computer's carry on. With `wait` false the fetch and what follows it happen in the
        background."""
        ours = self._tidy()
        if wait or not self.background:
            self._pick_up(ours)
            return
        space = self.workspace
        self._checking = space is not None and space.address is not None
        threading.Thread(target=self._pick_up, args=(ours,), daemon=True,
                         name='resuming').start()

    def _tidy(self) -> list[Path]:
        ours = []
        for root in self.every():
            try:
                record = self._load(root)
                if not team.ours(self.workspace, record):
                    continue
                research_cli.unlock(root)
                if (root / IN_HAND).exists() and not self._resting(record):
                    with self.files:
                        gitstate.discard(self.space(), root)
                (root / IN_HAND).unlink(missing_ok=True)
            except (WorkspaceError, OSError):
                continue
            ours.append(root)
        return ours

    def _pick_up(self, ours: list[Path]) -> None:
        try:
            self.fetch()
        except (WorkspaceError, OSError):
            pass
        except Exception as failure:  # the runner keeps serving, and says so
            self._stalled = STALLED.format(failure=failure)
        finally:
            self._checking = False
        try:
            self.adopt()
        except Exception as failure:
            self._stalled = STALLED.format(failure=failure)
        for root in ours:
            try:
                if self.mine(root):
                    self.wake(root)
            except (WorkspaceError, OSError):
                continue
            except Exception as failure:
                self._stalled = STALLED.format(failure=failure)

    def wake(self, path) -> None:
        """Have a deck's run look at its record again and carry on if it can."""
        root = self.driven(path)
        if root is None or self._closing:
            return
        if not self.background:
            self._work(root, self._run(root))
            return
        run = self._run(root)
        with self._lock:
            if run.thread is not None and run.thread.is_alive():
                run.again = True
                return
            run.thread = threading.Thread(target=self._drive, args=(root, run), daemon=True,
                                          name=f'run-{root.name}')
            run.thread.start()

    def _drive(self, root: Path, run: _Run) -> None:
        while True:
            self._work(root, run)
            with self._lock:
                if run.again and not self._closing:
                    run.again = False
                    continue
                run.thread = None
                return

    def close(self) -> None:
        """End every worker and wait for the runs to notice. Nothing half-made is kept."""
        self._closing = True
        self._ending.set()
        if self.upkeep is not None:
            self.upkeep.close()
        with self._lock:
            runs = list(self._runs.values())
        for run in runs:
            run.stop.set()
        for thread in [run.thread for run in runs] + [self._sharing, self._serving]:
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=15)

    # --- one step after another --------------------------------------------------------------

    @staticmethod
    def _resting(record: dict) -> bool:
        """True while a run may start nothing: halted, or waiting for an answer."""
        return bool(record.get('halted') or record.get('question'))

    def _work(self, root: Path, run: _Run) -> None:
        """Do one step after another until the deck waits, ends or is halted."""
        if run.busy:  # woken from inside its own step: that step's end looks again anyway
            return
        held, last, run.busy, settled = False, None, True, False
        try:
            while not self._closing:
                record = self._load(root)
                if run.gone or not team.ours(self.workspace, record):
                    return
                if self._resting(record):
                    return
                if not settled:
                    settled = True
                    if self._settle(root, record):
                        continue
                self._original(root, record)
                step = first(record)
                if step is None:
                    return
                if step.kind == 'gate' and gate_state(record, step.name) == 'waiting':
                    return
                if self.background and not held:
                    run.queued = True
                    held = self._slots.take(lambda: self._closing or run.stop.is_set(), run)
                    run.queued = False
                    if not held:
                        return
                    continue    # it may have waited a while: read the record again
                if step.kind != 'agent' and step.name == last:
                    return self._problem(root, step.name, 'failed', (
                        f'The runner could not get past this step: {step.label}.'),
                        KEPT_SO_FAR)
                last = step.name if step.kind != 'agent' else None
                (root / IN_HAND).parent.mkdir(parents=True, exist_ok=True)
                (root / IN_HAND).write_text(f'{step.name}\n', encoding='utf-8')
                with companion.stopping(run.stop):  # a command a step runs ends on Stop
                    getattr(self, RUN[step.name])(root, run, step)
                (root / IN_HAND).unlink(missing_ok=True)
        except _Halted:
            (root / IN_HAND).unlink(missing_ok=True)
        except _Gone:
            (root / IN_HAND).unlink(missing_ok=True)
        except companion.Stopped:   # ended on purpose; IN_HAND stays for the next start
            pass
        except Exception as failure:  # whatever a step does, the runner keeps serving
            (root / IN_HAND).unlink(missing_ok=True)
            self._trouble(root, failure)
        finally:
            if held:
                self._slots.give_back()
            run.queued = run.busy = False

    def _settle(self, root: Path, record: dict) -> bool:
        """Do again the steps whose work this computer lacks. What a deck is made from
        (sources/) and what its steps make on the way (work/) stay on the computer that
        made them, so a deck taken over, or brought in, may lack them. A document or deck
        that was uploaded or pasted cannot be fetched again, and the deck stops saying so.
        Returns True when the record changed."""
        if decks.delivered(root) is not None:
            return False
        names = [step.name for step in stages.steps(record)]

        def did(name: str) -> bool:
            return name in names and bool(tries(record, name).get('done'))

        source, route = (record.get('form') or {}).get('source') or {}, record.get('route')
        lacks = did('intake-source') and (
            (route == 'existing' and not (root / existing.SOURCE).is_file())
            or (route == 'document' and gate_state(record, 'gate:outline') != 'approved'
                and not any(entry['readable'] for entry in documents.listed(root))))
        if lacks and source.get('kind') != 'google':
            self._problem(root, 'intake-source', 'stopped', GIVEN_ELSEWHERE.format(
                how='pasted' if source.get('kind') == 'paste' else 'uploaded'),
                KEPT_SO_FAR, action=None)
            raise _Halted()
        again = ['intake-source'] if lacks else []
        if did('inventory') and gate_state(record, 'gate:classify') != 'approved' \
                and (lacks or not self._shots(root / existing.ORIGINAL_SHOTS)):
            again.append('inventory')
        if gate_state(record, 'gate:look') != 'approved' and did('look-preview') \
                and not (root / looks.SAMPLE).is_file():
            again.append('look-preview')
        if did('patch') and (lacks or not (root / existing.PATCH).is_file()):
            again += ['patch', 'build-render']
        if any(did(name) for name in BUILT) and (
                not build.read_state(root).get('start') and 'build-start' in names
                or did('build-render') and not self._rendered(root, record)):
            again += [name for name in BUILT if name in names]
        again = [name for name in names if name in again and did(name)]
        if not again:
            return False
        with self.files:
            record = self._load(root)
            for name in again:
                record['steps'][name].update(done=False, failed=0)
            if any(name in BUILT or name == 'patch' for name in again) \
                    and gate_state(record, 'gate:build') == 'approved':
                record['gates']['gate:build']['state'] = 'absent'   # shown again first
            self._store(root, record)
            self._commit(root, AGAIN_HERE.format(steps=', '.join(
                stages.BY_NAME[name].label.lower() for name in again)))
        return True

    def _original(self, root: Path, record: dict) -> None:
        """Draw the given deck's slides again, into work/, when the inventory was approved
        on another computer and its pictures stayed there: gate:build shows them beside the
        new ones. Nothing shared changes, so nothing is committed."""
        if record.get('route') != 'existing' \
                or gate_state(record, 'gate:classify') != 'approved' \
                or decks.delivered(root) is not None \
                or not (root / existing.SOURCE).is_file() \
                or self._shots(root / existing.ORIGINAL_SHOTS):
            return
        existing.draw_original(root, record, self.slides(),
                               self._renderer(root, stages.BY_NAME['inventory']))

    def _trouble(self, root: Path, failure: Exception) -> None:
        """Stop a deck on something a step refused or the runner did not expect."""
        if isinstance(failure, (_Gone, _Halted)):
            return
        said = (str(failure) if isinstance(failure, WorkspaceError)
                else f'{type(failure).__name__}: {failure}')
        try:
            record = self._load(root)
            step = first(record)
            self._problem(root, step.name if step else None, 'failed',
                          said if isinstance(failure, WorkspaceError)
                          else f'The runner could not go on: {said}', KEPT_SO_FAR)
        except Exception:  # the record cannot be written either; the view still says why
            pass

    def _done(self, root: Path, step: stages.Step, clock: float, what: str,
              record: dict | None = None, also=()) -> None:
        """Note a step of the runner's own that worked, and commit. Call it holding
        `files`."""
        record = record if record is not None else self._load(root)
        self._tried(record, step.name, home.now(), time.monotonic() - clock, 'kept')
        self._finish(record, step.name)
        self._store(root, record)
        self._commit(root, what, also)

    def _last(self) -> None:
        """Share what the runner did last for a deck: no decision follows it."""
        space = self.workspace
        if space is not None and space.share == gitstate.SHARE[0]:
            self.share_soon()

    def _gate(self, root: Path, run: _Run, step: stages.Step) -> None:
        """Put what the gate decides on in front of the person, and wait."""
        with self.files:
            record = self._load(root)
            if step.name == 'gate:build':
                build.gate_view(root, record)
                record = self._load(root)
            else:
                gate = record['gates'].get(step.name) or {}
                record['gates'][step.name] = {**gate, 'state': 'waiting',
                                              'round': int(gate.get('round') or 0) + 1}
                self._store(root, record)
            self._commit(root, f'ask for your decision on the {WORDS[step.name]}')

    # --- what this computer has for a deck ---------------------------------------------------

    def _look(self, fresh: bool = False) -> dict:
        """What this computer has for making a deck, looked at once every few minutes."""
        with self._looking:
            seen = self._looked
            if not fresh and seen and time.monotonic() - seen[0] < LOOKED_FOR:
                return seen[1]
            found = {'tool': None, 'version': None, 'local': False, 'drive': False,
                     'pictures': False, 'lacks': [],
                     'runtimes': {'slides': None, 'brand': None},
                     'brand': {'found': False, 'name': None, 'brands': [], 'problem': None},
                     'skills': [], 'research': None, 'research_problem': None}
            try:
                tool = self.slides()
                ready = slides_tool.ready(tool, drive=settings.load().previews != 'local')
                found.update(version=ready['version'], local=ready['local'],
                             drive=ready['drive'], pictures=ready['pictures'],
                             lacks=list(ready['missing']))
                found['runtimes']['slides'] = str(tool.runtime)
            except (WorkspaceError, OSError) as refusal:
                found['tool'] = str(refusal)
            try:
                skill = self._skill()
                found['runtimes']['brand'] = str(skill.runtime)
                found['brand'] = {
                    'found': True, 'name': str(skill.name), 'problem': None, 'brands': [
                        {'brand': str(entry.get('brand')), 'name': str(entry.get('name')),
                         'variants': [str(variant) for variant in entry.get('variants') or ()]}
                        for entry in skill.brands() if isinstance(entry, dict)]}
            except (WorkspaceError, OSError) as refusal:
                found['brand']['problem'] = str(refusal)
            try:
                found['skills'] = [entry for entry in brand_skill.found()
                                   if isinstance(entry, dict) and entry.get('runtime')]
            except (WorkspaceError, OSError):
                pass
            try:
                found['research'] = str(self.research().runtime)
            except (WorkspaceError, OSError) as refusal:
                found['research_problem'] = str(refusal)
            self._looked = (time.monotonic(), found)
            return found

    def deck_needs(self, fresh: bool = False) -> dict:
        """What a deck needs on this computer: `missing`, a sentence for each thing it
        lacks; `how`, the way previews are rendered here ('local', 'drive' or None);
        whether `drive` and `local` can render; `google`, whether Google access reaches
        Drive; the slides tool and its `version`; the brand skill found and its `brands`;
        the research tool (`research`, and `research_problem`); and `items`, each need as a
        line of the page's check of this computer."""
        seen, chosen = self._look(fresh), settings.load().previews
        how = chosen or ('local' if seen['local'] else 'drive' if seen['drive'] else None)
        brand, renders = seen['brand'], None
        dated = None if seen['tool'] or not seen['version'] \
            or not self._older(seen['version'], slides_tool.MINIMUM) else (
            f"The slides tool on this computer is version {seen['version']}, and a deck needs "
            f'{slides_tool.MINIMUM} or newer. Update it.')
        # The brand skill is not a need of drawing: a deck without one stops at its brand.
        missing = [said for said in (seen['tool'], dated) if said]
        if not seen['tool']:
            if how is None:
                renders = NOT_CHOSEN if seen['drive'] else NO_RENDERER
            elif not seen[how]:
                renders = NO_DRIVE if how == 'drive' else NO_LOCAL
            missing += [renders] if renders else []
            missing += [NO_PICTURES] if not seen['pictures'] else []
        fact, item = computer.fact, computer.item
        can = {True: 'ok', False: 'problem'}
        items = [
            item('deck-slides', 'The slides tool',
                 'missing' if seen['tool'] else 'problem' if dated else 'ok',
                 [fact('Installed', can[not seen['tool']], seen['version'] or 'not found')],
                 seen['tool'] or dated or ''),
            item('deck-brand', 'A brand skill', 'ok' if brand['found'] else 'missing',
                 [fact('Installed', can[brand['found']], brand['name'] or 'not found')],
                 brand['problem'] or ''),
            item('deck-previews', 'A way to render previews of slides',
                 'problem' if renders or seen['tool'] else 'ok',
                 [fact('LibreOffice on this computer', can[seen['local']]),
                  fact('Google Drive', 'unknown', 'not asked, as LibreOffice makes them')
                  if seen['drive'] is None else fact('Google Drive', can[bool(seen['drive'])]),
                  fact('Chosen', 'ok' if how else 'unknown',
                       {'drive': 'Google Drive', 'local': 'LibreOffice'}.get(how, 'not yet'))],
                 renders or ''),
            item('deck-pictures', 'The programs that turn a render into pictures',
                 'ok' if seen['pictures'] else 'missing',
                 [fact('Installed', can[seen['pictures']])],
                 NO_PICTURES if not seen['pictures'] else ''),
            item('deck-research', 'The research tool',
                 'ok' if seen['research'] else 'missing',
                 [fact('Installed', can[bool(seen['research'])])],
                 seen['research_problem'] or '')]
        return {'missing': missing, 'how': how, 'drive': seen['drive'],
                'local': seen['local'], 'google': bool(seen['drive']),
                'tool': not seen['tool'], 'version': seen['version'],
                'brand': dict(brand), 'brands': list(brand['brands']),
                'research': seen['research'], 'research_problem': seen['research_problem'],
                'items': items}

    @staticmethod
    def _older(version: str, needed: str) -> bool:
        def parts(text: str) -> tuple:
            return tuple(int(part) for part in re.findall(r'\d+', text)[:3])
        return parts(version) < parts(needed)

    def _skill(self):
        """The brand skill to use: the one the person named at set-up, else the first."""
        named = settings.load().brand_skill
        return self.brand(runtime=named) if named else self.brand()

    def brand_skills(self) -> list[dict]:
        named = settings.load().brand_skill
        return [{'name': str(entry.get('name') or entry['runtime']),
                 'path': str(entry['runtime']),
                 'chosen': str(entry['runtime']) == named if named else number == 0}
                for number, entry in enumerate(self._look()['skills'])]

    def brands(self) -> list[dict] | None:
        """The brands the brand skill on this computer has, or None with no brand skill."""
        brand = self._look()['brand']
        return list(brand['brands']) if brand['found'] else None

    def saved(self) -> None:
        """The person saved new settings."""
        self._slots.renew()
        self.deck_needs(fresh=True)

    def look_again(self) -> dict:
        """Look at this computer afresh, and wake every deck."""
        needs = self.deck_needs(fresh=True)
        for root in self.every():
            self.wake(root)
        return needs

    def _google_ready(self) -> bool:
        try:
            return bool(self.slides().drive_check())
        except WorkspaceError:
            return False

    def _renderer(self, root: Path, step: stages.Step) -> str:
        """How this computer renders a deck's slides. A computer that cannot stops the deck
        with what it lacks."""
        needs = self.deck_needs()
        if needs['missing'] or needs['how'] is None:
            said = ' '.join(needs['missing']) or NO_RENDERER
            self._problem(root, step.name, 'stopped', CANNOT_DRAW.format(said=said),
                          KEPT_SO_FAR)
            raise _Halted()
        return needs['how']

    def _contract(self, root: Path) -> Path:
        """The deck's brand contract: exported the first time, and checked every time after,
        before each step that uses it. A brand that changed stops the deck with build's
        sentence."""
        try:
            skill = self._skill()
        except WorkspaceError as refusal:
            # Only a brand skill that is not there at all is said as NO_BRAND: one that is
            # there but cannot be asked, or a folder named for it that holds none, says why.
            if str(refusal) == brand_skill.NO_NODE or os.environ.get(brand_skill.VARIABLE) \
                    or self._look(fresh=True)['skills']:
                raise
            with self.files:
                step = first(self._load(root))
            self._problem(root, step.name if step else 'brand', 'stopped', NO_BRAND,
                          KEPT_SO_FAR)
            raise _Halted()
        with self.files:
            record = self._load(root)
            form = record.get('form') or {}
            if not (root / build.CONTRACT).is_file():
                saved = settings.load()
                try:
                    chosen = decks.deck_brand(form, skill.brands(), saved.brand,
                                              saved.variant)
                except WorkspaceError as refusal:
                    step = first(record)
                    self._problem(root, step.name if step else 'brand', 'stopped',
                                  str(refusal), KEPT_SO_FAR)
                    raise _Halted()
                if (chosen['brand'], chosen['variant']) \
                        != (form.get('brand'), form.get('variant')):
                    record['form'] = {**form, **chosen}
                    self._store(root, record)
                    decks.name_brand(root, record['form'])
                    self._commit(root, 'make it in ' + decks.brand_words(record['form']))
            try:
                return build.export_brand(root, record, skill)
            except build.BrandChanged:
                kept = self._load(root)
                kept['halted'] = {'state': 'stopped', 'action': None, 'kept': KEPT_SO_FAR,
                                  **(kept.get('halted') or {})}
                self._store(root, kept)
                self._commit(root, 'stop: the brand changed since the deck began')
        raise _Halted()

    # --- the steps of the runner's own -------------------------------------------------------

    def _intake_source(self, root: Path, run: _Run, step: stages.Step) -> None:
        """Take in what the form brought: the person's document, or the deck to improve.
        What is fetched or kept goes under sources/, which is never shared, so it is done
        without `files`."""
        clock = time.monotonic()
        record = self._load(root)
        route, source = record['route'], dict((record['form'].get('source') or {}))
        incoming = root / INCOMING
        if route == 'document':
            if not any(entry['readable'] for entry in documents.listed(root)):
                if source.get('kind') == 'upload':
                    source['data'] = (incoming / 'upload').read_bytes()
                elif source.get('kind') == 'paste':
                    source['text'] = (incoming / 'pasted.txt').read_text(encoding='utf-8')
                intake.take_document(root, source, self.google() if self.google else None)
            what = 'take in your document'
        elif route == 'existing':
            if not (root / existing.SOURCE).is_file():
                if source.get('kind') == 'upload':
                    source['data'] = (incoming / 'upload').read_bytes()
                existing.fetch(root, source, self.slides(),
                               source.get('kind') != 'google' or self._google_ready())
                self._same_deck(root, step)
            what = 'bring in your deck'
        else:
            what = 'take in the brief'
        with self.files:
            shutil.rmtree(incoming, ignore_errors=True)
            self._done(root, step, clock, what)

    def _same_deck(self, root: Path, step: stages.Step) -> None:
        """A deck fetched again from Google Slides, on a computer that took it over, must be
        the deck that was read before: what was decided was decided about that one. Its
        slides are compared as the inventory lists them; an export's bytes differ each time."""
        read = home.read_json(root / existing.INVENTORY, None)
        before = read.get('slides') if isinstance(read, dict) else None
        if before is None:
            return
        now = existing.read_deck(root, self.slides())
        if now['slides'] != before:
            self._problem(root, step.name, 'stopped', CHANGED_IN_GOOGLE, KEPT_SO_FAR,
                          action=None)
            raise _Halted()
        if now['sha256'] != read.get('sha256'):    # the same slides, in a new file
            with self.files:
                write_atomic(root / existing.INVENTORY,
                             json.dumps({**read, 'sha256': now['sha256']}, indent=2,
                                        ensure_ascii=False) + '\n')

    def _inventory(self, root: Path, run: _Run, step: stages.Step) -> None:
        how = self._renderer(root, step)
        clock, slides = time.monotonic(), self.slides()
        shared = existing.read_deck(root, slides)
        existing.draw_original(root, self._load(root), slides, how)
        with self.files:
            record = existing.keep_inventory(root, self._load(root), shared)
            self._done(root, step, clock, 'list every slide of your deck', record)

    def _brand_step(self, root: Path, run: _Run, step: stages.Step) -> None:
        clock = time.monotonic()
        self._contract(root)
        with self.files:
            self._done(root, step, clock, 'load the brand')

    def _look_preview(self, root: Path, run: _Run, step: stages.Step) -> None:
        how = self._renderer(root, step)
        self._contract(root)
        clock = time.monotonic()
        looks.draw_sample(root, self._load(root), self.slides(), how)
        with self.files:
            record = self._load(root)
            looks.show_sample(root, record)
            self._done(root, step, clock, 'draw your cover in your brand', record)

    def _build_start(self, root: Path, run: _Run, step: stages.Step) -> None:
        contract = self._contract(root)
        clock = time.monotonic()
        began = build.start(root, self._load(root), self.slides(), contract)  # work/ only
        count = len(began['sections'])
        with self.files:
            self._done(root, step, clock, f"split the deck into {count} section"
                       f"{'' if count == 1 else 's'}")

    def _whole(self, root: Path, how: str) -> None:
        """Put the drawn sections together and preview the deck, in work/, without `files`;
        then share its contact sheet and commit."""
        made = build.draw_whole(root, self._load(root), self.slides(), how)
        count = len(made['slides'])
        with self.files:
            build.share_sheet(root)
            self._commit(root, f"put the deck together: {count} slide"
                               f"{'' if count == 1 else 's'}")

    @staticmethod
    def _needs_whole(root: Path) -> bool:
        """True when sections were drawn since the deck was last put together."""
        state = build.read_state(root)
        if not state.get('start') or build.to_draw(root):
            return False
        if not state['rounds']:
            return True
        made = state['rounds'][-1].get('made_from') or {}
        return any(made.get(ident) != entry.get('file')
                   for ident, entry in (state.get('sections') or {}).items())

    def _build_whole(self, root: Path, run: _Run, step: stages.Step) -> None:
        how = self._renderer(root, step)
        self._contract(root)
        clock = time.monotonic()
        if self._needs_whole(root):
            self._whole(root, how)
        with self.files:
            self._done(root, step, clock, 'the deck is put together')

    def _build_render(self, root: Path, run: _Run, step: stages.Step) -> None:
        how = self._renderer(root, step)
        self._contract(root)
        clock = time.monotonic()
        try:
            skill = self._skill()
        except WorkspaceError:
            skill = None
        build.render(root, self._load(root), self.slides(), brand=skill,  # work/ only
                     renderer=how)
        with self.files:
            self._done(root, step, clock, 'render the deck to deliver')

    def _deliver(self, root: Path, run: _Run, step: stages.Step) -> None:
        clock = time.monotonic()
        space = self.space()
        made = delivering.upload(root, self._load(root), self.slides())
        with self.files:
            record = self._load(root)
            made = delivering.record(root, record, made, space)
            record = self._load(root)
            record['driver'] = None     # a delivered deck has no driver
            where = made.get('url') or made.get('pptx') or ''
            self._done(root, step, clock, f"deliver revision {made['revision']}"
                       + (f': {where}' if where else ''), record, self._listed(space))
        self._last()

    # --- the steps a worker does -------------------------------------------------------------

    def _classify(self, root: Path, run: _Run, step: stages.Step) -> None:
        self._agent(root, run, step,
                    lambda record, request, error: intake.classify_work(root, record, request,
                                                                        error),
                    lambda record, handed: intake.keep_classification(
                        root, record, self._text(handed, intake.NAME)),
                    'keep what your document is')

    def _extract(self, root: Path, run: _Run, step: stages.Step) -> None:
        contract = self._contract(root)
        self._agent(root, run, step,
                    lambda record, request, error: outlines.extract_work(
                        root, record, request, error, contract, self.slides()),
                    lambda record, handed: outlines.keep_outline(
                        root, record, self._text(handed, outlines.NAME), extracted=True),
                    'keep the outline read from your deck')

    def _outline(self, root: Path, run: _Run, step: stages.Step) -> None:
        contract = self._contract(root)
        self._agent(root, run, step,
                    lambda record, request, error: outlines.outline_work(
                        root, record, request, error, contract, self.slides()),
                    lambda record, handed: outlines.keep_outline(
                        root, record, self._text(handed, outlines.NAME)),
                    'keep the outline')

    def _patch(self, root: Path, run: _Run, step: stages.Step) -> None:
        self._contract(root)
        self._agent(root, run, step,
                    lambda record, request, error: existing.patch_work(root, record, request,
                                                                       error),
                    lambda record, handed: existing.keep_patch(
                        root, self._text(handed, existing.NAME)),
                    'keep the plan of the changes you asked for')

    def _draw(self, root: Path, run: _Run, step: stages.Step, how: str) -> None:
        """One try at each section still to draw, side by side. Their previews are still
        taken one at a time."""
        again = step.name == 'build-repair'

        def one(section: str) -> None:
            number = build.numbered(section)
            label = f'Draw section {number}' + (' again' if again else '')
            try:
                self._agent(root, run, step,
                            lambda record, request, error: build.section_work(
                                root, record, section, request, error, how),
                            lambda record, handed: build.keep_section(root, record, section,
                                                                      handed),
                            f'keep section {number}' + (', drawn again' if again else ''),
                            name=f'{step.name}:{section}', label=label)
            except _Halted:
                pass

        sections = build.to_draw(root)
        if self.at_once <= 1 or len(sections) == 1:
            for section in sections:
                one(section)
        else:
            with ThreadPoolExecutor(max_workers=self.at_once) as pool:
                for pending in [pool.submit(contextvars.copy_context().run, one, section)
                                for section in sections]:
                    pending.result()
        if self._resting(self._load(root)):
            raise _Halted()

    def _build_sections(self, root: Path, run: _Run, step: stages.Step) -> None:
        how = self._renderer(root, step)
        self._contract(root)
        if build.to_draw(root):
            self._draw(root, run, step, how)
        if not build.to_draw(root):
            with self.files:
                self._done(root, step, time.monotonic(), 'every section is drawn')

    def _review(self, root: Path, run: _Run, step: stages.Step) -> None:
        self._agent(root, run, step,
                    lambda record, request, error: build.review_work(root, record),
                    lambda record, handed: build.keep_review(root, record, handed),
                    'keep the review of the deck', name=f'{step.name}:review'
                    if step.name == 'build-repair' else None,
                    label='Review the deck again' if step.name == 'build-repair' else None)

    @staticmethod
    def _reviewed(root: Path) -> bool:
        state = build.read_state(root)
        return bool(state['rounds']) and state['rounds'][-1].get('review') is not None

    def _build_review(self, root: Path, run: _Run, step: stages.Step) -> None:
        self._contract(root)
        if self._reviewed(root):
            with self.files:
                self._done(root, step, time.monotonic(), 'the deck is reviewed')
            return
        self._review(root, run, step)

    def _build_repair(self, root: Path, run: _Run, step: stages.Step) -> None:
        """Draw again what a review or the person sent back, put the deck together and
        review it again, until nothing is sent back."""
        how = self._renderer(root, step)
        self._contract(root)
        if build.to_draw(root):
            return self._draw(root, run, step, how)
        if self._needs_whole(root):
            return self._whole(root, how)
        if not self._reviewed(root):
            return self._review(root, run, step)
        with self.files:
            self._done(root, step, time.monotonic(), 'nothing more is sent back')

    # --- what a person does ------------------------------------------------------------------

    @staticmethod
    def _note(note) -> str | None:
        if note is None:
            return None
        if not isinstance(note, str):
            raise WorkspaceError('A note is text.')
        note = note.strip()
        if len(note) > NOTE:
            raise WorkspaceError(f'Say it in at most {NOTE} characters.')
        return note or None

    @staticmethod
    def _numbers(extra: dict) -> list[int] | None:
        named = extra.get('slides')
        if named is None:
            return None
        if not isinstance(named, list) or not all(type(one) is int and one > 0
                                                  for one in named):
            raise WorkspaceError('Name the slides by their numbers.')
        return sorted(set(named))

    @staticmethod
    def _sections_for(root: Path, numbers: list[int] | None) -> list[str]:
        """The sections that draw the slides a person named: every section when they named
        none."""
        state = build.read_state(root)
        began = state.get('start') or {}
        sections = [entry['id'] for entry in began.get('sections') or ()]
        if not numbers or not state.get('rounds'):
            return sections
        ids = {slide['number']: slide['id'] for slide in state['rounds'][-1]['slides']}
        wanted = {ids.get(number) for number in numbers}
        named = [entry['id'] for entry in began.get('sections') or ()
                 if wanted & set(entry['slides'])]
        return named or sections

    def decide(self, path, gate: str, decision: str, note: str | None = None,
               extra: dict | None = None) -> dict:
        """A person's decision at a gate: the only way a gate moves. Returns the deck's
        view."""
        root = self._held(path)
        if gate not in WORDS:
            raise WorkspaceError('A decision is made at one of the gates: '
                                 + ', '.join(WORDS) + '.')
        if decision not in DECISIONS:
            raise WorkspaceError('A decision is to approve, or to ask for changes.')
        note, extra = self._note(note), extra or {}
        if not isinstance(extra, dict):
            raise WorkspaceError('What comes with a decision was not understood.')
        rebrand = gate == 'gate:look' and decision == 'changes'
        if rebrand and not (isinstance(extra.get('brand'), str) and extra['brand'].strip()):
            raise WorkspaceError(NO_BRAND_CHOSEN)
        brands = self.brands() if rebrand else None
        space, it = self.space(), WORDS[gate]
        by = gitstate.identity(space.repo)
        with self.files:
            record = self._load(root)
            after = gate == 'gate:build' and decision == 'changes' \
                and decks.delivered(root) is not None
            if not after and gate_state(record, gate) != 'waiting':
                raise WorkspaceError(NOT_WAITING.format(it=it))
            marked = marks.check(gate, decision, extra, self._marked_ids(root, gate, extra))
            if decision == 'changes' and not note and not rebrand and not marks.asks(marked):
                raise WorkspaceError(NO_NOTE)
            at = home.now()
            if after:
                named = self._numbers(extra)
                gated = record['gates'].get(gate) or {}
                record['gates'][gate] = {**gated, 'slides': named}
                try:
                    record = delivering.again(root, record, self.slides(), note, space)
                except ValueError:
                    raise WorkspaceError(f'This deck has no {it} to change.') from None
                record['gates'][gate].update(by=by)
                for step in self._reopened(record, gate):
                    self._fresh(record, step)
                self._ask_again(root, named, note, at)
                self._store(root, record)
                said = f'ask for changes to the delivered {it}'
            elif decision == 'approve':
                record = self._approve(root, record, gate, note, extra, marked)
                gated = record['gates'].get(gate) or {}
                record['gates'][gate] = {**gated, 'state': 'approved', 'note': note,
                                         'at': at, 'by': by,
                                         'round': int(gated.get('round') or 1)}
                self._store(root, record)
                said = f'approve the {it}'
            else:
                gated = record['gates'].get(gate) or {}
                named = self._numbers(extra) if gate == 'gate:build' else None
                more = {'again': None, 'free': None} if gate == 'gate:research' else {}
                if rebrand:
                    looks.rebrand(root, record, extra['brand'], extra.get('variant'), brands)
                    note = note or ('Make it in ' + decks.brand_words(record['form']) + '.')
                if gate == 'gate:outline' and extra.get('edited') is not None:
                    self._edit_outline(root, record, extra['edited'])
                if marked:
                    record, note, more = self._apply_marks(root, record, gate, marked, note)
                record['gates'][gate] = {**gated, 'state': 'changes', 'note': note, 'at': at,
                                         'by': by, 'round': int(gated.get('round') or 1),
                                         **more,
                                         **({'slides': named} if gate == 'gate:build' else {})}
                try:
                    record = stages.reopen(record, gate)
                except ValueError:
                    raise WorkspaceError(f'This deck has no {it} to change.') from None
                for step in self._reopened(record, gate):
                    self._fresh(record, step)
                if gate == 'gate:build':
                    self._ask_again(root, named, note, at)
                self._store(root, record)
                said = ('make it in ' + decks.brand_words(record['form']) if rebrand
                        else f'ask for changes to the {it}')
            self._commit(root, said, self._listed(space) if after else ())
        if space.share == gitstate.SHARE[0]:
            self.share_soon()
        self.wake(root)
        return self.view(root)

    @staticmethod
    def _reopened(record: dict, gate: str) -> list[str]:
        """The steps a request for changes at `gate` runs again: its feeder and every step
        after it."""
        names = [step.name for step in stages.steps(record)]
        back = stages.feeder(record, gate)
        return names[names.index(back):] if back in names else []

    def _ask_again(self, root: Path, named: list[int] | None, note: str, at: str) -> None:
        """Send the sections back that draw what the person named at gate:build."""
        state = build.read_state(root)
        if not state.get('start'):
            return
        state.update(asked={'note': note, 'sections': self._sections_for(root, named),
                            'at': at}, repaired=0)
        build.write_state(root, state)

    def _approve(self, root: Path, record: dict, gate: str, note: str | None,
                 extra: dict, marked: dict) -> dict:
        """What approving one gate takes beside the approval: what the page chose there,
        and the marks that need no worker. Returns the run."""
        if gate == 'gate:classify' and extra.get('kind') is not None:
            if record['route'] != 'document':
                raise WorkspaceError('Only a document is a spec or material.')
            if extra['kind'] != record.get('classified'):
                record = intake.correct(root, record, extra['kind'])
        elif gate == 'gate:outline' and extra.get('edited') is not None:
            self._edit_outline(root, record, extra['edited'])
        elif gate == 'gate:research-plan' and marked.get('dropped'):
            self._drop_questions(root, record, marked['dropped'])
        elif gate == 'gate:research' and 'left_out' in marked:
            record['research'] = {**(record.get('research') or {}),
                                  'left_out': marked['left_out']}
            write_atomic(root / REPORT, self._report_text(root, record, self._verdicts(root)))
        elif gate == 'gate:look':
            looks.approve(root, record, note)
            record = self._load(root)
        return record

    def _edit_outline(self, root: Path, record: dict, edited) -> None:
        """The outline as the person edited it on the page, checked and saved."""
        try:
            contract = self._contract(root)
        except _Halted:
            raise WorkspaceError(self._load(root)['halted']['why']) from None
        outlines.apply_edits(root, record, edited, self.slides(), contract)

    def _marked_ids(self, root: Path, gate: str, extra: dict) -> list[str]:
        """What the marks at a reviewed stop may name: its questions, or its slides as the
        person's edit has them."""
        if gate in ('gate:research-plan', 'gate:research'):
            return list(self._questions(root))
        if gate == 'gate:outline':
            edited = extra.get('edited')
            slides = edited if isinstance(edited, list) \
                else build.slides_of(home.read_json(root / outlines.OUTLINE, None))
            return [str(one['id']) for one in slides if isinstance(one, dict) and one.get('id')]
        return []

    def _apply_marks(self, root: Path, record: dict, gate: str, marked: dict,
                     note: str | None) -> tuple[dict, str | None, dict]:
        """The marks of a request for changes that need no worker, applied before the stop
        is reopened. Returns the run, the note its worker reads and what the gate keeps
        beside it."""
        more = {}
        if gate == 'gate:research-plan' and marked.get('dropped'):
            self._drop_questions(root, record, marked['dropped'])
        elif gate == 'gate:research':
            if 'left_out' in marked:
                record['research'] = {**(record.get('research') or {}),
                                      'left_out': marked['left_out']}
            added = self._add_questions(root, record, marked.get('add') or [])
            again = {**(marked.get('again') or {}), **{ident: '' for ident in added}}
            more = {'again': again, 'free': note}
        return record, marks.note(gate, marked, note), more

    def act(self, path, action: str) -> dict:
        """Pause, resume, stop, try again or undo the last step, as the person asks."""
        root = self._held(path)
        if action not in ACTIONS:
            raise WorkspaceError('A run can be asked to: ' + ', '.join(ACTIONS) + '.')
        run = self._run(root)
        with self.files:
            record = self._load(root)
            state = self.view(root)['state']
            halted = record.get('halted') or {}
            if action == 'undo':
                if run.busy or run.workers or state == 'working':
                    raise WorkspaceError('Pause it first: a step is in hand.')
                if not gitstate.undo(self.space(), root):
                    raise WorkspaceError(UNDO_NOT)
            else:
                if action == 'pause':
                    if state != 'working':
                        raise WorkspaceError('Only a deck that is working can be paused. This '
                                             f'one is {STATES.get(state, state)}.')
                    record['halted'] = {'state': 'paused', 'step': None, 'action': 'resume',
                                        'why': 'Paused on the page.', 'kept': KEPT_SO_FAR,
                                        'at': home.now()}
                elif action == 'stop':
                    if state not in ('working', 'waiting', 'paused'):
                        raise WorkspaceError(f'This deck is {STATES.get(state, state)}, so '
                                             'there is nothing to stop.')
                    record['halted'] = {'state': 'stopped', 'step': None, 'action': 'resume',
                                        'why': 'Stopped on the page.', 'kept': KEPT_SO_FAR,
                                        'at': home.now()}
                    run.stop.set()
                elif action == 'resume':
                    if halted.get('action') != 'resume':
                        raise WorkspaceError('This deck is not paused or stopped, so there is '
                                             'nothing to resume.')
                elif halted.get('action') != 'retry':
                    raise WorkspaceError('Nothing here failed, so there is nothing to try '
                                         'again.')
                if action in ('resume', 'retry'):
                    if halted.get('limit'):
                        record['cleared'] = spent(record)[0] or 0.0
                    if action == 'retry':
                        self._fresh(record, halted.get('step'))
                    record['halted'] = None
                    chosen = settings.load()
                    record['limits'] = {'step_seconds': chosen.step_seconds,
                                        'dollars': chosen.deck_dollars}
                self._store(root, record)
                self._commit(root, {'pause': 'paused on the page',
                                    'stop': 'stopped on the page',
                                    'resume': 'resumed on the page',
                                    'retry': 'asked to try again on the page'}[action])
        if action in ('resume', 'retry', 'undo'):
            run.stop.clear()
            self.wake(root)
        return self.view(root)

    def answer(self, path, ident: str, text: str) -> dict:
        """Record a person's answer to a worker's question. The step runs again with it."""
        root = self._held(path)
        if not isinstance(text, str) or not text.strip():
            raise WorkspaceError('Write an answer first.')
        with self.files:
            record = self._load(root)
            asked = record.get('question')
            if not asked or asked.get('id') != ident:
                raise WorkspaceError('That question is not waiting for an answer any more.')
            record['answers'].setdefault(asked['step'], []).append(
                {'question': asked['text'], 'answer': text.strip()[:NOTE], 'at': home.now()})
            record['question'] = None
            self._store(root, record)
            self._commit(root, "a worker's question was answered on the page")
        self.wake(root)
        return self.view(root)

    # --- pictures and the deck itself --------------------------------------------------------

    @staticmethod
    def _shots(folder: Path) -> dict:
        found = home.read_json(folder / existing.SHOTS, None)
        listed = found.get('slides') if isinstance(found, dict) else None
        return {one.get('number'): folder / str(one.get('image')) for one in listed or ()
                if isinstance(one, dict)}

    def picture(self, path, kind: str, ref) -> bytes:
        """One picture of a deck, as PNG bytes: a slide of the build (`ref` its number, or
        'contact-sheet'), the sample of its brand (`ref` 'sample'), or a slide of the deck
        that was given (its number). Only a picture the steps recorded under the deck's work/
        folder is served, and the deck's contact sheet."""
        root = self.driven(path)
        if root is None:
            raise WorkspaceError('There is no deck there.')
        if kind not in PICTURE_KINDS:
            raise WorkspaceError('A picture is of the build, the brand or the original deck.')
        within, file = (root / 'work').resolve(), None
        if kind == 'build' and ref == SHEET:
            within, file = root.resolve(), root / build.SHEET
        elif kind == 'look':
            file = root / looks.SAMPLE if str(ref) == 'sample' else None
        else:
            try:
                number = int(ref)
            except (TypeError, ValueError):
                raise WorkspaceError('Name the slide by its number.') from None
            folder = root / (existing.ORIGINAL_SHOTS if kind == 'original'
                             else existing.AFTER_SHOTS)
            file = self._shots(folder).get(number)
        if file is None or within not in file.resolve().parents or not file.is_file():
            raise FileNotFoundError(NO_PICTURE)
        return worker_tools.picture(file)

    def download(self, path) -> tuple[str, bytes]:
        """The rendered deck, as a PowerPoint file: (its name, its bytes)."""
        root = self.driven(path)
        if root is None:
            raise WorkspaceError('There is no deck there.')
        record = self._load(root)
        deck = build.delivered_deck(root, record)
        return f'{root.name}.pptx', deck.read_bytes()

    # --- sharing -----------------------------------------------------------------------------

    def _step(self, space: gitstate.Workspace, push: bool) -> dict:
        """Get in step with the shared repository: fetch, learn which decks are no longer
        this computer's, replay, and push if asked. Never raises for the remote's sake."""
        try:
            report = gitstate.sync(space, push=push, before=lambda at: self._learn(space, at),
                                   held=self.files)
        except WorkspaceError as refusal:
            report = {'shared': False, 'reached': False, 'received': 0, 'conflict': [],
                      'notice': str(refusal)}
        with self.files:
            self._clashed(space, report)
            if self._clash:
                report['notice'] = ' '.join(self._clash.values())
            if report.get('reached'):
                self._fetched += 1
            dropped, self._dropped = self._dropped, set()
            for name in sorted(dropped):
                if not (Path(name) / decks.RUN).is_file():
                    self._let_go(Path(name))
        with self._lock:
            woken, self._woken = self._woken, []
        for moved in woken:
            self.wake(moved)
        if report.get('reached'):
            if not push:
                team.fetch_tags(space)
            elif self._tags_unsent:
                self._tags_unsent = team.send_tags(space) is not None
        return report

    def _listed(self, space: gitstate.Workspace) -> list[Path]:
        """The list of decks a step module just wrote, to commit with what it is part of: in
        a workspace on this computer, the README; in a shared one nothing, as the file is
        put back, to be written and shared on its own once the workspace is in step. Call it
        holding `files`."""
        index = space.root / 'README.md'
        if space.address is None:
            return [index]
        gitstate.discard(space, index)
        return []

    def _index(self, space: gitstate.Workspace) -> None:
        """The list of decks in the workspace's README. In a workspace on this computer it is
        written and committed at once. In a shared one the file is put back, and written
        and shared on its own once the workspace is in step, so that two computers
        delivering at once never stop each other sharing. Call it holding `files`."""
        index = space.root / 'README.md'
        if space.address is None:
            decks.write_index(space)
            gitstate.commit(space, 'Update the list of decks', [index])
        else:
            gitstate.discard(space, index)

    def _reindex(self, space: gitstate.Workspace) -> None:
        """Write and share the list of decks, now that the workspace is in step. One the
        shared repository would not take is taken back, to be written again next time."""
        index = space.root / 'README.md'
        with self.files:
            before = text_of(index)
            decks.write_index(space)
            if text_of(index) == before or gitstate.changed(space) != [
                    gitstate.inside(space, index)]:
                gitstate.discard(space, index)
                return
            gitstate.commit(space, 'Update the list of decks', [index])
        report = gitstate.sync(space, push=True, held=self.files)
        if not report.get('shared'):
            with self.files:
                gitstate.undo(space, index)

    def share(self) -> dict:
        """Share the workspace now. Never fails a run."""
        space = self.space()
        report = self._step(space, push=True)
        if report.get('shared') and space.address is not None:
            self._reindex(space)
        self._unshared = None if report['shared'] else report['notice']
        self.adopt()
        return {'shared': bool(report['shared']), 'notice': report['notice']}

    def fetch(self) -> dict:
        """Bring in what teammates have shared, and send nothing."""
        space = self.workspace
        if space is None or space.address is None:
            return {'reached': None, 'received': 0, 'notice': None}
        report = self._step(space, push=False)
        self.adopt()
        return {'reached': bool(report.get('reached')), 'received': report.get('received', 0),
                'notice': report.get('notice')}

    def share_soon(self) -> None:
        """Share without making anyone wait for it."""
        space = self.workspace
        if space is None or space.address is None:
            return
        if not self.background:
            self.share()
            return
        with self._lock:
            if self._sharing is not None and self._sharing.is_alive():
                self._share_again = True
                return
            self._sharing = threading.Thread(target=self._share_on, daemon=True,
                                             name='sharing')
            self._sharing.start()

    def _share_on(self) -> None:
        while True:
            try:
                self.share()
            except Exception as failure:  # sharing never ends the runner
                self._unshared = f'The work could not be shared ({failure}). It is kept on ' \
                                 'this computer.'
            with self._lock:
                if self._share_again and not self._closing:
                    self._share_again = False
                    continue
                self._sharing = None
                return

    def shared(self) -> dict:
        """Whether everything committed here has been shared, as far as can be told without
        asking the remote, and why the last try at sharing did not share it."""
        space = self.workspace
        if space is None or space.address is None:
            return {'shared': False, 'notice': None}
        refs, seen = _refs(space.repo, space.branch), self._ahead
        if refs is not None and seen is not None and seen[0] == refs:
            waiting = seen[1]
        else:
            waiting = hub.ahead(space.repo, f'refs/remotes/origin/{space.branch}')
            self._ahead = None if refs is None else (refs, waiting)
        return {'shared': not waiting, 'notice': self._unshared if waiting else None}

    # --- what the page shows -----------------------------------------------------------------

    def _state(self, root: Path, record: dict, run: _Run) -> tuple[str, str]:
        """A deck's state, and what is happening in a sentence."""
        halted, nxt = record.get('halted'), first(record)
        if halted:
            return halted.get('state') or 'failed', halted.get('why') or 'It has stopped.'
        if record.get('question'):
            return 'waiting', f"A question is waiting for you: {record['question']['text']}"
        if nxt is None:
            said = decks.delivered(root) or {}
            where = said.get('url') or said.get('pptx')
            return 'finished', (f"Delivered as revision {said.get('revision')}"
                                + (f': {where}.' if where else '.') + (
                                    f" {said['notice']}" if said.get('notice') else ''))
        if nxt.kind == 'gate' and gate_state(record, nxt.name) == 'waiting':
            return 'waiting', f'{nxt.doing}.'
        if run.queued:
            ahead = self._slots.ahead(run) or 0
            return 'working', 'Waiting for its turn. ' + (
                'It is next.' if not ahead else '1 deck is ahead of it.' if ahead == 1
                else f'{ahead} decks are ahead of it.')
        if nxt.kind == 'gate':
            return 'working', f'Getting the {WORDS[nxt.name]} ready for your decision.'
        error = last_error(record, nxt.name)
        if error:
            return 'working', f'{nxt.doing} again. The last try did not work: {error}'
        return 'working', f'{nxt.doing}.'

    def _queue(self, run: _Run) -> dict | None:
        ahead = self._slots.ahead(run) if run.queued else None
        return None if ahead is None else {'ahead': ahead}

    def _since_fetch(self, what: str, root: Path, read):
        kept = self._as_of.get((what, str(root)))
        if kept is None or kept[0] != self._fetched:
            kept = self._as_of[(what, str(root))] = (self._fetched, read())
        return kept[1]

    def _set_aside(self, root: Path) -> list[str]:
        space = self.workspace
        if space is None or space.address is None:
            return []
        return list(self._since_fetch('kept', root, lambda: gitstate.kept(space, root)))

    def _then(self, root: Path, record: dict) -> str:
        """Where a deck stood when it was last shared, said of the past."""
        halted, nxt = record.get('halted'), first(record)
        if halted:
            return f"Then, it had stopped: {halted.get('why')}"
        if record.get('question'):
            return 'Then, a question was waiting for an answer.'
        if nxt is None:
            return 'Then, it was delivered.'
        if nxt.kind == 'gate' and gate_state(record, nxt.name) == 'waiting':
            return f'Then, the {WORDS[nxt.name]} was waiting for a decision.'
        label = nxt.label
        return f'Then, the next step was to {label[:1].lower() + label[1:]}.'

    def _last_shared(self, root: Path, record: dict) -> dict:
        space = self.workspace
        by, at = self._since_fetch('last', root, lambda: gitstate.last_by(space, root)) \
            or (None, None)
        try:
            at = datetime.fromisoformat(at).astimezone(timezone.utc).strftime(
                '%Y-%m-%dT%H:%M:%SZ') if at else None
        except ValueError:
            at = None
        return {'at': at, 'by': by, 'says': self._then(root, record)}

    def _whose(self, root: Path, record: dict, state: str, sentence: str):
        """Whether a deck is this computer's, who drives it, and its state and sentence as
        someone who can only read it is told them."""
        space = self.workspace
        mine, who = team.ours(space, record), team.driver(space, record)
        if mine:
            return mine, who, state, sentence, None
        if who is None:
            return mine, who, *((state, sentence) if state == 'finished'
                                else ('stopped', team.NOBODY)), None
        last = self._last_shared(root, record)
        when = f", on {team.day(last['at'])}" if last['at'] else ''
        return mine, who, 'elsewhere', (THEIRS.format(name=who['name']) + LAST.format(
            when=when, then=last['says'])), last

    def _workers(self, run: _Run) -> list[dict]:
        with self._lock:
            live = list(run.workers.items())
        return [{'id': ident, 'label': worker['label'], 'started_at': worker['started_at'],
                 'lines': list(worker['lines'])} for ident, worker in live]

    def _timeline(self, record: dict, state: str) -> list[dict]:
        """stages.timeline, with each step's tries, time, cost and last error."""
        rows, failed = stages.timeline(record), (record.get('halted') or {}).get('step')
        for row in rows:
            tried = attempts(record, row['name'])
            dollars = [attempt['dollars'] for attempt in tried
                       if attempt.get('dollars') is not None]
            row.update(attempts=len(tried),
                       seconds=round(sum(attempt.get('seconds') or 0 for attempt in tried), 1)
                       if tried else None,
                       dollars=round(sum(dollars), 4) if dollars else None,
                       error=None if row['state'] == 'done' else last_error(record,
                                                                            row['name']),
                       failed=state == 'failed' and row['name'] == failed)
        return rows

    def _gate_view(self, root: Path, record: dict) -> dict | None:
        """What the page shows at the gate that waits, or None when none does."""
        nxt = first(record)
        if nxt is None or nxt.kind != 'gate' or gate_state(record, nxt.name) != 'waiting':
            return None
        gate = record['gates'].get(nxt.name) or {}
        shown = {'name': nxt.name, 'label': nxt.label, 'words': WORDS[nxt.name],
                 'round': gate.get('round'), 'note': gate.get('note'),
                 'said': record['said'].get(FED_BY.get(nxt.name, ''))}
        view = getattr(self, f"_show_{nxt.name.partition(':')[2].replace('-', '_')}")
        shown.update(view(root, record))
        return shown

    def _show_classify(self, root: Path, record: dict) -> dict:
        if record['route'] == 'document':
            text = text_of(root / intake.FILE) or ''
            said = dict(re.findall(r'^(Verdict|Reason|Slides): (.*)$', text, re.MULTILINE))
            return {'kind': 'document', 'verdict': record.get('classified'),
                    'reason': said.get('Reason'), 'slides': said.get('Slides'),
                    'corrected': '(Corrected by you)' in said.get('Verdict', ''),
                    'documents': [{key: entry.get(key) for key in ('name', 'title', 'bytes',
                                                                   'readable')}
                                  for entry in documents.listed(root)]}
        found = outlines.inventory_of(root) or {}
        pictured = sorted(number for number in self._shots(root / existing.ORIGINAL_SHOTS)
                          if isinstance(number, int))
        return {'kind': 'deck', 'source': found.get('source'),
                'inventory': [{'number': slide.get('number'), 'title': slide.get('title'),
                               'hidden': bool(slide.get('hidden')),
                               'words': sum(len((item.get('text') or '').split())
                                            for item in slide.get('objects') or ())}
                              for slide in found.get('slides') or ()],
                'pictures': [{'kind': 'original', 'ref': number} for number in pictured]}

    def _show_research_plan(self, root: Path, record: dict) -> dict:
        plan = home.read_json(root / PLAN, None)
        items = plan.get('items') if isinstance(plan, dict) else None
        return {'text': text_of(root / PLAN_MD) or '',
                'questions': [{'id': item['id'], 'title': marks.title(item['id']),
                               'question': str(item.get('question') or ''),
                               'search': item.get('public_query')}
                              for item in items or ()
                              if isinstance(item, dict) and isinstance(item.get('id'), str)]}

    def _show_research(self, root: Path, record: dict) -> dict:
        return {'text': text_of(root / REPORT) or '', 'verdicts': self._verdicts(root),
                'items': self._findings_shown(root, record)}

    def _show_outline(self, root: Path, record: dict) -> dict:
        found = home.read_json(root / outlines.OUTLINE, None)
        return {'text': text_of(root / outlines.OUTLINE_MD) or '',
                'slides': build.slides_of(found) if isinstance(found, dict) else [],
                'delivery': (found.get('delivery') if isinstance(found, dict) else None)
                or build.DELIVERY}

    def _show_look(self, root: Path, record: dict) -> dict:
        form = record.get('form') or {}
        return {'text': text_of(root / looks.LOOK_MD) or '', 'brand': form.get('brand'),
                'variant': form.get('variant'), 'made_in': decks.brand_words(form),
                'picture': {'kind': 'look', 'ref': 'sample'}
                if (root / looks.SAMPLE).is_file() else None}

    def _show_build(self, root: Path, record: dict) -> dict:
        """build.gate_view, with each picture named as `picture` takes it, never by path."""
        shown = build.gate_view(root, json.loads(json.dumps(record)))
        for slide in shown['slides']:
            slide['image'] = {'kind': 'build', 'ref': slide['number']}
        shown['pairs'] = [{'number': pair['number'],
                           'before': {'kind': 'original', 'ref': pair['number']},
                           'after': {'kind': 'build', 'ref': pair['number']}
                           if pair.get('after') else None} for pair in shown['pairs']]
        shown['contactSheet'] = {'kind': 'build', 'ref': SHEET} \
            if shown.get('contactSheet') else None
        return shown

    def view(self, path) -> dict | None:
        """Everything the page shows for one deck. None when there is no deck there."""
        root = self.driven(path)
        if root is None:
            return None
        record = self._load(root)
        run = self._run(root)
        state, sentence = self._state(root, record, run)
        mine, who, state, sentence, last = self._whose(root, record, state, sentence)
        asked, halted = record.get('question'), record.get('halted')
        dollars, tokens = spent(record)
        said = decks.delivered(root)
        return {
            'id': record.get('id') or root.name, 'path': str(root), 'title': record['title'],
            'route': record['route'], 'level': (record.get('form') or {}).get('level'),
            'output': (record.get('form') or {}).get('output'),
            'state': state, 'sentence': sentence, 'timeline': self._timeline(record, state),
            'gate': self._gate_view(root, record) if not halted else None,
            'driver': who, 'mine': mine, 'notice': self._notice(root, record),
            'taken': None if mine else team.taken(root), 'last_shared': last,
            'kept': self._set_aside(root), 'clash': root.name in self._clash,
            'queue': self._queue(run) if mine else None,
            'spent': {'dollars': dollars, 'tokens': tokens},
            'agent': record.get('agent'), 'model': record.get('model'),
            'effort': record.get('level_of_effort'),
            'workers': self._workers(run),
            'question': ({'id': asked['id'], 'text': asked['text'], 'from': asked['from']}
                         if asked and mine else None),
            'problem': ({key: halted.get(key) for key in ('state', 'why', 'kept', 'action')}
                        if halted else None),
            'deliver': ({**said, 'revisions': list(record.get('revisions') or []),
                         'download': self._rendered(root, record),
                         'to_google': said.get('notice') == delivering.NOT_CONNECTED
                         and ((record.get('form') or {}).get('output') or 'google')
                         == 'google'}
                        if said else None),
            'contactSheet': (root / build.SHEET).is_file()}

    @staticmethod
    def _rendered(root: Path, record: dict) -> bool:
        try:
            build.delivered_deck(root, record)
            return True
        except WorkspaceError:
            return False

    def _brief(self, root: Path) -> dict:
        """A deck in a few words, for a list."""
        try:
            record = self._load(root)
        except WorkspaceError as failure:
            return {'path': str(root), 'id': root.name, 'title': root.name, 'route': None,
                    'level': None, 'state': 'failed', 'sentence': str(failure),
                    'needs': True, 'mine': True, 'driver': None, 'notice': None,
                    'link': None, 'contactSheet': False, 'last_shared': None}
        run = self._run(root)
        state, sentence = self._state(root, record, run)
        halted = record.get('halted') or {}
        needs = bool(record.get('question') or state == 'waiting'
                     or (halted and halted.get('state') == 'failed'))
        mine, who, state, sentence, last = self._whose(root, record, state, sentence)
        said = decks.delivered(root) or {}
        return {'path': str(root), 'id': root.name, 'title': record.get('title'),
                'route': record.get('route'),
                'level': (record.get('form') or {}).get('level'), 'state': state,
                'sentence': sentence, 'needs': needs and mine, 'mine': mine, 'driver': who,
                'notice': self._notice(root, record), 'link': said.get('url'),
                'pptx': bool(said.get('pptx')), 'revision': said.get('revision'),
                'contactSheet': (root / build.SHEET).is_file(), 'last_shared': last}

    def decks(self) -> dict:
        """Every deck in the workspace, in the page's four lists: `needs` a decision of this
        computer's person, `working` on this computer, `finished` (delivered), and
        `elsewhere`, run by a teammate or by nobody."""
        found = {'needs': [], 'working': [], 'finished': [], 'elsewhere': []}
        for root in self.every():
            brief = self._brief(root)
            if brief['state'] == 'finished':
                found['finished'].append(brief)
            elif not brief['mine']:
                found['elsewhere'].append(brief)
            elif brief['needs']:
                found['needs'].append(brief)
            else:
                found['working'].append(brief)
        return found

    def status(self) -> dict:
        return {'problem': agents.data_shared(), 'decks': [{key: brief[key] for key in ('path', 'id', 'state', 'sentence')}
                          for brief in (self._brief(root) for root in self.every())]}

    def standing(self) -> dict:
        """What the status screen shows: every run on this computer with what it is doing
        and what it has cost, and apart from those the decks teammates drive."""
        runs, elsewhere = [], []
        for root in self.every():
            brief = self._brief(root)
            shown = {key: brief[key] for key in ('path', 'id', 'title', 'state', 'sentence',
                                                 'driver')}
            if brief['mine']:
                try:
                    dollars, tokens = spent(self._load(root))
                except WorkspaceError:
                    dollars = tokens = None
                runs.append({**shown, 'needs': brief['needs'],
                             'queue': self._queue(self._run(root)),
                             'spent': {'dollars': dollars, 'tokens': tokens},
                             'notice': brief['notice']})
            elif brief['driver'] is not None:
                elsewhere.append({**shown, 'last_shared': brief['last_shared'],
                                  'notice': brief['notice']})
        return {'limit': settings.load().parallel, 'runs': runs, 'elsewhere': elsewhere,
                'background': self.went_wrong(),
                'upkeep': self.upkeep.report() if self.upkeep else None}

    def went_wrong(self) -> dict | None:
        kept = list(self._background.values())
        return max(kept, key=lambda found: found['at']) if kept else None

    # --- a notification when no page is open -------------------------------------------------

    def seen(self) -> None:
        """A page asked something, so one is open."""
        self._asked = time.monotonic()

    def page_open(self) -> bool:
        return self._asked is not None and time.monotonic() - self._asked < PAGE_OPEN

    @staticmethod
    def _needs(record: dict) -> str | None:
        """The one thing a deck needs its person for now, named so that the same thing is
        never taken for a new one."""
        halted, asked = record.get('halted') or {}, record.get('question')
        if halted:
            return f"problem:{halted.get('at')}" if halted.get('state') == 'failed' else None
        if asked:
            return f"question:{asked.get('id')}"
        nxt = first(record)
        if nxt is not None and nxt.kind == 'gate' and gate_state(record, nxt.name) == 'waiting':
            return f"gate:{nxt.name}:{(record['gates'].get(nxt.name) or {}).get('round')}"
        return None

    def tell(self) -> list[str]:
        """Tell the person, through the computer's own notifications, about each deck of
        this computer's that needs a decision: only when that is turned on and no page is
        open, and once for each thing. Returns the titles that were told."""
        if not settings.load().notify or self.page_open():
            return []
        space, sent, told = self.workspace, team.kept('notified'), []
        for root in self.every():
            try:
                record = self._load(root)
                if not team.ours(space, record):
                    continue
            except WorkspaceError:
                continue
            thing = self._needs(record)
            if thing is None or sent.get(str(root)) == thing:
                continue
            if self.notifier.send(record['title']):
                sent[str(root)] = thing
                told.append(record['title'])
        if told:
            team.keep('notified', sent)
        return told

    def serving(self, every: float = FETCH_EVERY, tick: float = TICK) -> None:
        """While the runner serves: fetch every few minutes, and notify. `close` ends it."""
        with self._lock:
            if self._serving is not None and self._serving.is_alive():
                return
            self._serving = threading.Thread(target=self._serve, args=(every, tick),
                                             daemon=True, name='in-step')
            self._serving.start()

    def _serve(self, every: float, tick: float) -> None:
        last = time.monotonic()
        while not self._ending.wait(tick):
            if time.monotonic() - last >= every:
                last = time.monotonic()
                if not self._kept('fetch', self.fetch):
                    continue
            self._kept('tell', self.tell)

    def _kept(self, job: str, action) -> bool:
        try:
            action()
        except Exception as failure:  # neither ever ends the runner; the next look tries again
            said = str(failure).strip().rstrip('.') or type(failure).__name__
            self._background[job] = {'at': home.now(),
                                     'says': BACKGROUND[job].format(said=said)}
            return False
        self._background.pop(job, None)
        return True

    # --- publishing inside the workspace -----------------------------------------------------

    def publish(self, path) -> dict:
        """Publish a deck as it stands: the next numbered revision, a tag on the commit where
        the workspace is, pushed with it. One that is not delivered yet is published all the
        same, and the revision says so."""
        root = self.driven(path)
        if root is None:
            raise WorkspaceError('There is no deck there.')
        space = self.space()
        with self.files:
            record = self._load(root)
            who = team.driver(space, record)
            if who is not None and not who['here']:
                raise Elsewhere(team.elsewhere(space, record))
            by = gitstate.identity(space.repo)
        if space.address is not None:
            self._step(space, push=True)
        with self.files:
            ready = decks.delivered(root) is not None
            made = team.publish(space, root.name, record['title'], ready, by)
        said = []
        if not ready:
            said.append(f"Revision {made['revision']} was published before this deck was "
                        'delivered, and says so.')
        if space.address is None:
            said.append('This workspace has no shared repository, so the revision is kept on '
                        'this computer.')
        elif not made['shared']:
            self._tags_unsent = True
            said.append('The revision is kept on this computer and is not shared yet '
                        f"({made['why']}). It goes with the workspace the next time it is "
                        'shared.')
        return {'revision': made['revision'], 'ready': ready, 'shared': made['shared'],
                'notice': ' '.join(said) or None}

    def deliver_again(self, path) -> dict:
        """Send a deck that was made as a PowerPoint file, because Google was not
        connected, to Google Slides as its form asked. Nothing about the deck changes: the
        deck that was delivered goes to Google as the next revision. Returns its view."""
        root = self.driven(path)
        if root is None:
            raise WorkspaceError('There is no deck there.')
        space, slides = self.space(), self.slides()
        with self.files:
            record = self._load(root)
            who = team.driver(space, record)
            if who is not None and not who['here']:
                raise Elsewhere(team.elsewhere(space, record))
            said = decks.delivered(root)
            if said is None:
                raise WorkspaceError('This deck has not been delivered yet.')
            if said.get('notice') != delivering.NOT_CONNECTED \
                    or ((record.get('form') or {}).get('output') or 'google') != 'google':
                raise WorkspaceError('This deck is already delivered as you asked, so there '
                                     'is nothing to send to Google Slides.')
            if str(root) in self._sending:
                raise WorkspaceError(ON_ITS_WAY)
            self._sending.add(str(root))
        try:
            if not slides.drive_check():
                raise WorkspaceError(STILL_NOT_CONNECTED)
            made = delivering.upload(root, record, slides)
            if made.get('output') != 'google' or not made.get('url'):
                raise WorkspaceError(STILL_NOT_CONNECTED)
            with self.files:
                record = self._load(root)
                if decks.delivered(root) != said:
                    raise WorkspaceError('The deck changed while it was being sent. Look at '
                                         'it again before you deliver it.')
                made = delivering.record(root, record, made, space)
                self._commit(root, f"deliver revision {made['revision']} to Google Slides: "
                             f"{made['url']}", self._listed(space))
        finally:
            with self.files:
                self._sending.discard(str(root))
        self._last()
        return self.view(root)

    def published(self) -> list[dict]:
        space = self.workspace
        if space is None:
            return []
        return [entry for entry in team.published(space)
                if (Path(entry['path']) / decks.RUN).is_file()]

    # --- deleting a deck ---------------------------------------------------------------------

    def _may_not(self, space: gitstate.Workspace, record: dict, state: str) -> str | None:
        """Why this computer may not delete a deck, in a sentence; None when it may."""
        if self._checking:
            return CHECKING
        if team.ours(space, record):
            return None
        who = team.driver(space, record)
        if who is None:
            return None if state == 'finished' else NOT_TAKEN
        return NOT_YOURS.format(name=who['name'])

    def _drive_files(self, root: Path, record: dict) -> list[dict]:
        """What a deck left in Google Drive, which the runner never deletes."""
        found = []
        kept = home.read_json(root / build.BUILD / 'drive-preview.json', None)
        if isinstance(kept, dict) and kept.get('url'):
            found.append({'what': DRIVE_FILES['preview'], 'name': kept.get('name'),
                          'url': kept['url']})
        for revision in record.get('revisions') or ():
            if isinstance(revision, dict) and revision.get('url'):
                found.append({'what': DRIVE_FILES['slides'],
                              'name': f"Revision {revision.get('revision')}",
                              'url': revision['url']})
        return found

    def leaving(self, path) -> dict:
        """What deleting a deck would do, for the confirmation."""
        root = self.driven(path)
        if root is None:
            raise WorkspaceError('There is no deck there.')
        space, record, run = self.space(), self._load(root), self._run(root)
        state = self._state(root, record, run)[0]
        why = self._may_not(space, record, state)
        mine, _, shown, _, _ = self._whose(root, record, state, '')
        return {'path': str(root), 'title': record['title'], 'state': shown,
                'may': why is None, 'why': why,
                'stops': bool(mine and (state == 'working' or run.workers or run.busy)),
                'share': None if space.address is None else space.share,
                'revisions': team.revisions(space, root.name),
                'documents': len(documents.listed(root)),
                'drive': self._drive_files(root, record)}

    def delete(self, path, title: str) -> dict:
        """Delete a deck, as the person asks on the page. `title` is the one the page
        showed, so a page that is out of date deletes nothing."""
        root = self.driven(path)
        if root is None:
            raise WorkspaceError('There is no deck there.')
        space = self.space()
        by = gitstate.identity(space.repo)
        run = self._run(root)

        def allowed() -> None:
            record = self._load(root)
            if record['title'] != title:
                raise WorkspaceError(MISTITLED)
            why = self._may_not(space, record, self._state(root, record, run)[0])
            if why:
                raise Elsewhere(why)

        with self.files:
            allowed()
            run.gone = True
            run.stop.set()
        if not self._ended(run):
            with self.files:
                run.gone = False
                record = self._load(root)
                record['halted'] = {'state': 'stopped', 'step': None, 'action': 'resume',
                                    'why': 'Stopped on the page.', 'kept': KEPT_SO_FAR,
                                    'at': home.now()}
                self._store(root, record)
                self._commit(root, 'stopped on the page')
            raise WorkspaceError(NOT_ENDED)
        with self.files:
            if not (root / decks.RUN).is_file():
                raise WorkspaceError('This deck is not here any more.')
            allowed()
            gitstate.remove(space, root, f'{title}: {by} deletes this deck, on '
                                         f'{team.day(home.now())}')
            self._let_go(root, keep=True)
            self._index(space)
        report = None
        if space.address is not None and space.share == gitstate.SHARE[0]:
            report = self._step(space, push=True)
            self._unshared = None if report['shared'] else report['notice']
        with self.files:
            back = (root / decks.RUN).is_file()
            if not back:
                shutil.rmtree(root, ignore_errors=True)
        if back:
            self.adopt()
            raise WorkspaceError(self._notice(root) or KEPT_BACK.format(
                name='Someone', when='a moment ago'))
        shared = None if space.address is None else bool(report and report['shared'])
        return {'deleted': True, 'title': title, 'shared': shared,
                'notice': None if shared in (None, True) else WAITS}

    @staticmethod
    def _ended(run: _Run) -> bool:
        deadline = time.monotonic() + STOP_WAIT
        while True:
            thread = run.thread
            alive = (thread is not None and thread.is_alive()
                     and thread is not threading.current_thread())
            if not alive and not run.busy:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def _let_go(self, root: Path, keep: bool = False) -> None:
        """Forget a deck that is gone. Call it holding `files`."""
        run = self._run(root)
        run.gone = True
        run.stop.set()
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
        jobs = agents.staging()
        for old in jobs.iterdir() if jobs.is_dir() else ():
            if old.name.startswith(f'{root.name}--'):
                shutil.rmtree(old, ignore_errors=True)
        for name in ('notified', 'taken'):
            kept = team.kept(name)
            if kept.pop(str(root), None) is not None:
                team.keep(name, kept)
        home.forget(root)
        with self._lock:
            self._runs.pop(str(root), None)
        self._clash.pop(root.name, None)
        self._moved.pop(root.name, None)
        self._as_of = {key: value for key, value in self._as_of.items()
                       if key[1] != str(root)}

    # --- bringing a deck in ------------------------------------------------------------------

    def bring(self, path) -> dict:
        """Copy a deck made elsewhere, such as in a conversation, into the workspace under
        the name its title gives, take it, and commit. The folder it came from is only
        read. Returns {'path', 'id'}; the run carries on from what its record says."""
        space, chosen, top = self.space(), settings.load(), Path(path)
        gitstate.identity(space.repo)
        if top == space.root or space.root.resolve() in top.resolve().parents:
            raise WorkspaceError('This deck is already in the workspace.')
        try:
            record = decks.read_run(top)
            title, form = record['title'], record['form']
            if not isinstance(title, str) or not isinstance(form, dict):
                raise TypeError
        except (OSError, ValueError, KeyError, TypeError):
            raise WorkspaceError("This deck's run record cannot be read, so it cannot be "
                                 'brought into the workspace.') from None
        why = team.unacceptable(top)
        if why:
            raise WorkspaceError('This deck cannot be brought into the workspace. ' + why)
        with self.files:
            root = space.deck(decks.deck_id(space, title))
            try:
                team.copy_in(top, root)
                record = decks.read_run(root)
                record.update(id=root.name, driver=team.claim(space), halted=None,
                              question=None,
                              agent=record.get('agent') or chosen.agent,
                              model=record.get('model') or chosen.model,
                              limits={'step_seconds': chosen.step_seconds,
                                      'dollars': chosen.deck_dollars})
                record.setdefault('schema', decks.SCHEMA)
                record.setdefault('steps', {})
                self._store(root, record)
                self._commit(root, 'bring the deck in')
            except BaseException:  # a deck is brought in whole or not at all
                self._undo_start(space, root)
                raise
            self._claimed(root, space, NAME_TAKEN)
            home.remember(root, title)
        self.wake(root)
        return {'path': str(root), 'id': root.name}


# Which step's worker spoke last before each gate, for what the gate shows it said.
FED_BY = {gate: step for step, gate in FED.items()
          if step not in ('inventory', 'extract', 'patch', 'build-sections', 'build-repair')}
