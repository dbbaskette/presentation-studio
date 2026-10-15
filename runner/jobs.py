"""One job for one worker, the tries at each step, and what a run record holds of them.

What a caller needs to know
---------------------------
    jobs.tries(record, 'outline')        # {'failed', 'tries', 'done'} of one step
    jobs.attempts(record)                # every try, or those at one step and its jobs
    jobs.spent(record)                   # (dollars, tokens) so far, where the agent said
    jobs.first(record)                   # the next step: the first that is not done
    jobs.Slots(limit)                    # decks take turns, as many at once as `limit()`
    jobs.Run()                           # what the engine holds of one deck while it serves
    class Engine(jobs.Jobs, ...)         # the engine's methods for jobs and their tries

- A step is done when its entry in run['steps'] says so; a gate once it is approved.
- One try at an agent step (`Jobs._agent`) is an empty job folder under `agents.staging()`,
  a brief, a worker and results taken only from what the worker tools accepted. It is tried
  up to ATTEMPTS times, with the reason for the last failure added to its task; then the
  deck stops and says what went wrong. An agent that cannot be used stops it at once. A
  worker's question stops the run until the person answers; the answers go into the task
  of the next try, and after QUESTIONS answers the worker may ask no more.
- A deck that has spent what it may stops and asks before the next worker starts.
- `Jobs` is a part of the engine and is not used alone: it reads and writes through the
  engine's `files`, `_load`, `_store`, `_commit`, `adapter` and `_look`.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import shutil
import threading
import time
from collections import deque
from dataclasses import replace
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import home
from workspace import WorkspaceError

from runner import agents, briefs, settings, stages, worker_tools

ATTEMPTS = 3            # tries at one step: the first, and two more with the reason added
QUESTIONS = 3           # questions the workers on one step may put to the person
LINES = 6               # the last things a worker did that the page is shown

# The gate each step feeds, so that a step run again for a person's request reads their note.
FED = {'classify': 'gate:classify', 'inventory': 'gate:classify',
       'research-plan': 'gate:research-plan', 'research': 'gate:research',
       'extract': 'gate:outline', 'outline': 'gate:outline', 'look': 'gate:look',
       'patch': 'gate:build', 'build-sections': 'gate:build', 'build-repair': 'gate:build'}
KEPT = ('Everything kept before this step is still here. Nothing from the tries that failed '
        'was kept.')
KEPT_SO_FAR = 'Everything kept so far is still here.'


# --- what a run record holds ----------------------------------------------------------------

def tries(record: dict | None, step: str) -> dict:
    """What a run record holds for one step: its tries, how many have failed in a row since
    the last one that worked or the last fresh start, and whether it is done."""
    kept = ((record or {}).get('steps') or {}).get(step)
    return kept if isinstance(kept, dict) else {'failed': 0, 'tries': []}


def attempts(record: dict, step: str | None = None) -> list[dict]:
    """Every try the record holds, or the tries at one step and the jobs under it."""
    return [attempt for name, entry in (record.get('steps') or {}).items()
            if isinstance(entry, dict)
            and (step is None or name == step or name.startswith(f'{step}:'))
            for attempt in entry.get('tries') or []]


def spent(record: dict) -> tuple[float | None, int | None]:
    """What a deck has cost so far, where its agent said: dollars and tokens."""
    tried = attempts(record)
    dollars = [attempt['dollars'] for attempt in tried if attempt.get('dollars') is not None]
    tokens = [attempt['tokens'] for attempt in tried if attempt.get('tokens') is not None]
    return (round(sum(dollars), 4) if dollars else None, sum(tokens) if tokens else None)


def given_up(record: dict, step: str) -> bool:
    """True when a step has failed as often as it may."""
    return tries(record, step).get('failed', 0) >= ATTEMPTS


def last_error(record: dict, step: str) -> str | None:
    """Why the last try at a step failed, while it has failed since it last worked."""
    entry = tries(record, step)
    tried = [attempt for attempt in entry.get('tries') or [] if attempt.get('error')]
    return tried[-1]['error'] if tried and entry.get('failed') else None


def folder_name(step: str) -> str:
    """A step's name as part of a folder's."""
    return re.sub(r'[^a-z0-9]+', '-', step.lower()).strip('-')


def done(record: dict, step: stages.Step) -> bool:
    """Whether one step of a deck is done: a gate once it is approved."""
    if step.kind == 'gate':
        return ((record.get('gates') or {}).get(step.name) or {}).get('state') == 'approved'
    return bool(tries(record, step.name).get('done'))


def first(record: dict) -> stages.Step | None:
    """The first step of a deck that is not done: what comes next. None once the deck is
    delivered. Rehearsing is never next."""
    return next((step for step in stages.steps(record)
                 if step.name != 'rehearse' and not done(record, step)), None)


def gate_state(record: dict, gate: str) -> str | None:
    return ((record.get('gates') or {}).get(gate) or {}).get('state')


class Gone(WorkspaceError):
    """A deck stopped being this computer's while a step of it was in hand."""


class Halted(Exception):
    """A step stopped the deck and has said why: nothing more is done now."""


class Slots:
    """How many decks may work at once, and whose turn is next: they take turns in the order
    they asked. The limit is read as each one starts to wait, and again on `renew`."""

    def __init__(self, limit):
        self.read, self.limit, self.used = limit, None, 0
        self.changed = threading.Condition()
        self.waiting: list = []

    def take(self, closing, who=None) -> bool:
        who = object() if who is None else who
        with self.changed:
            self.waiting.append(who)
            self.limit = self.read()
            try:
                while self.used >= self.limit or self.waiting[0] is not who:
                    if closing():
                        return False
                    self.changed.wait(0.5)
                self.used += 1
                return True
            finally:
                self.waiting.remove(who)
                self.changed.notify_all()

    def ahead(self, who) -> int | None:
        with self.changed:
            return next((place for place, waiting in enumerate(self.waiting)
                         if waiting is who), None)

    def give_back(self) -> None:
        with self.changed:
            self.used -= 1
            self.changed.notify_all()

    def renew(self) -> None:
        with self.changed:
            self.limit = self.read()
            self.changed.notify_all()


class Run:
    """What the engine holds for one deck while it serves: nothing needed to resume it."""

    def __init__(self):
        self.thread: threading.Thread | None = None
        self.again = self.queued = self.busy = False
        self.gone = False   # it stopped being this computer's: nothing more is written
        self.stop = threading.Event()
        self.workers: dict[str, dict] = {}


def sha256_of(path: Path) -> str | None:
    """A file's SHA-256, or None when it cannot be read."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def text_of(path: Path) -> str | None:
    """A file's text, or None when it cannot be read."""
    try:
        return Path(path).read_text(encoding='utf-8')
    except OSError:
        return None


class Jobs:
    """The engine's part that runs workers: one job, its tries, its questions and limits."""

    def _problem(self, root: Path, step: str | None, state: str, what: str, kept: str,
                 action: str | None = 'retry', limit: bool = False) -> None:
        """Stop a deck in a state that says what went wrong and offers one action. `limit`
        says it stopped because it spent what it may."""
        with self.files:
            record = self._load(root)
            record['halted'] = {'state': state, 'step': step, 'why': what, 'kept': kept,
                                'action': action, 'at': home.now(),
                                **({'limit': True} if limit else {})}
            self._store(root, record)
            self._commit(root, f'stop. {what[:160].rstrip()}')

    def _tried(self, record: dict, step: str, started_at: str, seconds: float, outcome: str,
               error: str | None = None, dollars: float | None = None,
               tokens: int | None = None) -> dict:
        """Note one try at a step. A try that worked clears the count of failures."""
        entry = record['steps'].setdefault(step, {'failed': 0, 'tries': [], 'done': False})
        entry.setdefault('tries', [])
        entry['tries'].append({
            'started_at': started_at, 'ended_at': home.now(), 'seconds': round(seconds, 1),
            'dollars': dollars, 'tokens': tokens, 'outcome': outcome, 'error': error})
        if outcome == 'kept':
            entry['failed'] = 0
        elif outcome == 'failed':
            entry['failed'] = entry.get('failed', 0) + 1
        return entry

    @staticmethod
    def _finish(record: dict, step: str) -> None:
        entry = record['steps'].setdefault(step, {'failed': 0, 'tries': []})
        entry.update(done=True, at=home.now())

    def _request(self, record: dict, step: str) -> dict | None:
        """The person's request a step is run again for: the note at the gate it feeds,
        while that gate asks for changes."""
        gate = (record.get('gates') or {}).get(FED.get(step, '')) or {}
        if gate.get('state') == 'changes' and gate.get('note'):
            return {'note': gate['note'], 'at': gate.get('at')}
        return None

    def _agent(self, root: Path, run: Run, step: stages.Step, make, keep, what: str,
               name: str | None = None, label: str | None = None) -> bool:
        """One try at a job for a worker. `make(record, request, error)` returns its Work;
        `keep(record, handed)` keeps what it handed back, holding `files`. `name` is the
        record's name for the job when it is one of several under a step. Returns True when
        something was kept."""
        if not self._may_go(root):
            raise Halted()
        name = name or step.name
        record = self._load(root)
        request = self._request(record, step.name)
        work = make(record, request, last_error(record, name))
        answered = record['answers'].get(name) or []
        if answered:
            asked = '\n\n'.join(f"Question: {item['question']}\nAnswer: {item['answer']}"
                                for item in answered)
            work = replace(work, task=work.task + '\n\nA worker on this job asked the person '
                           f'before. Do not ask these again:\n\n{asked}')
        if work.prepared.get('ask', True) and len(answered) >= QUESTIONS:
            work = replace(work, prepared={**work.prepared, 'ask': False})
        if request:
            work = replace(work, guidance=work.guidance + '\n\n'
                           + briefs.guidance('change-request'))
        outcome, handed, started_at, folder = self._job(root, run, name,
                                                        label or step.doing, work)
        if outcome.reason == 'stopped':
            self._stopped(root, name, outcome, started_at)
            raise Halted()
        kept = handed['assessment'] if 'review' in work.prepared \
            else handed['artifacts'].get(work.name)
        if kept is not None:
            with self.files:
                record = self._load(root)
                keep(record, handed)
                record = self._load(root)
                self._tried(record, name, started_at, outcome.seconds, 'kept',
                            **self._cost(outcome))
                if handed.get('review'):
                    record['said'][name] = handed['review'].strip()
                record['answers'].pop(name, None)
                if name == step.name:
                    self._finish(record, step.name)
                self._store(root, record)
                self._commit(root, what)
            shutil.rmtree(folder, ignore_errors=True)
            return True
        if handed['question']:
            with self.files:
                record = self._load(root)
                self._tried(record, name, started_at, outcome.seconds, 'question',
                            **self._cost(outcome))
                record['question'] = {
                    'id': secrets.token_hex(6), 'step': name, 'text': handed['question'],
                    'from': f'The worker {step.doing[0].lower()}{step.doing[1:]}',
                    'at': home.now()}
                self._store(root, record)
                self._commit(root, f'a worker asks a question: {step.label}')
            raise Halted()
        self._failed(root, name, label or step.label, outcome, started_at,
                     self._why_not(handed, outcome.detail))
        return False

    @staticmethod
    def _text(handed: dict, name: str) -> str:
        return handed['artifacts'][name]['text']

    def _left(self, record: dict) -> float:
        dollars = spent(record)[0] or 0.0
        limit = (record.get('limits') or {}).get('dollars')
        if limit is None:
            limit = settings.load().deck_dollars
        return round(limit + record.get('cleared', 0.0) - dollars, 4)

    def _may_go(self, root: Path) -> bool:
        """Whether a worker may start now. Stops the deck, and asks, once it has spent what
        it may."""
        with self.files:
            record = self._load(root)
            if self._closing or self._resting(record):
                return False
            if self._left(record) > 0:
                return True
            dollars = spent(record)[0] or 0.0
            limit = (record.get('limits') or {}).get('dollars') \
                or settings.load().deck_dollars
            self._problem(root, None, 'stopped', (
                f'This deck has spent ${dollars:,.2f}. It stops and asks each time it has spent '
                f'another ${limit:,.2f}.'), 'Everything made so far is kept.', 'resume',
                limit=True)
            return False

    def _folder(self, root: Path, name: str, number: int) -> Path:
        base, stem = agents.staging(), f'{root.name}--{folder_name(name)}-'
        left = re.compile(re.escape(stem) + r'\d+-[0-9a-f]{6}')
        for old in base.iterdir() if base.is_dir() else ():
            if left.fullmatch(old.name):
                shutil.rmtree(old, ignore_errors=True)
        return base / f'{stem}{number}-{secrets.token_hex(3)}'

    def _job(self, root: Path, run: Run, name: str, doing: str, work, deck: bool = True):
        """Run one worker on one job. Returns how the agent ended, what the worker tools
        accepted from it, when it started and the job's folder."""
        record = self._load(root)
        number = len(tries(record, name).get('tries') or []) + 1
        folder = self._folder(root, name, number)
        runtimes = {key: value for key, value in self._look()['runtimes'].items() if value} \
            if deck else {}
        worker_tools.prepare(folder, **{**work.prepared, 'runtimes': runtimes})
        limits = record.get('limits') or {}
        job = agents.Job(work.guidance, work.task, folder, work.profile,
                         tuple(worker_tools.command(folder)),
                         agents.Limits(int(limits.get('step_seconds')
                                           or settings.load().step_seconds),
                                       max(0.01, self._left(record))),
                         record.get('model'), record.get('level_of_effort'))
        lines, started_at, clock = deque(maxlen=LINES), home.now(), time.monotonic()
        with self._lock:
            run.workers[name] = {'label': doing, 'started_at': started_at, 'lines': lines,
                                 'folder': folder}
        try:
            outcome = self.adapter(record.get('agent') or settings.load().agent).run(
                job, activity=lines.append, stop=run.stop)
        except WorkspaceError as refusal:  # a job that was wrong before it started
            outcome = agents.Outcome(False, 'failed', str(refusal))
        finally:
            with self._lock:
                run.workers.pop(name, None)
        if run.stop.is_set() and outcome.reason != 'stopped':
            outcome = replace(outcome, finished=False, reason='stopped')
        if not outcome.seconds:
            outcome = replace(outcome, seconds=round(time.monotonic() - clock, 1))
        return outcome, worker_tools.collect(folder), started_at, folder

    @staticmethod
    def _cost(outcome: agents.Outcome) -> dict:
        tokens = outcome.tokens or {}
        counted = (tokens.get('input') or 0) + (tokens.get('output') or 0)
        return {'dollars': outcome.cost, 'tokens': counted if outcome.tokens else None}

    @staticmethod
    def _why_not(handed: dict, said: str) -> str:
        refused = [problem for found in handed['problems'].values() for problem in found]
        if refused:
            return ('What it handed back did not pass the checks: ' + ' '.join(refused[:3])
                    + (' And more.' if len(refused) > 3 else ''))
        return said or 'It ended without handing anything back.'

    def _failed(self, root: Path, name: str, label: str, outcome: agents.Outcome,
                started_at: str, detail: str, question: bool = False) -> None:
        """Note a try that did not work. After the last one a step may have, or when the
        agent cannot be used at all, the deck stops and says so."""
        with self.files:
            record = self._load(root)
            entry = self._tried(record, name, started_at, outcome.seconds, 'failed', detail,
                                **self._cost(outcome))
            self._store(root, record)
            self._commit(root, f'a try at this step did not work: {label}')
        step = name.partition(':')[0]
        if outcome.reason == 'unavailable':
            self._problem(root, step, 'failed',
                          f"{self._title(record.get('agent'))} could not be used. {detail}",
                          KEPT)
        elif not question and entry['failed'] >= ATTEMPTS:
            self._problem(root, step, 'failed', (
                f'This step did not work in {ATTEMPTS} tries: {label}. The last one: '
                f'{detail}'), KEPT)

    def _title(self, name: str | None) -> str:
        try:
            return getattr(self.adapter(name or ''), 'title', name)
        except WorkspaceError:
            return name or 'The agent'

    def _stopped(self, root: Path, name: str, outcome: agents.Outcome,
                 started_at: str) -> None:
        with self.files:
            record = self._load(root)
            self._tried(record, name, started_at, outcome.seconds, 'stopped',
                        **self._cost(outcome))
            self._store(root, record)
            self._commit(root, f'this step was stopped: {name}')

    @staticmethod
    def _fresh(record: dict, step: str | None) -> None:
        """Let a step, and the jobs under it, be tried from the start again."""
        for name, entry in (record.get('steps') or {}).items():
            if isinstance(entry, dict) and (step is None or name == step
                                            or name.startswith(f'{step}:')):
                entry['failed'] = 0

