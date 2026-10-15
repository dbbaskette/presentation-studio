# Reviewing Stops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a person judge the research plan, the research findings and the outline item by item: what needs them first, marks on each item, and one button that says what it will do.

**Architecture:** A new pure module, `runner/marks.py`, checks what the page sends with a decision and writes the note a worker reads. The engine applies marks that need no worker (drops, leave-outs, outline edits) itself and reopens the stop for the rest, and the research steps learn to research only the marked questions and to write the report from each question's data. Keeping findings when a question is added, and a one-sentence headline per finding, are harness-research's (its plan `~/projects/harness-research-skill/docs/superpowers/plans/2026-10-15-keep-findings-and-headlines.md`, released as 0.8.1); this plan pins that release first. The page draws the three stops on one shared review component in `app.js`.

**Prerequisite:** harness-research 0.8.1 is released: tag `v0.8.1` at merge commit `d58d20dbbd0a51173cd122f223351eea66168cb0` ([dbbaskette/harness-research-skill#8](https://github.com/dbbaskette/harness-research-skill/pull/8)). Task 0 pins it. Its guidance's `minimumRuntime` is 0.8.1, so a computer with harness-research 0.8.0 installed must update it ("Update the skills" on the page, once this is pinned) before refreshed guidance works there.

**Tech Stack:** Python 3.11 standard library (runner), vanilla JavaScript (page, `skills/presentation-studio/scripts/desk/app.js`), `unittest`, and the Node page harness (`tests/page_harness.js`).

**Spec:** `docs/superpowers/specs/2026-10-15-reviewing-stops-design.md`.

**Branch:** `claude/reviewing-stops` (cut from `claude/lucid-heisenberg-725224`, which is pull request #5).

---

## Working agreements that apply (from `AGENTS.md`)

- Standard library only; no build step. Tests use temporary directories and never the network.
- Words a person reads never say "artifact", "stale" or "lineage", and no tracked file names a real brand (`tests/test_no_brand_named.py`).
- Run the targeted tests at each task; run the whole suite once at the end: `python3 scripts/ci/run_tests.py`.
- One module or class: `python3 scripts/ci/run_tests.py test_marks` or `python3 scripts/ci/run_tests.py test_engine.ResearchTests`.

## File structure

| File | Change | Responsibility |
| --- | --- | --- |
| `installer/companions.json` | Modify (by `install.sh pin`) | harness-research pinned at 0.8.1 |
| `runner/research.py` | Modify | `record` hands harness-research the finding's headline |
| `tests/stand_ins/research.py` | Modify | The stand-in keeps unchanged findings across a plan change and takes a headline, as 0.8.1 does |
| `runner/marks.py` | Create | Check the marks sent with a decision at a reviewed stop; write the note a worker reads; titles and IDs for questions |
| `tests/test_marks.py` | Create | Unit tests for `marks` |
| `runner/worker_tools.py` | Modify | `submit_finding` takes a required `headline`; its tool description says so |
| `runner/briefs/research-question.md` | Modify | Tell the research worker to give a headline |
| `runner/research_steps.py` | Modify | Drop and add questions; write the report from each question's data, without what was left out; research only marked questions with their lines; the per-item research view |
| `runner/engine.py` | Modify | `decide` checks and applies marks; research and outline views list items |
| `runner/page.py` | Modify | `/api/decide` takes changes with marks and no note |
| `skills/presentation-studio/scripts/desk/app.js` | Modify | The review component; the research plan, research and outline panels; the decision button |
| `skills/presentation-studio/scripts/desk/deck.css` | Modify | Styles for the review component |
| Tests | Modify | `runner_support.py`, `test_runner_worker_tools.py`, `test_runner_research.py`, `test_runner_documents.py`, `test_engine.py`, `test_runner_page.py`, `test_desk.py` |
| `README.md`, `docs/runner.md`, the spec | Modify | Say how the stops work now |

---

### Task 0: Use harness-research 0.8.1

harness-research 0.8.1 keeps the findings of unchanged questions when a plan changes (and lists them in `carried`), and keeps an optional one-line `headline` with a finding, shown as `Answer:` in its report. This task pins it, hands it the headline, and makes the tests' stand-in behave the same. What the stand-in must match, as released:

- `carried` is `[]` when an identical plan resumes its run, although that run's findings remain; compare `run` to tell a resume from a new run. `status` returns no `carried`.
- A question is compared as a whole object, so `claim: null` and a missing `claim` key differ. The pinned inputs include claim files and selected source files, with their contents.
- `headline` is optional: omit the key when there is none, because `null` is refused. The 300-character limit is checked before trimming, and only `\r` and `\n` count as line breaks. The headline is kept only in `research.json` (`results[id].headline`) and the report (`Answer:`), never in the JSON `plan`, `record` or `status` return.

**Files:**
- Modify: `installer/companions.json` (by the pin command)
- Modify: `runner/research.py` (`Research.record`, `Research.plan` docstring)
- Modify: `tests/stand_ins/research.py` (`_plan`, `_record`, `_render`, new `_kept`)
- Test: `tests/test_runner_research.py` (`StandInTests`)

- [ ] **Step 1: Pin the release**

Run (it reads the tag from GitHub, so it needs network access): `sh installer/install.sh pin harness-research --revision v0.8.1`
Expected: `installer/companions.json` names harness-research at version 0.8.1 with a new commit and file digests. Read the diff between v0.8.0 and v0.8.1 before committing, as `docs/development.md` asks.

- [ ] **Step 2: Write the failing stand-in tests**

In `tests/test_runner_research.py`, replace `test_the_same_plan_continues_its_run_and_a_changed_one_starts_another` with:

```python
    def test_the_same_plan_continues_its_run_and_a_changed_one_keeps_unchanged_findings(self):
        run = self.planned()
        self.research.record(self.root, run, 'instance-min', self.finding())
        again = self.research.plan(self.root, self.plan_file)
        self.assertEqual((again['run'], again['completed'], again['carried']), (run, 1, []))
        longer = {**PLAN, 'items': PLAN['items'] + [{'id': 'rollback', 'question': 'How is a '
                                                     'failed restart rolled back?'}]}
        self.plan_file.write_text(json.dumps(longer))
        changed = self.research.plan(self.root, self.plan_file)
        self.assertNotEqual(changed['run'], run)
        self.assertEqual((changed['completed'], changed['total'], changed['carried']),
                         (1, 3, ['instance-min']))
        self.plan_file.write_text(json.dumps({**longer, 'topic': 'Another topic'}))
        retitled = self.research.plan(self.root, self.plan_file)
        self.assertEqual((retitled['completed'], retitled['carried']), (0, []))

    def test_a_finding_keeps_its_headline_and_the_report_gives_it(self):
        run = self.planned()
        status = self.research.record(self.root, run, 'instance-min',
                                      self.finding(headline='Two instances keep capacity.'))
        self.assertEqual(research_record(self.root)['results']['instance-min']['headline'],
                         'Two instances keep capacity.')
        self.assertIn('Answer: Two instances keep capacity.',
                      Path(status['report']).read_text())
        for headline in ('Two\nlines', '   ', 'x' * 301):
            with self.subTest(headline=headline):
                self.assertEqual(
                    self.refusal(self.research.record, self.root, run, 'health-checks',
                                 self.finding(headline=headline)),
                    'Headline requires one nonempty line (maximum 300 characters).')
        self.assertNotIn('headline', status)
        # harness-research refuses a null headline, so a finding without one is handed over
        # without the key.
        self.research.record(self.root, run, 'health-checks', self.finding(headline=None))
        self.assertNotIn('headline', research_record(self.root)['results']['health-checks'])
```

- [ ] **Step 3: Run them to see them fail**

Run: `python3 scripts/ci/run_tests.py test_runner_research.StandInTests`
Expected: FAIL: `KeyError: 'carried'`.

- [ ] **Step 4: Hand the headline over**

In `runner/research.py`, `Research.record`, after the line that builds `wanted`, add:

```python
        if finding.get('headline'):
            wanted['headline'] = finding['headline']
```

and change the `plan` docstring to:

```python
        """Hand over an approved plan. The same plan again continues its run; a changed
        one starts a new run that keeps the findings of unchanged questions, listed in
        `carried`, when its topic, scope and sources are unchanged. `allow_web` permits a
        plan that widens supplied-only research to the public web."""
```

In the module docstring's list of what every call returns, add `carried` after `total`, and say harness-research 0.8.1 or newer is needed:

```python
- Every call returns the command's own JSON: `run`, `status` (`not-started`,
  `in-progress`, `complete` or `stale`), `pending`, `unresolved`, `staleItems`,
  `completed`, `total`, `sourceGaps`, and where the record and the `report` are; `plan`
  also returns `carried`. It needs harness-research 0.8.1 or newer.
```

- [ ] **Step 5: Teach the stand-in**

In `tests/stand_ins/research.py`, `StandIn._plan`, replace the last lines (from `if old and old['run'] == run:`) with:

```python
        if old and old['run'] == run:
            return {**self._status(project), 'carried': []}
        kept = self._kept(old, plan, pins) if old else {}
        status = self._save(project, {
            'schema': 1, 'owner': 'harness-research', 'run': run, **plan, 'inputs': pins,
            'results': kept, 'created_at': _now()})
        return {**status, 'carried': [item['id'] for item in items if item['id'] in kept]}

    @staticmethod
    def _kept(old: dict, plan: dict, pins: dict) -> dict:
        """As the real command keeps them: the findings of questions defined as before,
        when the topic, purpose, scope, selected sources and inputs are unchanged."""
        same = all(old.get(key) == plan.get(key) for key in ('topic', 'purpose', 'scope')) \
            and old.get('sources') == plan.get('sources') and old.get('inputs') == pins
        if not same:
            return {}
        before = {item['id']: item for item in old['items']}
        return {item['id']: old['results'][item['id']] for item in plan['items']
                if before.get(item['id']) == item and item['id'] in old['results']}
```

In `StandIn._record`, after `_text(supplied.get('limits'), 'Coverage limits')` add:

```python
        headline = supplied.get('headline')
        if 'headline' in supplied and (not isinstance(headline, str) or not headline.strip()
                                       or len(headline) > 300
                                       or re.search(r'[\r\n]', headline)):
            raise _Said('Headline requires one nonempty line (maximum 300 characters).')
```

and replace the line that stores the result with:

```python
        value['results'][ident] = {
            'status': supplied['status'],
            **({'headline': headline.strip()} if 'headline' in supplied else {}),
            'summary': supplied['summary'], 'limits': supplied['limits'],
            'evidence': evidence, 'checked_at': _now()}
```

In `StandIn._render`, replace `lines += [finding['summary'], '',` with:

```python
                if finding.get('headline'):
                    lines += [f"Answer: {finding['headline']}", '']
                lines += [finding['summary'], '',
```

(keeping the rest of that statement as it is).

- [ ] **Step 6: Run the tests**

Run: `python3 scripts/ci/run_tests.py test_runner_research test_engine test_flow_routes`
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add installer/companions.json runner/research.py tests/stand_ins/research.py tests/test_runner_research.py
git commit -m "Use harness-research 0.8.1: findings kept across a plan change, and headlines"
```

---

### Task 1: The marks module

**Files:**
- Create: `runner/marks.py`
- Test: `tests/test_marks.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_marks.py`:

```python
"""What a person marks at a stop reviewed item by item: checked, and the note it becomes."""
import unittest

import helpers  # noqa: F401
from workspace import WorkspaceError

from runner import marks

QUESTIONS = ['instance-min', 'health-checks']
SLIDES = ['cover-restarts', 'what-it-does']


class CheckTests(unittest.TestCase):
    def test_a_stop_not_reviewed_item_by_item_has_no_marks(self):
        self.assertEqual(marks.check('gate:build', 'approve', {'slides': [2]}, []), {})

    def test_plan_marks_are_cleaned(self):
        marked = marks.check('gate:research-plan', 'changes', {
            'dropped': ['health-checks', 'health-checks'],
            'reword': {'instance-min': '  How many   instances? '},
            'add': ['  What does it cost? ']}, QUESTIONS)
        self.assertEqual(marked, {'dropped': ['health-checks'],
                                  'reword': {'instance-min': 'How many instances?'},
                                  'add': ['What does it cost?']})

    def test_plan_refusals(self):
        for extra, said in (
                ({'dropped': ['nowhere']}, 'There is no question nowhere here.'),
                ({'dropped': QUESTIONS}, marks.ALL_DROPPED),
                ({'reword': {'instance-min': '  '}}, 'Say what should change for instance-min.'),
                ({'dropped': ['instance-min'], 'reword': {'instance-min': 'Again?'}},
                 'instance-min is both dropped and reworded'),
                ({'add': ['']}, 'A question to add is empty.'),
                ({'add': ['Why?'] * 11}, 'Add at most 10 questions at once.'),
                ({'dropped': 'health-checks'}, 'Name each question by its ID.')):
            with self.subTest(extra=extra):
                with self.assertRaises(WorkspaceError) as caught:
                    marks.check('gate:research-plan', 'changes', extra, QUESTIONS)
                self.assertIn(said, str(caught.exception))

    def test_only_drops_go_with_approve_at_the_plan(self):
        self.assertEqual(marks.check('gate:research-plan', 'approve',
                                     {'dropped': ['health-checks']}, QUESTIONS),
                         {'dropped': ['health-checks']})
        with self.assertRaises(WorkspaceError) as caught:
            marks.check('gate:research-plan', 'approve', {'add': ['Why?']}, QUESTIONS)
        self.assertEqual(str(caught.exception), marks.AS_CHANGES)

    def test_research_marks_keep_an_empty_left_out_and_an_empty_line(self):
        marked = marks.check('gate:research', 'changes',
                             {'left_out': [], 'again': {'health-checks': ''}}, QUESTIONS)
        self.assertEqual(marked, {'left_out': [], 'again': {'health-checks': ''}})
        self.assertEqual(marks.check('gate:research', 'approve', {}, QUESTIONS), {})

    def test_research_refusals(self):
        for extra, said in (
                ({'left_out': QUESTIONS}, marks.ALL_LEFT_OUT),
                ({'left_out': ['instance-min'], 'again': {'instance-min': ''}},
                 'instance-min is both left out and researched again'),
                ({'again': {'nowhere': ''}}, 'There is no question nowhere here.')):
            with self.subTest(extra=extra):
                with self.assertRaises(WorkspaceError) as caught:
                    marks.check('gate:research', 'changes', extra, QUESTIONS)
                self.assertIn(said, str(caught.exception))
        with self.assertRaises(WorkspaceError):
            marks.check('gate:research', 'approve', {'again': {'instance-min': ''}}, QUESTIONS)

    def test_outline_marks_need_a_line_and_go_as_changes(self):
        self.assertEqual(marks.check('gate:outline', 'changes',
                                     {'slides': {'what-it-does': 'Split it.'}}, SLIDES),
                         {'slides': {'what-it-does': 'Split it.'}})
        for extra in ({'slides': {'what-it-does': ''}}, {'slides': {'nowhere': 'Split.'}}):
            with self.subTest(extra=extra), self.assertRaises(WorkspaceError):
                marks.check('gate:outline', 'changes', extra, SLIDES)
        with self.assertRaises(WorkspaceError):
            marks.check('gate:outline', 'approve', {'slides': {'what-it-does': 'Split.'}},
                        SLIDES)

    def test_what_asks_a_worker(self):
        self.assertFalse(marks.asks({}))
        self.assertFalse(marks.asks({'left_out': ['instance-min']}))
        self.assertTrue(marks.asks({'again': {'instance-min': ''}}))
        self.assertTrue(marks.asks({'dropped': ['instance-min']}))


class NoteTests(unittest.TestCase):
    def test_the_note_lists_each_mark_then_the_person_s_own_words(self):
        said = marks.note('gate:research-plan', {
            'reword': {'instance-min': 'How many instances?'}, 'add': ['What does it cost?'],
            'dropped': ['health-checks']}, 'Keep it short.')
        self.assertEqual(said, '- Reword `instance-min` as: How many instances?\n'
                               '- Add a question: What does it cost?\n'
                               '- `health-checks` is dropped: leave it out.\n\n'
                               'Keep it short.')

    def test_research_and_outline_notes(self):
        self.assertEqual(marks.note('gate:research', {
            'again': {'instance-min': 'Use the docs.', 'health-checks': ''},
            'add': ['Why?'], 'left_out': ['other']}, None),
            '- Research `instance-min` again: Use the docs.\n'
            '- Research `health-checks` again.\n- Add a question: Why?\n'
            '- Leave out `other`.')
        self.assertEqual(marks.note('gate:outline', {'slides': {'what-it-does': 'Split it.'}},
                                    None), '- Slide `what-it-does`: Split it.')

    def test_no_marks_and_no_words_is_no_note(self):
        self.assertIsNone(marks.note('gate:outline', {}, None))
        self.assertEqual(marks.note('gate:outline', {}, 'Shorter.'), 'Shorter.')


class WordsTests(unittest.TestCase):
    def test_a_title_is_read_from_an_id(self):
        self.assertEqual(marks.title('licensing-cost'), 'Licensing cost')
        self.assertEqual(marks.title('market-players-2'), 'Market players 2')

    def test_a_new_id_is_made_from_the_question_and_never_taken(self):
        self.assertEqual(marks.new_id('What does a rolling restart cost?', []),
                         'what-does-a-rolling-restart')
        self.assertEqual(marks.new_id('What does a rolling restart cost?',
                                      ['what-does-a-rolling-restart']),
                         'what-does-a-rolling-restart-2')
        self.assertEqual(marks.new_id('???', []), 'question')

    def test_the_first_sentence(self):
        self.assertEqual(marks.first_sentence('One thing. Then another.'), 'One thing.')
        self.assertEqual(marks.first_sentence('  No stop at all '), 'No stop at all')
        self.assertEqual(marks.first_sentence(None), '')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python3 scripts/ci/run_tests.py test_marks`
Expected: FAIL with `ImportError: cannot import name 'marks' from 'runner'`.

- [ ] **Step 3: Write the module**

Create `runner/marks.py`:

```python
"""What a person marks at a stop reviewed item by item, checked, and the note it becomes.

What a caller needs to know
---------------------------
    marked = marks.check(gate, decision, extra, ids)   # the marks, cleaned, or a refusal
    marks.asks(marked)                                 # whether any mark needs a worker
    marks.note(gate, marked, free)                     # the note a worker reads, or None
    marks.title('licensing-cost')                      # 'Licensing cost'
    marks.new_id('What does it cost?', taken)          # 'what-does-it-cost'
    marks.first_sentence(text)

- REVIEWED are the stops reviewed this way. `ids` are what the stop has: its questions, or
  its slides as the person's edit has them. A mark naming anything else is refused.
- gate:research-plan takes {"dropped": [id], "reword": {id: text}, "add": [text]}.
  gate:research takes {"left_out": [id], "again": {id: line}, "add": [text]}; a line to
  research again with may be empty, and `left_out` is the whole set, so an empty one brings
  every finding back. gate:outline takes {"slides": {id: line}}, each line said.
- Approve takes only what needs no worker: drops at the plan and leave-outs at the
  research. Anything else is refused with AS_CHANGES.
- `check` returns only the marks that say something, and `left_out` whenever it was sent.
"""
from __future__ import annotations

import re

import runner  # noqa: F401  puts the core on the import path
from workspace import WorkspaceError

REVIEWED = ('gate:research-plan', 'gate:research', 'gate:outline')
ASKING = ('dropped', 'reword', 'add', 'again', 'slides')   # marks a worker acts on
LINE = 1000             # characters in one line a person writes against an item
ADDED = 10              # questions added at once
WORDS = 5               # words of a question a new ID is made from
ALL_DROPPED = 'Keep at least one question: research needs something to look up.'
ALL_LEFT_OUT = 'Keep at least one finding: the outline is drafted from them.'
AS_CHANGES = ('Rewording, adding, researching again and changing a slide go back to a '
              'worker: send them as changes.')


def _ids(value, ids: list[str], what: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(one, str) for one in value):
        raise WorkspaceError(f'Name each {what} by its ID.')
    unknown = [one for one in value if one not in ids]
    if unknown:
        raise WorkspaceError(f'There is no {what} {unknown[0]} here.')
    return list(dict.fromkeys(value))


def _lines(value, ids: list[str], what: str, needed: bool) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WorkspaceError(f'Give each {what} its line, by its ID.')
    lines = {}
    for ident, line in value.items():
        if ident not in ids:
            raise WorkspaceError(f'There is no {what} {ident} here.')
        if line is not None and not isinstance(line, str):
            raise WorkspaceError(f'What you wrote for {ident} is not text.')
        line = ' '.join((line or '').split())
        if needed and not line:
            raise WorkspaceError(f'Say what should change for {ident}.')
        if len(line) > LINE:
            raise WorkspaceError(f'Say it for {ident} in at most {LINE:,} characters.')
        lines[ident] = line
    return lines


def _texts(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(one, str) for one in value):
        raise WorkspaceError('A question to add is text.')
    texts = [' '.join(one.split()) for one in value]
    if any(not one for one in texts):
        raise WorkspaceError('A question to add is empty.')
    if any(len(one) > LINE for one in texts):
        raise WorkspaceError(f'Ask a question to add in at most {LINE:,} characters.')
    if len(texts) > ADDED:
        raise WorkspaceError(f'Add at most {ADDED} questions at once.')
    return texts


def check(gate: str, decision: str, extra: dict, ids) -> dict:
    """The marks sent with a decision at `gate`, cleaned. Refuses, in a sentence, one that
    names what the stop does not have, says nothing where it must, or goes with Approve
    when it needs a worker."""
    if gate not in REVIEWED:
        return {}
    ids, extra = list(ids), extra or {}
    if gate == 'gate:research-plan':
        marked = {'dropped': _ids(extra.get('dropped'), ids, 'question'),
                  'reword': _lines(extra.get('reword'), ids, 'question', True),
                  'add': _texts(extra.get('add'))}
        if ids and set(marked['dropped']) >= set(ids):
            raise WorkspaceError(ALL_DROPPED)
        both = [one for one in marked['reword'] if one in marked['dropped']]
        if both:
            raise WorkspaceError(f'{both[0]} is both dropped and reworded: choose one.')
        working = marked['reword'] or marked['add']
    elif gate == 'gate:research':
        marked = {'again': _lines(extra.get('again'), ids, 'question', False),
                  'add': _texts(extra.get('add'))}
        if 'left_out' in extra:
            marked['left_out'] = _ids(extra.get('left_out'), ids, 'question')
            if ids and set(marked['left_out']) >= set(ids):
                raise WorkspaceError(ALL_LEFT_OUT)
            both = [one for one in marked['again'] if one in marked['left_out']]
            if both:
                raise WorkspaceError(f'{both[0]} is both left out and researched again: '
                                     'choose one.')
        working = marked['again'] or marked['add']
    else:
        marked = {'slides': _lines(extra.get('slides'), ids, 'slide', True)}
        working = marked['slides']
    if decision == 'approve' and working:
        raise WorkspaceError(AS_CHANGES)
    return {key: value for key, value in marked.items() if value or key == 'left_out'}


def asks(marked: dict) -> bool:
    """Whether the marks ask a worker for anything."""
    return any((marked or {}).get(key) for key in ASKING)


def note(gate: str, marked: dict, free: str | None) -> str | None:
    """The note a worker reads: one line for each mark, then the person's own words."""
    lines = []
    if gate == 'gate:research-plan':
        lines += [f'Reword `{ident}` as: {text}'
                  for ident, text in (marked.get('reword') or {}).items()]
        lines += [f'Add a question: {text}' for text in marked.get('add') or ()]
        lines += [f'`{ident}` is dropped: leave it out.' for ident in marked.get('dropped') or ()]
    elif gate == 'gate:research':
        lines += [f'Research `{ident}` again' + (f': {line}' if line else '.')
                  for ident, line in (marked.get('again') or {}).items()]
        lines += [f'Add a question: {text}' for text in marked.get('add') or ()]
        lines += [f'Leave out `{ident}`.' for ident in marked.get('left_out') or ()]
    elif gate == 'gate:outline':
        lines += [f'Slide `{ident}`: {line}'
                  for ident, line in (marked.get('slides') or {}).items()]
    said = '\n'.join(f'- {line}' for line in lines)
    if free:
        said = f'{said}\n\n{free}' if said else free
    return said or None


def title(ident: str) -> str:
    """A question's ID as a person reads it: 'licensing-cost' is 'Licensing cost'."""
    words = str(ident).replace('-', ' ').strip()
    return words[:1].upper() + words[1:]


def new_id(question: str, taken) -> str:
    """An ID for a question the person added, from its first words, that no other has."""
    words = re.findall(r'[a-z0-9]+', str(question).lower())[:WORDS]
    base = '-'.join(words)[:40].strip('-') or 'question'
    ident, number = base, 2
    while ident in set(taken):
        ident, number = f'{base}-{number}', number + 1
    return ident


def first_sentence(text) -> str:
    """The first sentence of a text, with its spaces made single."""
    said = ' '.join(str(text or '').split())
    return re.split(r'(?<=[.!?])\s', said, maxsplit=1)[0] if said else ''
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python3 scripts/ci/run_tests.py test_marks`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add runner/marks.py tests/test_marks.py
git commit -m "Check what a person marks at a stop reviewed item by item"
```

---

### Task 2: A headline with every finding

**Files:**
- Modify: `runner/worker_tools.py` (`submit_finding` near line 1490; `TOOLS` near line 1653; constants near line 125)
- Modify: `runner/briefs/research-question.md` ("Hand back")
- Modify tests that hand back findings: `tests/runner_support.py:748`, `tests/test_runner_worker_tools.py` (`FindingTests.submit` and the call near line 797), `tests/test_runner_research.py:406`, `tests/test_runner_documents.py:706`
- Test: `tests/test_runner_worker_tools.py`, `tests/test_engine.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_runner_worker_tools.py`, class `FindingTests`, give `submit` a headline and add two tests after `test_an_accepted_finding_has_each_quote_placed`:

```python
    def submit(self, tools, quote=QUOTE, **changes):
        given = {'item': 'instance-min', 'status': 'supported',
                 'summary': 'An app keeps capacity when it runs more than one instance.',
                 'headline': 'Capacity holds when more than one instance runs.',
                 'limits': 'One page from the platform\'s own documentation.',
                 'evidence': [{'source_id': 's1', 'quote': quote}], **changes}
        return tools.submit_finding(**given)

    def test_an_accepted_finding_keeps_its_headline(self):
        tools = self.research()
        self.ok(self.submit(tools, headline='  Capacity holds   with two instances. '))
        finding = worker_tools.collect(self.job)['finding']
        self.assertEqual(finding['headline'], 'Capacity holds with two instances.')

    def test_a_finding_without_a_headline_or_with_a_long_one_is_refused(self):
        tools = self.research()
        said = self.refused(self.submit(tools, headline=''))
        self.assertIn('The headline is empty: give the answer in one sentence.', said)
        said = self.refused(self.submit(tools, headline=' '.join(['word'] * 26)))
        self.assertIn('The headline is 26 words. Give the answer in one sentence of at most '
                      '25 words.', said)
        self.assertIsNone(worker_tools.collect(self.job)['finding'])
```

Also add `headline=` to the `submit_finding` call near line 797 of the same file:

```python
        self.ok(tools.submit_finding('instance-min', 'supported', 'Two instances are kept.',
                                     headline='Two instances are kept.',
                                     evidence=[{'source_id': 's1', 'quote': 'Keep two '
                                                'instances running throughout.'}]))
```

In `tests/test_engine.py`, class `ResearchTests`, add:

```python
    def test_each_finding_s_headline_is_kept_with_the_research(self):
        root = self.start(research=True)
        self.to_gate(root, 'gate:research')
        record = json.loads((root / '.harness-research' / 'research.json').read_text())
        self.assertEqual({ident: result.get('headline')
                          for ident, result in record['results'].items()},
                         {'instance-min': 'The page answers instance-min.',
                          'health-checks': 'The page answers health-checks.'})
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 scripts/ci/run_tests.py test_runner_worker_tools.FindingTests test_engine.ResearchTests`
Expected: FAIL: `submit_finding() got an unexpected keyword argument 'headline'`.

- [ ] **Step 3: Take the headline in the worker tool**

In `runner/worker_tools.py`, beside `SUMMARY = 1500` add:

```python
HEADLINE = 25           # words in a finding's headline
```

Replace the start of `submit_finding` up to its first `if status not in STATUSES:` and the write of the accepted finding so it reads:

```python
    def submit_finding(self, item, status, summary, limits='', evidence=None, headline=None):
        """Hand back the finding for the job's question, with exact quotes."""
        wanted = self.job['finding']
        if not wanted:
            raise Refusal('This job does not answer a research question.')
        if str(item).strip() != wanted:
            raise Refusal(f'This job answers {wanted}, not "{item}".')
        self._allowed('finding', 'This finding')
        passages = self._passages(evidence)
        problems, kept = [], []
        headline = ' '.join(headline.split()) if isinstance(headline, str) else ''
        words = len(headline.split())
        if not words:
            problems.append('The headline is empty: give the answer in one sentence.')
        elif words > HEADLINE:
            problems.append(f'The headline is {words} words. Give the answer in one sentence '
                            f'of at most {HEADLINE} words.')
        if status not in STATUSES:
```

and, further down in the same method:

```python
        home.write_json(self.folder / 'accepted' / 'finding.json', {
            'item': wanted, 'status': status, 'summary': summary.strip(),
            'headline': headline, 'limits': limits, 'evidence': kept})
```

In `TOOLS`, replace the `submit_finding` entry with:

```python
    _described('submit_finding', 'Hand back the finding for your research question. Each '
               'quote must be copied exactly from a saved source; its place is worked out '
               'for you.',
               {'item': TEXT, 'status': {'type': 'string', 'enum': list(STATUSES)},
                'headline': TEXT, 'summary': TEXT, 'limits': TEXT,
                'evidence': {'type': 'array', 'items': {
                    'type': 'object', 'properties': {'source_id': TEXT, 'quote': TEXT},
                    'required': ['source_id', 'quote']}}},
               ['item', 'status', 'headline', 'summary']),
```

- [ ] **Step 4: Tell the worker**

In `runner/briefs/research-question.md`, in the "Hand back" list, after the `status` line add:

```markdown
- `headline`: the answer in one sentence of at most 25 words, as you would say it to the audience. For `insufficient` or `unavailable`, say what is not known.
```

- [ ] **Step 5: Nothing more to keep it**

The engine already hands each accepted finding to `Research.record`, which hands its `headline` to harness-research since Task 0, and harness-research keeps it in its record. Nothing in `runner/research_steps.py` changes for this task.

- [ ] **Step 6: Give every scripted finding a headline**

`tests/runner_support.py`, `Workers.question`:

```python
        self._ok(tools.submit_finding(ident, 'supported', f'What the page says about {ident}.',
                                      headline=f'The page answers {ident}.',
                                      evidence=[{'source_id': saved, 'quote': QUOTE}]))
```

`tests/test_runner_research.py` near line 406:

```python
        accepted = tools.submit_finding(
            'instance-min', 'supported', 'An app keeps capacity with two or more instances.',
            headline='Two or more instances keep capacity.',
            evidence=[{'source_id': 's1', 'quote': QUOTE}, {'source_id': 's1', 'quote': typed}])
```

`tests/test_runner_documents.py` near line 706:

```python
        handed = tools.submit_finding('instance-min', 'supported', 'Two or more instances.',
                                      headline='Two or more instances.',
                                      evidence=[{'source_id': 's1', 'quote': QUOTE},
                                                {'source_id': 's2', 'quote': QUOTE}])
```

Then search for any other caller: `grep -rn "submit_finding(" tests/` and give each one a `headline=`.

- [ ] **Step 7: Run the tests**

Run: `python3 scripts/ci/run_tests.py test_runner_worker_tools test_runner_research test_runner_documents test_engine test_briefs`
Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
git add runner/worker_tools.py runner/briefs/research-question.md tests/
git commit -m "Hand back a one-sentence headline with every finding"
```

---

### Task 3: The research stops list their items

**Files:**
- Modify: `runner/research_steps.py` (new `_findings_shown`)
- Modify: `runner/engine.py` (`_show_research_plan`, `_show_research`, near line 2047)
- Test: `tests/test_engine.py` (`ResearchTests`)

- [ ] **Step 1: Write the failing test**

Add to `ResearchTests` in `tests/test_engine.py`:

```python
    def test_the_research_stops_list_each_question_and_finding(self):
        root = self.start(research=True)
        plan = self.view(root)['gate']
        self.assertEqual(plan['questions'][0], {
            'id': 'instance-min', 'title': 'Instance min',
            'question': 'How many instances keep capacity during a restart?',
            'search': 'rolling restart minimum instances'})
        self.decide(root, 'gate:research-plan')
        found = self.view(root)['gate']
        first = found['items'][0]
        self.assertEqual({key: first[key] for key in ('id', 'title', 'status', 'headline',
                                                      'left_out', 'unknown')},
                         {'id': 'instance-min', 'title': 'Instance min', 'status': 'supported',
                          'headline': 'The page answers instance-min.', 'left_out': False,
                          'unknown': ''})
        self.assertEqual(first['sources'][0]['quote'], runner_support.QUOTE)
        self.assertEqual(first['sources'][0]['origin'], runner_support.URL)
        self.assertNotIn(str(root), json.dumps(found))
        # A finding kept before headlines were asked for is given its summary's first
        # sentence.
        kept = root / '.harness-research' / 'research.json'
        record = json.loads(kept.read_text())
        del record['results']['instance-min']['headline']
        kept.write_text(json.dumps(record))
        self.assertEqual(self.view(root)['gate']['items'][0]['headline'],
                         'What the page says about instance-min.')
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 scripts/ci/run_tests.py test_engine.ResearchTests`
Expected: FAIL with `KeyError: 'title'`.

- [ ] **Step 3: Build the per-item view**

In `runner/research_steps.py`, import `marks`:

```python
from runner import briefs, documents, marks, stages, worker_tools
```

Add to `Researching`, after `_verdicts`:

```python
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
            known = limits.strip().lower() in ('', 'none')
            shown.append({
                'id': ident, 'title': marks.title(ident), 'question': question,
                'status': result.get('status') or 'pending',
                'headline': headline or marks.first_sentence(summary), 'summary': summary,
                'limits': '' if known else limits,
                'unknown': '' if known else marks.first_sentence(limits),
                'left_out': ident in left,
                'sources': [{'title': str(passage.get('title') or ''),
                             'origin': str(passage.get('origin') or ''),
                             'quote': str(passage.get('quote') or '')}
                            for passage in result.get('evidence') or ()
                            if isinstance(passage, dict)]})
        return shown
```

In `runner/engine.py`, add `marks` to the `from runner import ...` line:

```python
from runner import agents, companion, decks, documents, gitstate, marks, settings, stages
```

and replace `_show_research_plan` and `_show_research` with:

```python
    def _show_research_plan(self, root: Path, record: dict) -> dict:
        plan = home.read_json(root / research_steps.PLAN, None)
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
```

and import the module where `PLAN_MD` is imported:

```python
from runner import research_steps
from runner.research_steps import PLAN_MD, REPORT, Researching
```

- [ ] **Step 4: Run the tests**

Run: `python3 scripts/ci/run_tests.py test_engine test_runner_page`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add runner/research_steps.py runner/engine.py tests/test_engine.py
git commit -m "List each question and finding at the research stops"
```

---

### Task 4: Marks at the research plan

**Files:**
- Modify: `runner/research_steps.py` (new `_drop_questions`)
- Modify: `runner/engine.py` (`decide`, `_approve`, new `_marked_ids`, `_apply_marks`, `_edit_outline`)
- Modify: `runner/page.py` (`decide`)
- Test: `tests/test_engine.py` (new class `PlanMarkTests`), `tests/test_runner_page.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_engine.py`:

```python
class PlanMarkTests(StudioCase):
    def questions(self, root):
        return [item['id'] for item in
                json.loads((root / 'research' / 'plan.json').read_text())['items']]

    def test_dropped_questions_go_with_the_approval(self):
        root = self.start(research=True)
        self.engine.decide(root, 'gate:research-plan', 'approve', None,
                           {'dropped': ['health-checks']})
        self.assertEqual(self.questions(root), ['instance-min'])
        self.assertNotIn('health-checks', (root / 'research' / 'plan.md').read_text())
        self.assertEqual(len(self.workers.of('question')), 1)
        self.assertEqual(self.waiting(root), 'gate:research')

    def test_rewording_and_adding_go_back_to_the_planner_as_one_note(self):
        root = self.start(research=True)
        self.engine.decide(root, 'gate:research-plan', 'changes', 'Keep it short.', {
            'dropped': ['health-checks'],
            'reword': {'instance-min': 'How many instances keep capacity?'},
            'add': ['What does a restart cost?']})
        task = self.workers.of('research-plan')[-1].task
        self.assertIn('- Reword `instance-min` as: How many instances keep capacity?', task)
        self.assertIn('- Add a question: What does a restart cost?', task)
        self.assertIn('Keep it short.', task)
        # The drop was applied before the planner ran again.
        self.assertIn('"id": "instance-min"', task)
        self.assertNotIn('"id": "health-checks"', task)
        gate = self.record(root)['gates']['gate:research-plan']
        self.assertEqual((gate['state'], gate['round']), ('waiting', 2))

    def test_marks_that_say_nothing_or_need_a_worker_with_approve_are_refused(self):
        root = self.start(research=True)
        for decision, extra, said in (
                ('approve', {'add': ['Why?']}, marks.AS_CHANGES),
                ('approve', {'dropped': ['instance-min', 'health-checks']}, marks.ALL_DROPPED),
                ('changes', {'dropped': ['nowhere']}, 'There is no question nowhere here.'),
                ('changes', {}, 'Say what should change.')):
            with self.subTest(extra=extra):
                with self.assertRaises(WorkspaceError) as caught:
                    self.engine.decide(root, 'gate:research-plan', decision, None, extra)
                self.assertIn(said, str(caught.exception))
        self.assertEqual(self.questions(root), ['instance-min', 'health-checks'])
        self.assertEqual(self.waiting(root), 'gate:research-plan')
```

Add `marks` to the test module's runner import:

```python
from runner import decks, marks, stages
```

Add to `tests/test_runner_page.py`, class `RunTests`:

```python
    def test_changes_with_marks_need_no_note_and_changes_with_nothing_do(self):
        path = self.started(research=True)
        self.post('decide', {'path': path, 'gate': 'gate:research-plan',
                             'decision': 'changes'}, 400)
        self.post('decide', {'path': path, 'gate': 'gate:research-plan', 'decision': 'changes',
                             'extra': {'add': ['What does a restart cost?']}})
        self.assertEqual(self.run_of(path)['gate']['round'], 2)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 scripts/ci/run_tests.py test_engine.PlanMarkTests test_runner_page.RunTests`
Expected: FAIL: the drop is not applied, and the page refuses changes with marks and no note.

- [ ] **Step 3: Drop questions from the plan**

In `runner/research_steps.py`, add to `Researching`, after `_keep_plan`:

```python
    def _drop_questions(self, root: Path, record: dict, dropped) -> None:
        """Take the questions the person dropped out of the plan, as they asked, with no
        worker. A plan is never left with none."""
        plan = home.read_json(root / PLAN, None)
        items = plan.get('items') if isinstance(plan, dict) else None
        if not isinstance(items, list):
            raise WorkspaceError('There is no research plan to drop a question from.')
        kept = [item for item in items
                if not (isinstance(item, dict) and item.get('id') in set(dropped))]
        if not kept:
            raise WorkspaceError(marks.ALL_DROPPED)
        self._keep_plan(root, record, json.dumps({**plan, 'items': kept}, indent=2,
                                                 ensure_ascii=False))
```

- [ ] **Step 4: Check and apply marks in `decide`**

In `runner/engine.py`, in `decide`, replace:

```python
        if decision == 'changes' and not note and not rebrand:
            raise WorkspaceError(NO_NOTE)
```

with:

```python
        marked = marks.check(gate, decision, extra, self._marked_ids(root, gate, extra))
        if decision == 'changes' and not note and not rebrand and not marks.asks(marked):
            raise WorkspaceError(NO_NOTE)
```

In the approve branch, pass the marks:

```python
            elif decision == 'approve':
                record = self._approve(root, record, gate, note, extra, marked)
```

In the changes branch, apply the marks before the gate is written. The branch becomes:

```python
            else:
                gated = record['gates'].get(gate) or {}
                named = self._numbers(extra) if gate == 'gate:build' else None
                more = {'again': None, 'free': None} if gate == 'gate:research' else {}
                if rebrand:
                    looks.rebrand(root, record, extra['brand'], extra.get('variant'), brands)
                    note = note or ('Make it in ' + decks.brand_words(record['form']) + '.')
                elif marked:
                    record, note, more = self._apply_marks(root, record, gate, marked, note,
                                                           extra)
                record['gates'][gate] = {**gated, 'state': 'changes', 'note': note, 'at': at,
                                         'by': by, 'round': int(gated.get('round') or 1),
                                         **more,
                                         **({'slides': named} if gate == 'gate:build' else {})}
```

Replace `_approve` with:

```python
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
            record.setdefault('research', {})['left_out'] = marked['left_out']
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
                     note: str | None, extra: dict) -> tuple[dict, str | None, dict]:
        """The marks of a request for changes that need no worker, applied before the stop
        is reopened. Returns the run, the note its worker reads and what the gate keeps
        beside it."""
        more = {}
        if gate == 'gate:research-plan' and marked.get('dropped'):
            self._drop_questions(root, record, marked['dropped'])
        elif gate == 'gate:research':
            if 'left_out' in marked:
                record.setdefault('research', {})['left_out'] = marked['left_out']
            added = self._add_questions(root, record, marked.get('add') or [])
            again = {**(marked.get('again') or {}), **{ident: '' for ident in added}}
            more = {'again': again, 'free': note}
        elif gate == 'gate:outline' and extra.get('edited') is not None:
            self._edit_outline(root, record, extra['edited'])
        return record, marks.note(gate, marked, note), more
```

(`_add_questions` is written in Task 5. Until then, add this placeholder-free stub to `Researching` so this task's tests run; Task 5 replaces its body:)

```python
    def _add_questions(self, root: Path, record: dict, texts) -> list[str]:
        """Add the questions the person wrote to the plan. Returns their IDs."""
        if texts:
            raise WorkspaceError('Adding a question after the research comes next.')
        return []
```

- [ ] **Step 5: Let the page send changes with marks and no note**

In `runner/page.py`, import `marks`:

```python
from runner import decks, gitstate, marks, settings, setup
```

and in `decide` replace the note check with:

```python
        if decision == 'changes' and gate != 'gate:look' and not (note or '').strip() \
                and not marks.asks(extra or {}):
            raise server.Refusal(HTTPStatus.BAD_REQUEST, engines.NO_NOTE)
```

and its docstring with:

```python
        """A person's decision at a gate: approve, or ask for changes with a note, marks, or
        both. At the brand's gate the change is another brand, and needs no note."""
```

- [ ] **Step 6: Run the tests**

Run: `python3 scripts/ci/run_tests.py test_engine test_runner_page test_marks`
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add runner/research_steps.py runner/engine.py runner/page.py tests/test_engine.py tests/test_runner_page.py
git commit -m "Drop, reword and add research questions at the plan"
```

---

### Task 5: Marks at the research findings

**Files:**
- Modify: `runner/research_steps.py` (`_research`, `_question`, `_report_text`, `_add_questions`, new `_asked`)
- Test: `tests/test_engine.py` (new class `FindingMarkTests`)

Keeping the other findings when a question is added is harness-research's since 0.8.1 (Task 0): a changed plan keeps the findings of unchanged questions. Nothing here re-records them.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_engine.py`:

```python
def unsettled(workers, ident):
    """A research worker that leaves `ident` open and answers every other question."""
    def act(tools, job):
        if tools.job['finding'] != ident:
            return workers.question(tools, job)
        return tools.submit_finding(ident, 'insufficient', 'No page says.',
                                    headline='No page says what starts the next batch.',
                                    limits='Only one page was found.', evidence=[])
    return act


class FindingMarkTests(StudioCase):
    def researched(self):
        self.workers.then('question', unsettled(self.workers, 'health-checks'),
                          unsettled(self.workers, 'health-checks'))
        root = self.start(research=True)
        self.decide(root, 'gate:research-plan')
        self.assertEqual(self.waiting(root), 'gate:research')
        return root

    def test_the_report_is_written_from_each_finding(self):
        root = self.researched()
        report = (root / 'research' / 'report.md').read_text()
        for said in ('1 of 2 questions have an answer the sources support.',
                     'Not settled (1):', '## Instance min (`instance-min`)',
                     'The page answers instance-min.', 'Not known: Only one page was found.',
                     f'"{runner_support.QUOTE}"'):
            self.assertIn(said, report)

    def test_left_out_findings_go_with_the_approval_and_leave_the_report(self):
        root = self.researched()
        self.engine.decide(root, 'gate:research', 'approve', None,
                           {'left_out': ['health-checks']})
        report = (root / 'research' / 'report.md').read_text()
        self.assertIn('1 of 1 question have an answer the sources support.', report)
        self.assertIn('Left out by you (1):\n- Health checks', report)
        self.assertNotIn('No page says', report)
        self.assertEqual(self.record(root)['research']['left_out'], ['health-checks'])
        self.assertEqual(self.waiting(root), 'gate:outline')

    def test_research_again_redoes_only_the_marked_question_with_its_line(self):
        root = self.researched()
        before = len(self.workers.of('question'))
        self.engine.decide(root, 'gate:research', 'changes', 'Be brief.', {
            'left_out': [], 'again': {'health-checks': 'Look for the platform docs.'}})
        asked = [spec['finding'] for kind, job, spec in self.workers.jobs
                 if kind.startswith('question:')][before:]
        self.assertEqual(asked, ['health-checks'])
        task = self.workers.of('question')[-1].task
        self.assertIn('researched again. What they said about it:\n\nLook for the platform '
                      'docs.', task)
        self.assertIn('Be brief.', task)
        gate = self.view(root)['gate']
        self.assertEqual((gate['name'], gate['round']), ('gate:research', 2))

    def test_a_question_added_after_the_research_keeps_the_other_findings(self):
        root = self.researched()
        before = len(self.workers.of('question'))
        self.engine.decide(root, 'gate:research', 'changes', None,
                           {'add': ['What does a restart cost?']})
        asked = [spec['finding'] for kind, job, spec in self.workers.jobs
                 if kind.startswith('question:')][before:]
        self.assertEqual(asked, ['what-does-a-restart-cost'])
        statuses = {item['id']: item['status'] for item in self.view(root)['gate']['items']}
        self.assertEqual(statuses, {'instance-min': 'supported', 'health-checks': 'insufficient',
                                    'what-does-a-restart-cost': 'supported'})

    def test_marks_that_need_a_worker_go_as_changes(self):
        root = self.researched()
        with self.assertRaises(WorkspaceError) as caught:
            self.engine.decide(root, 'gate:research', 'approve', None,
                               {'again': {'health-checks': ''}})
        self.assertEqual(str(caught.exception), marks.AS_CHANGES)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 scripts/ci/run_tests.py test_engine.FindingMarkTests`
Expected: FAIL: the report has no per-question sections, every unresolved question is researched again, and adding a question is refused.

- [ ] **Step 3: Write the report from each finding**

In `runner/research_steps.py`, replace `_report_text` with the version below. It no longer splices in harness-research's own report: each question the person kept is written from its data, so a finding left out is simply not written, and nothing depends on how harness-research lays its report out.

```python
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
                 f"{supported} of {total} question{'' if total == 1 else 's'} have an answer "
                 'the sources support.']
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
                          f"\"{source['quote']}\"" for source in item['sources']]
        return '\n'.join(lines) + '\n'
```

`verdicts` is no longer read; keep the parameter so the callers stay as they are.

- [ ] **Step 4: Add questions to the plan**

Replace the `_add_questions` stub from Task 4 with:

```python
    def _add_questions(self, root: Path, record: dict, texts) -> list[str]:
        """Add the questions the person wrote to the plan, as they wrote them and with no
        search words. Returns their IDs."""
        if not texts:
            return []
        plan = home.read_json(root / PLAN, None)
        if not isinstance(plan, dict) or not isinstance(plan.get('items'), list):
            raise WorkspaceError('There is no research plan to add a question to.')
        taken = [item.get('id') for item in plan['items'] if isinstance(item, dict)]
        added = []
        for text in texts:
            ident = marks.new_id(text, taken + added)
            plan['items'].append({'id': ident, 'question': text, 'public_query': None,
                                  'claim': None})
            added.append(ident)
        checked = worker_tools.check_research_plan(plan)
        if checked['status'] == 'failed':
            raise WorkspaceError(' '.join(checked['problems']))
        self._keep_plan(root, record, json.dumps(plan, indent=2, ensure_ascii=False))
        return added
```

- [ ] **Step 5: Research only the marked questions, each with its line**

In `_research`, keep what the run record holds about the research when a changed plan is handed over (the person's leave-outs live there). Replace:

```python
                record['research'] = {'run': status.get('run'), 'plan': sha256_of(root / PLAN)}
```

with:

```python
                record['research'] = {**handed, 'run': status.get('run'),
                                      'plan': sha256_of(root / PLAN)}
```

Then replace the block that works out which questions to research again:

```python
            if gate.get('state') == 'changes' and (asked or {}).get('at') != gate.get('at'):
                verdicts = self._verdicts(root)
                left = [ident for ident, verdict in verdicts.items()
                        if self._named(ident, gate.get('note'))
                        or verdict in ('pending', *UNRESOLVED)] or list(verdicts)
```

with:

```python
            if gate.get('state') == 'changes' and (asked or {}).get('at') != gate.get('at'):
                verdicts = self._verdicts(root)
                marked = gate.get('again')
                if isinstance(marked, dict) and marked:
                    left = [ident for ident in verdicts if ident in marked]
                else:
                    left = [ident for ident, verdict in verdicts.items()
                            if self._named(ident, gate.get('note'))
                            or verdict in ('pending', *UNRESOLVED)] or list(verdicts)
```

Further down in `_research`, replace:

```python
        note = gate.get('note') if gate.get('state') == 'changes' else None

        def one(ident: str) -> None:
            if self._may_go(root):
                self._question(root, run, ident, note)
```

with:

```python
        def one(ident: str) -> None:
            if self._may_go(root):
                self._question(root, run, ident, self._asked(gate, ident))
```

In `_question`, rename the parameter `note` to `asked` and replace:

```python
        if note:
            task += ('\n\nThe person looked at the research and asked for this, which may or '
                     f'may not be about your question:\n\n{note}')
```

with:

```python
        if asked:
            task += f'\n\n{asked}'
```

Add to `Researching`, after `_named`:

```python
    @staticmethod
    def _asked(gate: dict, ident: str) -> str | None:
        """What a worker researching `ident` again is told the person said: the line they
        wrote against it and their own words, or the note at the gate."""
        if gate.get('state') != 'changes':
            return None
        again = gate.get('again')
        if isinstance(again, dict) and again:
            line = again.get(ident) or ''
            said = ('The person asked for your question to be researched again'
                    + (f'. What they said about it:\n\n{line}' if line else '.'))
            if gate.get('free'):
                said += ('\n\nThey also wrote this, which may or may not be about your '
                         f"question:\n\n{gate['free']}")
            return said
        note = gate.get('note')
        return ('The person looked at the research and asked for this, which may or may '
                f'not be about your question:\n\n{note}') if note else None
```

- [ ] **Step 6: Run the tests**

Run: `python3 scripts/ci/run_tests.py test_engine test_runner_research test_flow_routes test_desk`
Expected: `OK`. The existing `test_changes_at_the_research_redo_the_questions_the_note_names` still passes, because a note without marks takes the old path. If a test looked for harness-research's own report text in `report.md` (`Status: supported.` is still there; `Source:` lines are now `Sources:`), point it at the new wording.

- [ ] **Step 7: Commit**

```bash
git add runner/research_steps.py tests/test_engine.py
git commit -m "Leave out, research again and add questions at the findings"
```

---

### Task 6: Marks on the outline's slides

**Files:**
- Test: `tests/test_engine.py` (new class `OutlineMarkTests`)

The engine work was done in Task 4 (`_marked_ids`, `_apply_marks`). This task proves it.

- [ ] **Step 1: Write the tests**

```python
class OutlineMarkTests(StudioCase):
    def test_slides_marked_for_changes_reach_the_outline_worker(self):
        root = self.start()
        slides = self.view(root)['gate']['slides']
        moved = [slides[0], slides[2], slides[1], *slides[3:]]
        self.engine.decide(root, 'gate:outline', 'changes', None, {
            'edited': moved, 'slides': {slides[1]['id']: 'Split it in two.'}})
        kept = json.loads((root / 'outline.json').read_text())
        self.assertEqual([one['id'] for one in kept['slides']], [one['id'] for one in moved])
        task = self.workers.of('outline')[-1].task
        self.assertIn(f"- Slide `{slides[1]['id']}`: Split it in two.", task)
        self.assertEqual(self.record(root)['gates']['gate:outline']['round'], 2)

    def test_a_slide_the_outline_does_not_have_is_refused(self):
        root = self.start()
        with self.assertRaises(WorkspaceError) as caught:
            self.engine.decide(root, 'gate:outline', 'changes', None,
                               {'slides': {'no-such-slide': 'Split it.'}})
        self.assertEqual(str(caught.exception), 'There is no slide no-such-slide here.')
        self.assertEqual(len(self.workers.of('outline')), 1)
```

- [ ] **Step 2: Run them**

Run: `python3 scripts/ci/run_tests.py test_engine.OutlineMarkTests`
Expected: `OK`. If the first fails because the scripted outline worker draws the old order, set `self.workers.outline_said = {**self.workers.outline_said, 'slides': moved}` before `decide`, as `tests/test_desk.py` does.

- [ ] **Step 3: Commit**

```bash
git add tests/test_engine.py
git commit -m "Prove slide marks reach the outline worker with the edits"
```

---

### Task 7: The page's review component and decision button

**Files:**
- Modify: `skills/presentation-studio/scripts/desk/app.js` (`chosenFor` near line 2939; `extraFor`, `decide`, `deckActions` near lines 3806-3960; `paintDeck`'s toolbar mark; a new section before `// --- one deck: deciding and steering`)
- Modify: `skills/presentation-studio/scripts/desk/deck.css`
- Test: `tests/test_desk.py`

- [ ] **Step 1: Hold the marks**

In `chosenFor`, the initial object becomes:

```js
  if (!view.chosen[key]) view.chosen[key] = { wrong: false, work: null, edited: false,
    marked: [], adding: '', brand: '', variant: '', dropped: [], reword: {}, again: {},
    leftOut: null, added: [], asking: '', slideNotes: {} };
```

- [ ] **Step 2: Add the review component**

Insert this section before `// --- one deck: deciding and steering`:

```js
// --- one deck: a stop reviewed item by item -------------------------------------------------
// The research plan, the research and the outline are shown as items the person marks one
// by one: what needs them first, the rest a line each, and one button that says what it
// will do. Marks are kept with the stop's other choices (`chosenFor`), so a refresh loses
// nothing, and nothing is sent until the button is pressed.

const REVIEWED = ['gate:research-plan', 'gate:research', 'gate:outline'];
const FINDING_WORDS = { supported: ['done', 'Answered'], insufficient: ['late', 'Not settled'],
  unavailable: ['late', 'Not found'], contradicted: ['review', 'Contradicted'],
  pending: ['out', 'Not answered'] };

function sized(value) {
  return Array.isArray(value) ? value.length : Object.keys(value || {}).length;
}

function owns(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

// The lines typed against items, trimmed, keeping those that say something. `unchanged`
// leaves out a line that is what the item says already.
function filled(lines, unchanged) {
  const kept = {};
  for (const [id, text] of Object.entries(lines || {})) {
    const said = String(text || '').trim();
    if (said && (!unchanged || said !== unchanged(id))) kept[id] = said;
  }
  return kept;
}

// The findings the person leaves out: as the runner has them until they change it here.
function leftOut(gate) {
  const held = chosenFor(gate);
  if (!held.leftOut) {
    held.leftOut = list(gate.items).filter((item) => item.left_out).map((item) => item.id);
  }
  return held.leftOut;
}

// What the person has marked at a reviewed stop, as the runner takes it.
function marksOf(gate) {
  const held = chosenFor(gate);
  if (gate.name === 'gate:research-plan') {
    const asked = new Map(list(gate.questions).map((item) => [item.id, item.question]));
    return { dropped: held.dropped.slice(),
      reword: filled(held.reword, (id) => asked.get(id)), add: held.added.slice() };
  }
  if (gate.name === 'gate:research') {
    const again = {};
    for (const [id, text] of Object.entries(held.again)) again[id] = String(text || '').trim();
    return { left_out: leftOut(gate).slice(), again, add: held.added.slice() };
  }
  if (gate.name === 'gate:outline') {
    const here = new Set(outlineWork(gate).map((one) => one.id));
    const slides = filled(held.slideNotes);
    for (const id of Object.keys(slides)) if (!here.has(id)) delete slides[id];
    return { slides };
  }
  return {};
}

// What a reviewed stop's button does now: its words, whether it approves, what goes with
// it, and a tally of the marks.
function reviewOf(gate) {
  const held = chosenFor(gate);
  const marks = marksOf(gate);
  if (gate.name === 'gate:research-plan') {
    const dropped = sized(marks.dropped);
    const asked = sized(marks.reword) + sized(marks.add);
    const tally = [count(dropped, 'dropped', 'dropped'),
      count(sized(marks.reword), 'reworded', 'reworded'),
      count(sized(marks.add), 'added', 'added')].join(' · ');
    if (asked) {
      return { label: 'Send ' + count(asked + dropped, 'change', 'changes'), approve: false,
        extra: marks, tally };
    }
    if (dropped) {
      return { label: 'Approve without ' + count(dropped, 'question', 'questions'),
        approve: true, extra: { dropped: marks.dropped }, tally };
    }
    return { label: 'Approve', approve: true, extra: null, tally };
  }
  if (gate.name === 'gate:research') {
    const before = list(gate.items).filter((item) => item.left_out).map((item) => item.id);
    const moved = marks.left_out.filter((id) => !before.includes(id)).length
      + before.filter((id) => !marks.left_out.includes(id)).length;
    const asked = sized(marks.again) + sized(marks.add);
    const tally = [count(sized(marks.again), 'to research again', 'to research again'),
      count(marks.left_out.length, 'left out', 'left out'),
      count(sized(marks.add), 'added', 'added')].join(' · ');
    if (asked) {
      return { label: 'Send ' + count(asked + moved, 'change', 'changes'), approve: false,
        extra: marks, tally };
    }
    if (moved) {
      return { label: marks.left_out.length ? 'Approve, leaving out '
        + count(marks.left_out.length, 'finding', 'findings') : 'Approve with every finding',
      approve: true, extra: { left_out: marks.left_out }, tally };
    }
    return { label: 'Approve', approve: true, extra: null, tally };
  }
  const slides = sized(marks.slides);
  const edited = held.edited ? { edited: held.work } : null;
  const tally = count(slides, 'slide to change', 'slides to change')
    + (held.edited ? ' · edited here' : '');
  if (slides) {
    return { label: 'Send ' + count(slides, 'change', 'changes'), approve: false,
      extra: { ...marks, ...(edited || {}) }, tally };
  }
  return { label: 'Approve', approve: true, extra: edited, tally };
}

function sendReview(gate, pressed) {
  const made = reviewOf(gate);
  decide(made.approve ? 'approve' : 'changes', '', null, pressed, made.extra);
}

// Two to four numbers in a row, each with what it counts.
function reviewCounts(pairs) {
  const node = make('div', 'review-counts');
  for (const [number, words] of pairs) {
    add(node, add(make('p', 'review-count'), make('span', 'review-number', String(number)),
      ' ', make('span', 'quiet', words)));
  }
  return node;
}

// The full text a stop was drawn from, folded.
function fullText(summary, label, text, key) {
  const node = make('details', 'card-part');
  node.dataset.key = key;
  return add(node, make('summary', '', summary), documentPart(label, text));
}

// The tally of the marks and the button that sends them, at the foot of the items.
function reviewBar(gate) {
  const node = make('div', 'review-bar');
  node.id = 'review-bar';
  paintReviewBar(gate, node);
  return node;
}

function paintReviewBar(gate, node) {
  if (!node) return;
  const made = reviewOf(gate);
  const tally = make('p', 'quiet', made.tally);
  tally.setAttribute('role', 'status');
  const go = capsule(made.label, '', () => sendReview(gate, go), 'review-send');
  node.replaceChildren(tally, add(make('div', 'bar'), go));
}

// A mark changed: the tally, this button and the toolbar's say so at once.
function reviewChanged(gate) {
  paintReviewBar(gate, byId('review-bar'));
  if (view.screen === 'deck' && view.run) paintDeck(false);
}

// New questions the person adds, each with the way to take it back, and a box for one more.
function addedPart(gate) {
  const node = make('div', 'review-added');
  node.id = 'review-added';
  paintAdded(gate, node);
  return node;
}

function paintAdded(gate, node) {
  if (!node) return;
  const held = chosenFor(gate);
  const items = make('ul', 'plain review-list');
  held.added.forEach((text, index) => {
    const take = capsule('Take it back', 'quiet', () => {
      held.added.splice(index, 1);
      paintAdded(gate, byId('review-added'));
      reviewChanged(gate);
      focusKey('added-question');
    }, 'unadd ' + index);
    take.setAttribute('aria-label', 'Take back “' + text + '”');
    items.append(add(make('li', 'review-row'), make('p', '', text),
      add(make('div', 'bar'), take)));
  });
  const box = field('added-question', 'A question to add', held, 'asking',
    { long: true, limit: 1000 });
  const go = capsule('Add the question', 'quiet', () => {
    const text = String(held.asking || '').trim();
    if (!text) {
      refuse('added-question', 'Write the question first.');
      focusKey('added-question');
      return;
    }
    held.added.push(text);
    held.asking = '';
    paintAdded(gate, byId('review-added'));
    reviewChanged(gate);
    focusKey('added-question');
  }, 'add-question');
  node.replaceChildren(...(held.added.length ? [make('h3', 'row-title', 'Questions you added'),
    items] : []), box, add(make('div', 'bar'), go));
}
```

- [ ] **Step 3: Send marks with a decision**

Replace `extraFor` with:

```js
// What comes with a decision at the gate, from what the person chose there.
function extraFor(gate, decision) {
  const held = chosenFor(gate);
  if (REVIEWED.includes(gate.name)) {
    if (decision === 'approve') return reviewOf(gate).extra;
    const marks = marksOf(gate);
    return gate.name === 'gate:outline' && held.edited ? { ...marks, edited: held.work } : marks;
  }
  if (gate.name === 'gate:classify' && decision === 'approve' && held.wrong
      && gate.kind === 'document') {
    return { kind: gate.verdict === 'spec' ? 'material' : 'spec' };
  }
  if (gate.name === 'gate:look' && decision === 'changes') {
    return { brand: held.brand, variant: held.variant || null };
  }
  if (gate.name === 'gate:build' && decision === 'changes' && held.marked.length) {
    return { slides: markedSlides() };
  }
  return null;
}
```

In `decide`, take an explicit `extra`. Its first lines become:

```js
async function decide(decision, note, problem, pressed, extra) {
  if (view.busy) return;
  const turn = view.turn;
  const run = view.run;
  const gate = run.gate;
  const noted = noteKey(decision);
  const body = { path: view.path, gate: gate ? gate.name : 'gate:build', decision };
  if (note) body.note = note;
  const more = extra !== undefined ? extra : gate ? extraFor(gate, decision) : null;
  if (more) body.extra = more;
```

(delete the two old lines that set `extra` from `extraFor`).

In `deckActions`, the gate's buttons become:

```js
  if (run.gate && !run.question) {
    // Approve acts at once: what it does is said beside the gate before it is pressed. At
    // a stop reviewed item by item it says what it will do with the marks.
    const reviewed = REVIEWED.includes(run.gate.name);
    const approve = capsule(reviewed ? reviewOf(run.gate).label : 'Approve',
      lead === 'approve' ? 'filled' : '', () => (reviewed ? sendReview(run.gate, approve)
        : decide('approve', '', null, approve)), 'approve');
    const brand = run.gate.name === 'gate:look';
    actions.push(approve, capsule(brand ? 'Choose another brand' : 'Ask for changes', '',
      openSheet(brand ? 'rebrand' : 'changes', 'changes'), 'changes'));
  }
```

In `paintDeck`, add the button's words to the toolbar's mark so it is drawn again when a mark changes:

```js
    mark: [title, route, run.state, lead, gate && [gate.name, gate.round], read, driver,
      Boolean(run.question), run.problem,
      gate && REVIEWED.includes(gate.name) && !read ? reviewOf(gate).label : ''] }, [
```

- [ ] **Step 4: Style it**

Append to `skills/presentation-studio/scripts/desk/deck.css`:

```css
/* A stop reviewed item by item: its counts, its items, and the button that says what it
   does. */
.review-counts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 0.6rem;
  margin: 0.4rem 0 0.8rem;
}

.review-count {
  padding: 0.6rem 0.8rem;
  background: var(--well);
  border-radius: 12px;
}

.review-number {
  display: block;
  font-size: 1.4rem;
  font-weight: 650;
}

.review-list > li + li {
  margin-top: 0.6rem;
}

.review-row {
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--hair);
  border-radius: 12px;
}

.review-row > * + * {
  margin-top: 0.35rem;
}

.review-off {
  color: var(--quiet);
}

.review-off .row-title {
  text-decoration: line-through;
}

.review-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.6rem;
}

.review-headline {
  font-weight: 560;
}

.review-quote {
  margin: 0.3rem 0 0.6rem;
  padding-left: 0.8rem;
  border-left: 2px solid var(--hair);
  color: var(--quiet);
}

.review-bar {
  margin-top: 1rem;
  padding-top: 0.8rem;
  border-top: 1px solid var(--hair);
}
```

- [ ] **Step 5: Check the script and the page tests**

Run: `node --check skills/presentation-studio/scripts/desk/app.js && python3 scripts/ci/run_tests.py test_desk test_page_app`
Expected: `OK`. Nothing draws the component yet, so behaviour is unchanged; the toolbar still says Approve at every stop with no marks.

- [ ] **Step 6: Commit**

```bash
git add skills/presentation-studio/scripts/desk/app.js skills/presentation-studio/scripts/desk/deck.css
git commit -m "Add the page's review component and its decision button"
```

---

### Task 8: The research plan stop on the page

**Files:**
- Modify: `skills/presentation-studio/scripts/desk/app.js` (`researchPlanPanel` near line 3309; `gatePanel`)
- Test: `tests/test_desk.py` (`ScreenTests`)

- [ ] **Step 1: Write the failing tests**

Add to `ScreenTests` in `tests/test_desk.py`:

```python
    def test_a_question_dropped_on_the_page_goes_with_the_approval(self):
        path = self.started(research=True)
        result = self.deck_screen(path, [
            {'snapshot': 'plan'}, {'click': 'Drop “Health checks”'}, {'snapshot': 'dropped'},
            {'click': 'Approve without 1 question'}],
            **{'POST /api/decide': [ok(self.run_of(path))]})
        plan = result['snapshots']['plan']
        for said in ('2\nquestions', 'Instance min', 'Searched for: rolling restart minimum '
                     'instances', 'Read the full plan'):
            self.assertIn(said, plan['text'])
        self.assertIn('1 dropped · 0 reworded · 0 added', result['snapshots']['dropped']['text'])
        (_, body), = self.posts(result)
        self.assertEqual((body['decision'], body['extra']),
                         ('approve', {'dropped': ['health-checks']}))
        self.post('decide', body)
        self.assertEqual(self.run_of(path)['gate']['name'], 'gate:research')

    def test_a_reworded_and_an_added_question_are_sent_as_changes(self):
        path = self.started(research=True)
        result = self.deck_screen(path, [
            {'click': 'Reword “Instance min”'},
            {'fill': 'New wording for “Instance min”',
             'value': 'How many instances keep capacity?'},
            {'fill': 'A question to add', 'value': 'What does a restart cost?'},
            {'click': 'Add the question'}, {'snapshot': 'marked'},
            {'click': 'Send 2 changes'}],
            **{'POST /api/decide': [ok(self.run_of(path))]})
        self.assertIn('Questions you added', result['snapshots']['marked']['text'])
        (_, body), = self.posts(result)
        self.assertNotIn('note', body)
        self.assertEqual((body['decision'], body['extra']), ('changes', {
            'dropped': [], 'reword': {'instance-min': 'How many instances keep capacity?'},
            'add': ['What does a restart cost?']}))
        self.post('decide', body)
        self.assertEqual(self.run_of(path)['gate']['round'], 2)
```

The `2\nquestions` check relies on the count strip's number and words being separate `span`s inside one `p`. If the harness joins them without a line break, assert `'2 questions'` instead.

- [ ] **Step 2: Run them to see them fail**

Run: `python3 scripts/ci/run_tests.py test_desk.ScreenTests`
Expected: FAIL: `Nothing on the page is named "Drop “Health checks”"`.

- [ ] **Step 3: Draw the plan as items**

Replace `researchPlanPanel` with:

```js
// The research plan: each question with the way to drop or reword it, and a box for one
// more. Drops go with Approve; rewording and new questions go back to be redrafted.
function researchPlanPanel(gate, readonly) {
  const node = card('The research plan');
  const questions = list(gate.questions);
  const searched = questions.filter((item) => item.search).length;
  add(node, reviewCounts([[questions.length, questions.length === 1 ? 'question'
    : 'questions'], [searched, 'searched on the web']]));
  if (!readonly) {
    add(node, make('p', '', 'Drop a question, or reword it. A drop takes effect when you '
      + 'approve; rewording and new questions go back to be redrafted, and come back here.'));
  }
  const items = make('ol', 'plain review-list');
  for (const item of questions) items.append(planRow(gate, item, readonly));
  add(node, items);
  if (!readonly) add(node, addedPart(gate), reviewBar(gate));
  return add(node, fullText('Read the full plan', 'The research plan', gate.text, 'plan-text'),
    ...gateSaid(gate));
}

function planRow(gate, item, readonly) {
  const held = chosenFor(gate);
  const title = item.title || item.id;
  const dropped = held.dropped.includes(item.id);
  const rewording = !dropped && owns(held.reword, item.id);
  const row = make('li', 'review-row' + (dropped ? ' review-off' : ''));
  add(row, make('p', 'row-title', title), make('p', '', item.question),
    item.search ? make('p', 'quiet', 'Searched for: ' + item.search) : null);
  if (readonly) return row;
  if (dropped) add(row, make('p', 'quiet', 'Dropped: it is not researched.'));
  if (rewording) {
    add(row, field('reword-' + item.id, 'New wording for “' + title + '”', held.reword,
      item.id, { long: true, limit: 1000, typed: () => reviewChanged(gate) }));
  }
  const redraw = (key) => {
    row.replaceWith(planRow(gate, item, false));
    reviewChanged(gate);
    focusKey(key);
  };
  const drop = capsule(dropped ? 'Keep' : 'Drop', 'quiet', () => {
    held.dropped = dropped ? held.dropped.filter((id) => id !== item.id)
      : [...held.dropped, item.id];
    delete held.reword[item.id];
    redraw('drop ' + item.id);
  }, 'drop ' + item.id);
  drop.setAttribute('aria-label', (dropped ? 'Keep “' : 'Drop “') + title + '”');
  const reword = dropped ? null : capsule(rewording ? 'Keep the wording' : 'Reword', 'quiet',
    () => {
      if (rewording) delete held.reword[item.id];
      else held.reword[item.id] = item.question;
      redraw(rewording ? 'reword ' + item.id : 'reword-' + item.id);
    }, 'reword ' + item.id);
  if (reword) {
    reword.setAttribute('aria-label', (rewording ? 'Keep the wording of “' : 'Reword “')
      + title + '”');
  }
  return add(row, add(make('div', 'bar'), drop, reword));
}
```

In `gatePanel`, pass `readonly` to both research panels:

```js
  if (gate.name === 'gate:research-plan') return researchPlanPanel(gate, readonly);
  if (gate.name === 'gate:research') return researchPanel(gate, readonly);
```

- [ ] **Step 4: Run the tests**

Run: `node --check skills/presentation-studio/scripts/desk/app.js && python3 scripts/ci/run_tests.py test_desk`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add skills/presentation-studio/scripts/desk/app.js tests/test_desk.py
git commit -m "Draw the research plan as questions to drop, reword or add"
```

---

### Task 9: The research findings stop on the page

**Files:**
- Modify: `skills/presentation-studio/scripts/desk/app.js` (`researchPanel` near line 3324)
- Test: `tests/test_desk.py`

- [ ] **Step 1: Write the failing test**

Add `unsettled` to `tests/test_desk.py` (the same helper as in `tests/test_engine.py`):

```python
def unsettled(workers, ident):
    """A research worker that leaves `ident` open and answers every other question."""
    def act(tools, job):
        if tools.job['finding'] != ident:
            return workers.question(tools, job)
        return tools.submit_finding(ident, 'insufficient', 'No page says.',
                                    headline='No page says what starts the next batch.',
                                    limits='Only one page was found.', evidence=[])
    return act
```

and the test to `ScreenTests`:

```python
    def test_findings_that_need_a_look_come_first_and_marks_go_as_changes(self):
        self.workers.then('question', unsettled(self.workers, 'health-checks'),
                          unsettled(self.workers, 'health-checks'))
        path = self.started(research=True)
        self.decided(path, 'gate:research-plan')
        self.assertEqual(self.run_of(path)['gate']['name'], 'gate:research')
        result = self.deck_screen(path, [
            {'snapshot': 'found'},
            {'click': 'Research “Health checks” again'},
            {'fill': 'What was wrong with “Health checks” (optional)',
             'value': 'Look for the platform docs.'},
            {'click': 'Instance min'}, {'click': 'Sources for “Instance min” (1)'},
            {'snapshot': 'opened'}, {'click': 'Leave out “Instance min”'},
            {'snapshot': 'marked'}, {'click': 'Send 2 changes'}],
            **{'POST /api/decide': [ok(self.run_of(path))]})
        found = result['snapshots']['found']['text']
        for said in ('Look at these first', 'Not settled',
                     'No page says what starts the next batch.',
                     'Not known: Only one page was found.', 'Answered', 'Read the full report'):
            self.assertIn(said, found)
        self.assertLess(found.index('Health checks'), found.index('Instance min'))
        opened = result['snapshots']['opened']
        self.assertIn(QUOTE, opened['text'])
        self.assertTrue(any(link['href'] == URL for link in opened['links']))
        self.assertIn('1 to research again · 1 left out · 0 added',
                      result['snapshots']['marked']['text'])
        (_, body), = self.posts(result)
        self.assertEqual((body['decision'], body['extra']), ('changes', {
            'left_out': ['instance-min'],
            'again': {'health-checks': 'Look for the platform docs.'}, 'add': []}))
```

Import `QUOTE` and `URL` from `runner_support` at the top of `tests/test_desk.py` if they are not imported already:

```python
from runner_support import QUOTE, URL
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 scripts/ci/run_tests.py test_desk.ScreenTests`
Expected: FAIL: `Nothing on the page is named "Research “Health checks” again"`.

- [ ] **Step 3: Draw the findings as items**

Replace `researchPanel` with:

```js
// What the research found: the findings that need a look first, as cards, and the answered
// ones a line each that opens into the same card. Each can be researched again or left out,
// and a question added.
function researchPanel(gate, readonly) {
  const node = card('What the research found');
  const items = list(gate.items);
  const settled = items.filter((item) => item.status === 'supported');
  const open = items.filter((item) => item.status !== 'supported');
  add(node, reviewCounts([[items.length, items.length === 1 ? 'question' : 'questions'],
    [settled.length, 'answered by the sources'], [open.length, 'to look at']]));
  if (open.length) {
    const cards = make('ul', 'plain review-list');
    for (const item of open) cards.append(findingCard(gate, item, readonly, false, false));
    add(node, make('h3', 'row-title', 'Look at these first'), cards);
  }
  if (settled.length) {
    const rows = make('ul', 'plain review-list');
    for (const item of settled) rows.append(findingCard(gate, item, readonly, true, false));
    add(node, make('h3', 'row-title', 'Answered'), rows);
  }
  if (!readonly && items.length) add(node, addedPart(gate), reviewBar(gate));
  return add(node, fullText('Read the full report', 'The research report', gate.text,
    'report-text'), ...gateSaid(gate));
}

// The quoted passages behind a finding, folded, each with where it came from.
function sourcesPart(item) {
  const sources = list(item.sources);
  if (!sources.length) return make('p', 'quiet', 'No passage is quoted for it.');
  const node = make('details', 'card-part');
  node.dataset.key = 'sources ' + item.id;
  const quotes = make('ul', 'plain review-sources');
  for (const one of sources) {
    quotes.append(add(make('li', ''), outLink(one.origin, one.title || one.origin
      || 'A source'), make('blockquote', 'review-quote', one.quote)));
  }
  return add(node, make('summary', '', 'Sources for “' + (item.title || item.id) + '” ('
    + sources.length + ')'), quotes);
}

function findingCard(gate, item, readonly, folded, opened) {
  const held = chosenFor(gate);
  const title = item.title || item.id;
  const out = leftOut(gate).includes(item.id);
  const again = !out && owns(held.again, item.id);
  const [shape, words] = FINDING_WORDS[item.status] || FINDING_WORDS.pending;
  const said = out ? 'Left out' : again ? 'To research again' : words;
  const body = [make('p', 'quiet', item.question),
    item.headline ? make('p', 'review-headline', item.headline) : null,
    item.unknown ? make('p', 'quiet', 'Not known: ' + item.unknown) : null,
    sourcesPart(item)];
  if (!readonly) {
    if (again) {
      body.push(field('again-' + item.id, 'What was wrong with “' + title + '” (optional)',
        held.again, item.id, { limit: 1000, typed: () => reviewChanged(gate) }));
    }
    const redraw = (key) => {
      row.replaceWith(findingCard(gate, item, false, folded, true));
      reviewChanged(gate);
      focusKey(key);
    };
    const leave = capsule(out ? 'Bring it back' : 'Leave out', 'quiet', () => {
      held.leftOut = out ? leftOut(gate).filter((id) => id !== item.id)
        : [...leftOut(gate), item.id];
      delete held.again[item.id];
      redraw('leave ' + item.id);
    }, 'leave ' + item.id);
    leave.setAttribute('aria-label', (out ? 'Bring back “' : 'Leave out “') + title + '”');
    const redo = out ? null : capsule(again ? 'Don’t research it again' : 'Research again',
      'quiet', () => {
        if (again) delete held.again[item.id];
        else held.again[item.id] = '';
        redraw(again ? 'again ' + item.id : 'again-' + item.id);
      }, 'again ' + item.id);
    if (redo) {
      redo.setAttribute('aria-label', again ? 'Don’t research “' + title + '” again'
        : 'Research “' + title + '” again');
    }
    body.push(add(make('div', 'bar'), redo, leave));
  }
  const row = make('li', 'review-row' + (out ? ' review-off' : ''));
  if (folded) {
    const fold = make('details', 'review-fold');
    fold.dataset.key = 'finding ' + item.id;
    fold.open = Boolean(opened);
    const top = make('summary', '', title);
    top.setAttribute('aria-label', title);
    return add(row, add(fold, add(top, ' · ', said, ' · ', count(list(item.sources).length,
      'source', 'sources')), ...body));
  }
  return add(row, add(make('div', 'review-top'), make('p', 'row-title', title),
    state(out ? 'off' : again ? 'review' : shape, said)), ...body);
}
```

The summary's `aria-label` is the title alone, so a test can open it by the title ("Instance min").

- [ ] **Step 4: Run the tests**

Run: `node --check skills/presentation-studio/scripts/desk/app.js && python3 scripts/ci/run_tests.py test_desk`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add skills/presentation-studio/scripts/desk/app.js tests/test_desk.py
git commit -m "Draw the research findings as what needs a look first"
```

---

### Task 10: The outline stop on the page

**Files:**
- Modify: `skills/presentation-studio/scripts/desk/app.js` (`outlineRow`, `outlineEdited`, `outlinePanel`, the title field's `typed`)
- Test: `tests/test_desk.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_a_slide_marked_on_the_page_is_sent_with_what_should_change(self):
        path = self.started()
        second = self.run_of(path)['gate']['slides'][1]
        result = self.deck_screen(path, [
            {'snapshot': 'outline'},
            {'click': f"Ask for changes to “{second['title']}”"},
            {'fill': f"What should change on “{second['title']}”", 'value': 'Split it in two.'},
            {'snapshot': 'marked'}, {'click': 'Send 1 change'}],
            **{'POST /api/decide': [ok(self.run_of(path))]})
        self.assertIn('Points and notes', result['snapshots']['outline']['text'])
        self.assertIn('1 slide to change', result['snapshots']['marked']['text'])
        (_, body), = self.posts(result)
        self.assertEqual((body['decision'], body['extra']),
                         ('changes', {'slides': {second['id']: 'Split it in two.'}}))
        self.post('decide', body)
        self.assertIn(f"- Slide `{second['id']}`: Split it in two.",
                      self.workers.of('outline')[-1].task)
```

- [ ] **Step 2: Run it to see it fail**

Run: `python3 scripts/ci/run_tests.py test_desk.ScreenTests`
Expected: FAIL: `Nothing on the page is named "Ask for changes to “…”"`.

- [ ] **Step 3: Compact rows with a mark each**

In `outlineRow`, replace everything from `for (const text of [one.subtitle, one.understand])` to the line before `if (readonly) return node;` with:

```js
  if (one.understand) add(node, make('p', 'outline-said', one.understand));
  const points = list(one.points).filter((point) => point && (point.label || point.text));
  const more = [one.subtitle ? make('p', 'outline-said', one.subtitle) : null,
    points.length ? bullets(points.map((point) => (point.label && point.text
      ? point.label + ': ' + point.text : point.label || point.text)), 'outline-points') : null,
    one.notes ? make('p', 'outline-notes quiet', 'Notes: ' + one.notes) : null]
    .filter(Boolean);
  if (more.length) {
    const fold = make('details', 'card-part');
    fold.dataset.key = 'slide-more ' + one.id;
    const top = make('summary', '', 'Points and notes');
    top.setAttribute('aria-label', 'Points and notes of slide ' + (index + 1));
    add(node, add(fold, top, ...more));
  }
```

Then, after `if (readonly) return node;`, add the mark before the move buttons:

```js
  const held = chosenFor(gate);
  const asking = owns(held.slideNotes, one.id);
  if (asking) {
    add(node, field('slide-note-' + one.id, 'What should change on “' + title + '”',
      held.slideNotes, one.id, { limit: 1000, typed: () => reviewChanged(gate) }));
  }
  const ask = capsule(asking ? 'Keep it as it is' : 'Ask for changes', 'quiet', () => {
    if (asking) delete held.slideNotes[one.id];
    else held.slideNotes[one.id] = '';
    paintOutline(gate, byId('outline-list'), byId('outline-said'));
    reviewChanged(gate);
    focusKey(asking ? 'slide-ask ' + one.id : 'slide-note-' + one.id);
  }, 'slide-ask ' + one.id);
  ask.setAttribute('aria-label', asking ? 'Keep “' + title + '” as it is'
    : 'Ask for changes to “' + title + '”');
```

and put `ask` first in the row's bar:

```js
  return add(node, add(make('div', 'bar'), ask, up, down, remove));
```

In the title field's `typed` handler, and at the end of `outlineEdited`, call `reviewChanged(gate)` so the tally and the button follow edits:

```js
      { limit: 300, typed: () => {
        chosenFor(gate).edited = true;
        paintOutlineSaid(gate, byId('outline-said'));
        reviewChanged(gate);
      } }));
```

```js
function outlineEdited(gate) {
  chosenFor(gate).edited = true;
  paintOutline(gate, byId('outline-list'), byId('outline-said'));
  reviewChanged(gate);
}
```

(Keep any other lines `outlineEdited` already has.)

In `outlinePanel`, add `reviewBar(gate)` after the add-a-slide form when not readonly, and say what a mark does in its first paragraph:

```js
  add(node, make('p', '', count(slides.length, 'slide', 'slides') + ', each with its title '
    + 'and what it must make clear; its points and notes open under it.' + (readonly ? ''
    : ' Retitle, move, add or remove slides here, or ask for changes to one; your edits go '
      + 'with your decision.')));
```

```js
  if (!readonly) add(node, reviewBar(gate));
```

- [ ] **Step 4: Run the tests**

Run: `node --check skills/presentation-studio/scripts/desk/app.js && python3 scripts/ci/run_tests.py test_desk`
Expected: `OK`. The older outline tests (`test_a_slide_added_and_moved_on_the_page_...`, `..._carries_its_notes`) still pass: notes are in the snapshot's text even when folded, and the title fields stay in view.

- [ ] **Step 5: Commit**

```bash
git add skills/presentation-studio/scripts/desk/app.js tests/test_desk.py
git commit -m "Draw the outline as compact rows with a change mark each"
```

---

### Task 11: Say how the stops work now, and run everything

**Files:**
- Modify: `README.md` ("What you do at each step")
- Modify: `docs/runner.md` ("Make a deck")
- Modify: `docs/superpowers/specs/2026-10-15-reviewing-stops-design.md` (status, the research-again line)

- [ ] **Step 1: README**

In "What you do at each step", replace items 2 and 3 with:

```markdown
2. **Research plan and research** (only if you turned research on). Each question is a line you can drop or reword, and you can add one. The findings that need a look come first, each with a one-sentence answer, what is not known and its sources; research any of them again, leave one out of the outline, or add a question. The full report is a click away.
3. **Outline.** A title and what each slide must make clear, with its points and notes a click away. You can reorder, add and remove slides, and ask for changes to any one of them.
```

- [ ] **Step 2: Runner docs**

In `docs/runner.md`, after the paragraph that begins "At each stop the page shows what was made", add:

```markdown
**The research and the outline, item by item.** The research plan, the findings and the outline are lists to mark: drop or reword a question, research a finding again or leave it out, ask for changes to one slide, add a question. Nothing is sent until you press the button at the foot of the list, which says what it will do: **Approve** when nothing is marked; **Approve without 2 questions** (or **Approve, leaving out 1**) when what you marked needs no assistant, which is applied and approved in one click; **Send 3 changes** when something must be redone, which comes back to you. The full plan and report stay a click away.
```

- [ ] **Step 3: The spec**

In the spec, change `Status: agreed design, not built.` to `Status: built.`, and in "What changes in the runner", change "an empty line" to "an empty line for a slide or a rewording (a line to research again with may be empty)".

- [ ] **Step 4: Check the package and the whole suite**

Run: `python3 skills/presentation-studio/scripts/validate_package.py && python3 scripts/ci/run_tests.py`
Expected: `ok`, then `OK`. Fix anything that fails before going on.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/runner.md docs/superpowers/specs/2026-10-15-reviewing-stops-design.md
git commit -m "Say how the research and outline stops are reviewed item by item"
```

---

## After the plan

- Try it on the page with `PRESENTATION_STUDIO_FAKE=1 python3 runner/studio.py serve --fake --open`, from a terminal of your own (the page's key is shown only to a person): start a deck with research on and walk the plan, the findings and the outline.
- A release raises `VERSION` in both places; this work changes no conversation guidance, so `minimum_runtime` stays.
