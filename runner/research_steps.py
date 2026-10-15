"""Research for a deck: the plan a worker drafts, the questions harness-research is handed,
each question researched by a worker, and the report the person decides on.

What a caller needs to know
---------------------------
    class Engine(..., research_steps.Researching)   # the engine's research steps

- The plan is research/plan.json (and plan.md to read); the report research/report.md,
  written from each finding the person kept. harness-research keeps its own record in
  .harness-research/.
- Each question still to answer is researched by one worker, several at a time. A finding
  the worker tools accepted is recorded with harness-research at once. A question that fails
  ATTEMPTS times is left unanswered and named in the report; research that answered nothing
  stops the deck.
- Asking for changes at gate:research with questions marked to research again, or added,
  researches only those: each worker is told the line written against its question, or
  that the person added it, and their own words. A note alone researches again the
  questions it names by their IDs, and those not yet settled. A question the person left
  out is never researched again; a finding a changed plan lost always is.
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

from runner import briefs, documents, marks, stages, worker_tools
from runner import research as research_cli
from runner.jobs import Halted, Run, given_up, last_error, sha256_of, text_of, tries
from runner.steps import Work

BUSY_TRIES = 20         # times a finding is offered while another save holds the lock
PLAN = Path('research') / 'plan.json'
PLAN_MD = Path('research') / 'plan.md'
REPORT = Path('research') / 'report.md'
RECORD = Path('.harness-research') / 'research.json'
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
        """The report the person reads and the outline is drafted from: what the research
        settled and did not, what the person left out, then each finding kept, with its
        answer, what is not known and the passages it quotes."""
        items = self._findings_shown(root, record)
        left = [item for item in items if item['left_out']]
        kept = [item for item in items if not item['left_out']]
        total = len(kept)
        supported = sum(item['status'] == 'supported' for item in kept)
        lines = ['# Research report', '',
                 f"{supported} of {total} question{'' if total == 1 else 's'} "
                 f"{'has' if supported == 1 else 'have'} an answer the sources support."]
        unresolved = [item for item in kept if item['status'] in UNRESOLVED]
        unread = [item for item in kept if item['status'] == 'pending']
        if unresolved:
            lines += ['', f'Not settled ({len(unresolved)}):']
            lines += [f"- {item['id']}: {item['question']} ({item['status']})"
                      for item in unresolved]
        if unread:
            lines += ['', f'Not researched ({len(unread)}):']
            for item in unread:
                why = last_error(record, 'research:' + item['id']) or 'no reason was kept'
                lines.append(f"- {item['id']}: {item['question']} ({why})")
        if left:
            lines += ['', f'Left out by you ({len(left)}):']
            lines += [f"- {item['title']}" for item in left]
        for item in kept:
            if item['status'] == 'pending':
                continue
            lines += ['', f"## {item['title']} (`{item['id']}`)", '', item['question'], '',
                      f"Status: {item['status']}."]
            for said in (item['headline'], item['summary']):
                if said and said not in lines[-1]:
                    lines += ['', said]
            if item['limits']:
                lines += ['', f"Not known: {item['limits']}"]
            if item['sources']:
                lines += ['', 'Sources:']
                lines += [f"- {source['title'] or source['origin']} ({source['origin']}): "
                          f"\"{' '.join(source['quote'].split())}\""
                          for source in item['sources']]
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
        return {ident: self._status(results.get(ident)) for ident in self._questions(root)}

    @staticmethod
    def _status(result) -> str:
        """A kept finding's verdict, or 'pending' where it has none a person can read."""
        status = result.get('status') if isinstance(result, dict) else None
        return status if isinstance(status, str) and status else 'pending'

    def _findings_shown(self, root: Path, record: dict) -> list[dict]:
        """Each question of the plan with what the research found, for the page: its title,
        status, one-sentence answer, what is not known and the passages quoted. A finding
        kept before headlines were asked for is given its summary's first sentence."""
        found = home.read_json(root / RECORD, None)
        results = found.get('results') if isinstance(found, dict) else None
        results = results if isinstance(results, dict) else {}
        left = set((record.get('research') or {}).get('left_out') or ())
        shown = []
        for ident, question in self._questions(root).items():
            result = results.get(ident) if isinstance(results.get(ident), dict) else {}
            summary, limits = str(result.get('summary') or ''), str(result.get('limits') or '')
            headline = result.get('headline') if isinstance(result.get('headline'), str) else ''
            evidence = result.get('evidence')
            known = limits.strip().rstrip('.').lower() in ('', 'none')
            shown.append({
                'id': ident, 'title': marks.title(ident), 'question': question,
                'status': self._status(result),
                'headline': headline or marks.first_sentence(summary), 'summary': summary,
                'limits': '' if known else limits,
                'unknown': '' if known else marks.first_sentence(limits),
                'left_out': ident in left,
                'sources': [{'title': str(passage.get('title') or ''),
                             'origin': str(passage.get('origin') or ''),
                             'quote': str(passage.get('quote') or '')}
                            for passage in (evidence if isinstance(evidence, list) else ())
                            if isinstance(passage, dict)]})
        return shown

    @staticmethod
    def _named(ident: str, note: str | None) -> bool:
        return bool(note) and re.search(
            rf'(?<![a-z0-9-]){re.escape(ident)}(?![a-z0-9-])', note.lower()) is not None

    @staticmethod
    def _own_words(gate: dict) -> str | None:
        """What the person wrote themselves at gate:research. A request with marks keeps it
        as `free`, beside the note the runner wrote from the marks."""
        return gate.get('free') if isinstance(gate.get('again'), dict) else gate.get('note')

    @classmethod
    def _told(cls, gate: dict, ident: str) -> str | None:
        """What a worker researching `ident` is told the person said: that they added the
        question, or the line they wrote against it, then their own words; or their note
        at the gate."""
        if gate.get('state') != 'changes':
            return None
        again = gate.get('again')
        if isinstance(again, dict) and ident in again:
            line = again[ident] or ''
            if ident in (gate.get('added') or ()):
                said = 'The person added your question after reading the research.'
            else:
                said = ('The person asked for your question to be researched again'
                        + (f'. What they said about it:\n\n{line}' if line else '.'))
            if gate.get('free'):
                said += ('\n\nThey also wrote this, which may or may not be about your '
                         f"question:\n\n{gate['free']}")
            return said
        note = cls._own_words(gate)
        return ('The person looked at the research and asked for this, which may or may '
                f'not be about your question:\n\n{note}') if note else None

    def _research(self, root: Path, run: Run, step: stages.Step) -> None:
        """Hand the approved plan to harness-research, then research each question still
        to answer, several at a time. A question that fails three times is left for the
        report to name."""
        with self.files:
            record = self._load(root)
            handed, lost = record.get('research') or {}, []
            if not handed.get('run') or handed.get('plan') != sha256_of(root / PLAN):
                before = self._verdicts(root)
                status = self.research().plan(root, root / PLAN)
                # A finding harness-research did not keep for the changed plan, as when a
                # file it rests on changed, is researched again.
                lost = [ident for ident, verdict in self._verdicts(root).items()
                        if verdict == 'pending' and before.get(ident, 'pending') != 'pending']
                # What the person left out stays with a changed plan.
                record['research'] = {**handed, 'run': status.get('run'),
                                      'plan': sha256_of(root / PLAN)}
                self._store(root, record)
                self._commit(root, 'hand the approved questions to research')
            gate = record['gates'].get('gate:research') or {}
            # Two kinds of `again`: the gate's is what the person marked; `research.again`
            # is the runner's own list of the questions this request still has to research.
            asked = record['research'].get('again')
            if gate.get('state') == 'changes' and (asked or {}).get('at') != gate.get('at'):
                verdicts = self._verdicts(root)
                out = set(record['research'].get('left_out') or ())
                kept = [ident for ident in verdicts if ident not in out]
                marked = gate.get('again')
                if isinstance(marked, dict) and marked:
                    left = [ident for ident in kept if ident in marked]
                else:
                    # Only the person's own words are looked through for IDs: the note the
                    # runner wrote from marks names the questions left out.
                    said = self._own_words(gate)
                    left = [ident for ident in kept
                            if self._named(ident, said)
                            or verdicts[ident] in ('pending', *UNRESOLVED)] or kept
                left += [ident for ident in lost if ident in kept and ident not in left]
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

        def one(ident: str) -> None:
            if self._may_go(root):
                self._question(root, run, ident, self._told(gate, ident))

        if self.at_once <= 1 or len(todo) == 1:
            for ident in todo:
                one(ident)
            return
        with ThreadPoolExecutor(max_workers=self.at_once) as pool:
            for pending in [pool.submit(contextvars.copy_context().run, one, ident)
                            for ident in todo]:
                pending.result()

    def _question(self, root: Path, run: Run, ident: str, told: str | None) -> None:
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
        if told:
            task += f'\n\n{told}'
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
                again = (record.get('research') or {}).get('again') or {}
                if ident in again.get('left', []):
                    again['left'].remove(ident)
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

    def _drop_questions(self, root: Path, record: dict, dropped) -> None:
        """Take the questions the person dropped out of the plan, as they asked, with no
        worker. A plan is never left with none."""
        plan = home.read_json(root / PLAN, None)
        items = plan.get('items') if isinstance(plan, dict) else None
        if not isinstance(items, list):
            raise WorkspaceError('There is no research plan to drop a question from.')
        dropped = set(dropped)
        kept = [item for item in items
                if not (isinstance(item, dict) and item.get('id') in dropped)]
        if not kept:
            raise WorkspaceError(marks.ALL_DROPPED)
        self._keep_plan(root, record, json.dumps({**plan, 'items': kept}, indent=2,
                                                 ensure_ascii=False))

    def _add_questions(self, root: Path, record: dict, texts) -> list[str]:
        """Add the questions the person wrote to the plan, as they wrote them and with no
        search words. Returns their IDs. A plan that would be refused is not written."""
        if not texts:
            return []
        plan = home.read_json(root / PLAN, None)
        if not isinstance(plan, dict) or not isinstance(plan.get('items'), list):
            raise WorkspaceError('There is no research plan to add a question to.')
        if len(plan['items']) + len(texts) > worker_tools.QUESTIONS:
            raise WorkspaceError(f'A plan holds at most {worker_tools.QUESTIONS} '
                                 'questions.')
        taken = [item.get('id') for item in plan['items'] if isinstance(item, dict)]
        added = []
        for text in texts:
            ident = marks.new_id(text, taken + added)
            # Shaped as the plan's checks shape every question. The others are written back
            # as they were, so harness-research keeps their findings.
            plan['items'].append({'id': ident, 'question': text, 'public_query': None,
                                  'claim': None})
            added.append(ident)
        checked = worker_tools.check_research_plan(plan)
        if checked['status'] == 'failed':
            raise WorkspaceError(' '.join(checked['problems']))
        self._keep_plan(root, record, json.dumps(plan, indent=2, ensure_ascii=False))
        return added

    def _research_plan(self, root: Path, run: Run, step: stages.Step) -> None:
        self._agent(root, run, step,
                    lambda record, request, error: self._plan_work(root, record, request,
                                                                   error),
                    lambda record, handed: self._keep_plan(root, record,
                                                           self._text(handed, 'research-plan')),
                    'keep the research plan')

