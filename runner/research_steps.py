"""Research for a deck: the plan a worker drafts, the questions harness-research is handed,
each question researched by a worker, and the report the person decides on.

What a caller needs to know
---------------------------
    class Engine(..., research_steps.Researching)   # the engine's research steps

- The plan is research/plan.json (and plan.md to read); the report research/report.md.
  harness-research keeps its own record in .harness-research/.
- Each question still to answer is researched by one worker, several at a time. A finding
  the worker tools accepted is recorded with harness-research at once. A question that fails
  ATTEMPTS times is left unanswered and named in the report; research that answered nothing
  stops the deck.
- Asking for changes at gate:research researches again the questions the note names by
  their IDs, and those not yet settled.
- `Researching` is a part of the engine and is not used alone.
"""
from __future__ import annotations

import contextvars
import json
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import home
from workspace import WorkspaceError, write_atomic

from runner import briefs, documents, stages
from runner import research as research_cli
from runner.jobs import Halted, Run, given_up, last_error, sha256_of, text_of, tries
from runner.steps import Work

BUSY_TRIES = 20         # times a finding is offered while another save holds the lock
PLAN = Path('research') / 'plan.json'
PLAN_MD = Path('research') / 'plan.md'
REPORT = Path('research') / 'report.md'
RECORD = Path('.harness-research') / 'research.json'
HARNESS_REPORT = Path('.harness-research') / 'research-report.md'
UNRESOLVED = ('insufficient', 'unavailable')


class Researching:
    """The engine's research steps."""

    def _research_report(self, root: Path, run: Run, step: stages.Step) -> None:
        """Ask harness-research where the research stands and write the report for the
        gate. Research that answered nothing stops the deck."""
        clock = time.monotonic()
        with self.files:
            self.research().status(root)
            record = self._load(root)
            verdicts = self._verdicts(root)
            unread = [ident for ident, verdict in verdicts.items() if verdict == 'pending']
            if verdicts and len(unread) == len(verdicts):
                why = next((last_error(record, f'research:{ident}') for ident in unread
                            if last_error(record, f'research:{ident}')), '')
                self._problem(root, 'research', 'failed', (
                    f'None of the {len(verdicts)} research questions could be answered. '
                    f'{why}').strip(), 'The research plan you approved is kept.')
                raise Halted()
            write_atomic(root / REPORT, self._report_text(root, record, verdicts))
            (record.get('research') or {}).pop('again', None)
            self._done(root, step, clock, 'keep the research report', record)

    def _report_text(self, root: Path, record: dict, verdicts: dict) -> str:
        questions = self._questions(root)
        total = len(verdicts)
        supported = sum(verdict == 'supported' for verdict in verdicts.values())
        lines = ['# Research report', '',
                 f"{supported} of {total} question{'' if total == 1 else 's'} have an answer "
                 'the sources support.']
        unresolved = [ident for ident, verdict in verdicts.items() if verdict in UNRESOLVED]
        unread = [ident for ident, verdict in verdicts.items() if verdict == 'pending']
        if unresolved:
            lines += ['', f'Not settled ({len(unresolved)}):']
            lines += [f'- {ident}: {questions.get(ident, "")} ({verdicts[ident]})'
                      for ident in unresolved]
        if unread:
            lines += ['', f'Not researched ({len(unread)}):']
            lines += [f"- {ident}: {questions.get(ident, '')} "
                      f"({last_error(record, f'research:{ident}') or 'no reason was kept'})"
                      for ident in unread]
        said = text_of(root / HARNESS_REPORT)
        if said:
            lines += ['', '---', '', said.strip()]
        return '\n'.join(lines) + '\n'

    @staticmethod
    def _questions(root: Path) -> dict:
        plan = home.read_json(root / PLAN, None)
        items = plan.get('items') if isinstance(plan, dict) else None
        return {item['id']: str(item.get('question') or '') for item in items or ()
                if isinstance(item, dict) and isinstance(item.get('id'), str)}

    def _verdicts(self, root: Path) -> dict:
        """Each question of the approved plan, with its verdict or 'pending'."""
        record = home.read_json(root / RECORD, None)
        results = (record or {}).get('results') if isinstance(record, dict) else None
        results = results if isinstance(results, dict) else {}
        return {ident: (results.get(ident) or {}).get('status', 'pending')
                for ident in self._questions(root)}

    @staticmethod
    def _named(ident: str, note: str | None) -> bool:
        return bool(note) and re.search(
            rf'(?<![a-z0-9-]){re.escape(ident)}(?![a-z0-9-])', note.lower()) is not None

    def _research(self, root: Path, run: Run, step: stages.Step) -> None:
        """Hand the approved plan to harness-research, then research each question still
        to answer, several at a time. A question that fails three times is left for the
        report to name."""
        with self.files:
            record = self._load(root)
            handed = record.get('research') or {}
            if not handed.get('run') or handed.get('plan') != sha256_of(root / PLAN):
                status = self.research().plan(root, root / PLAN)
                record['research'] = {'run': status.get('run'), 'plan': sha256_of(root / PLAN)}
                self._store(root, record)
                self._commit(root, 'hand the approved questions to research')
            gate = record['gates'].get('gate:research') or {}
            asked = record['research'].get('again')
            if gate.get('state') == 'changes' and (asked or {}).get('at') != gate.get('at'):
                verdicts = self._verdicts(root)
                left = [ident for ident, verdict in verdicts.items()
                        if self._named(ident, gate.get('note'))
                        or verdict in ('pending', *UNRESOLVED)] or list(verdicts)
                record['research']['again'] = {'at': gate.get('at'), 'left': left}
                for ident in left:
                    tries(record, f'research:{ident}')
                    entry = record['steps'].get(f'research:{ident}')
                    if entry:
                        entry['failed'] = 0
                self._store(root, record)
            asked = record['research'].get('again')
            verdicts = self._verdicts(root)
            todo = [ident for ident in (asked['left'] if asked else
                                        [i for i, v in verdicts.items() if v == 'pending'])
                    if not given_up(record, f'research:{ident}')]
        if not todo:
            with self.files:
                self._done(root, step, time.monotonic(), 'every question is researched')
            return
        note = gate.get('note') if gate.get('state') == 'changes' else None

        def one(ident: str) -> None:
            if self._may_go(root):
                self._question(root, run, ident, note)

        if self.at_once <= 1 or len(todo) == 1:
            for ident in todo:
                one(ident)
            return
        with ThreadPoolExecutor(max_workers=self.at_once) as pool:
            for pending in [pool.submit(contextvars.copy_context().run, one, ident)
                            for ident in todo]:
                pending.result()

    def _question(self, root: Path, run: Run, ident: str, note: str | None) -> None:
        """One try at one research question. An accepted finding is recorded at once."""
        name = f'research:{ident}'
        record = self._load(root)
        question = self._questions(root).get(ident, '')
        plan = home.read_json(root / PLAN, {}) or {}
        query = next((item.get('public_query') for item in plan.get('items') or ()
                      if isinstance(item, dict) and item.get('id') == ident), None)
        offered = documents.sources(root)[1] if documents.listed(root) else []
        task = ('Research this question for a presentation.\n\n'
                f'Question ID: {ident}\nQuestion: {question}\n'
                + (f'Search words to start from: {query}\n' if query else '')
                + ('The documents the person supplied are saved for you already. Read them '
                   'as well as the web.\n' if offered else '')
                + f'\nThe presentation:\n{self._about(record)}')
        if note:
            task += ('\n\nThe person looked at the research and asked for this, which may or '
                     f'may not be about your question:\n\n{note}')
        error = last_error(record, name)
        if error:
            task += (f'\n\nAn earlier try at this job did not work: {error}\nTake care not to '
                     'end the same way.')
        work = Work(briefs.guidance('research-question'), task, 'research',
                           {'finding': ident, 'fetch': True, 'ask': False, 'sources': offered})
        outcome, handed, started_at, folder = self._job(root, run, name,
                                                        f'Researching the question {ident}',
                                                        work, deck=False)
        if outcome.reason == 'stopped':
            return self._stopped(root, name, outcome, started_at)
        if handed['finding'] is None:
            return self._failed(root, name, f'Research the question {ident}', outcome,
                                started_at, self._why_not(handed, outcome.detail),
                                question=True)
        refused = None
        with self.files:
            try:
                self._keep_sources(root, handed)
                self._record(root, ident, handed['finding'])
            except WorkspaceError as refusal:
                refused = str(refusal)
            else:
                record = self._load(root)
                self._tried(record, name, started_at, outcome.seconds, 'kept',
                            **self._cost(outcome))
                asked = (record.get('research') or {}).get('again') or {}
                if ident in asked.get('left', []):
                    asked['left'].remove(ident)
                self._store(root, record)
                self._commit(root, f'keep the finding for {ident}')
        if refused:
            return self._failed(root, name, f'Research the question {ident}', outcome,
                                started_at, refused, question=True)
        shutil.rmtree(folder, ignore_errors=True)

    @staticmethod
    def _keep_sources(root: Path, handed: dict) -> None:
        """Copy the sources a finding quotes into the deck's own sources folder, where
        harness-research reads them. They stay on this computer."""
        quoted = {passage.get('file') for passage in handed['finding'].get('evidence') or []}
        inside = (root / 'sources').resolve()
        for source in handed['sources']:
            if source.get('file') not in quoted:
                continue
            for name, path in ((source.get('file'), source.get('path')),
                               (source.get('original'), source.get('original_path'))):
                if not name or path is None:
                    continue
                target = (root / name).resolve()
                if inside not in target.parents or target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)

    def _record(self, root: Path, ident: str, finding: dict) -> None:
        handed_to = (self._load(root).get('research') or {}).get('run')
        for left in range(BUSY_TRIES, 0, -1):
            try:
                self.research().record(root, handed_to, ident, finding)
                return
            except research_cli.Refused as refusal:
                if not refusal.busy or left == 1:
                    raise
                time.sleep(0.25)

    @staticmethod
    def _about(record: dict) -> str:
        form = record.get('form') or {}
        return '\n'.join([f"Title: {record.get('title') or form.get('title')}",
                          f"Audience: {form.get('audience') or 'not given'}",
                          f"Goal: {form.get('goal') or 'not given'}",
                          f"Length: {form.get('minutes') or 'not given'} minutes"
                          if form.get('minutes') else 'Length: not given'])

    def _plan_work(self, root: Path, record: dict, request: dict | None,
                   error: str | None) -> Work:
        name = 'research-plan'
        listed = documents.sources(root)[0] if documents.listed(root) else []
        allowed = ('the public web, and these documents the person supplied. Ask what the '
                   'documents can answer as well as what the web can:\n'
                   + '\n'.join(f"- {source.get('title') or source.get('id')}"
                               for source in listed)) if listed else 'the public web.'
        task = ('Draft the research questions for this presentation.\n\n'
                f'{self._about(record)}\n'
                f'Sources that may be used: {allowed}\n\n'
                f'Hand the questions back with submit_artifact under the name "{name}".')
        earlier = text_of(root / PLAN)
        if request and request.get('note'):
            task += ('\n\nYou are revising an earlier draft. What the person asked for:\n\n'
                     f"{request['note']}")
            if earlier:
                task += f'\n\nThe earlier draft:\n\n{earlier}'
        if error:
            task += (f'\n\nAn earlier try at this job did not work: {error}\nTake care not to '
                     'end the same way.')
        prepared = {'inputs': {'intake': text_of(root / 'intake.md') or ''},
                    'artifacts': {name: {'kind': 'research-plan', 'scope': 'public-web',
                                         'sources': listed}},
                    'ask': True}
        return Work(briefs.guidance('research-plan'), task, 'write', prepared, name)

    @staticmethod
    def _keep_plan(root: Path, record: dict, text: str) -> None:
        write_atomic(root / PLAN, text if text.endswith('\n') else text + '\n')
        plan = json.loads(text)
        lines = ['# Research plan', '', str(plan.get('topic') or ''), '']
        for item in plan.get('items') or ():
            lines.append(f"- **{item.get('id')}**: {item.get('question')}"
                         + (f" (search: {item['public_query']})"
                            if item.get('public_query') else ''))
        write_atomic(root / PLAN_MD, '\n'.join(lines).rstrip() + '\n')

    def _research_plan(self, root: Path, run: Run, step: stages.Step) -> None:
        self._agent(root, run, step,
                    lambda record, request, error: self._plan_work(root, record, request,
                                                                   error),
                    lambda record, handed: self._keep_plan(root, record,
                                                           self._text(handed, 'research-plan')),
                    'keep the research plan')

