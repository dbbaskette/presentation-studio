"""Outline steps: which brief each route gets, the rules that hold a redesign to the deck's
own words, and the person's edits. Nothing here starts the slides tool."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import runner_support
from runner_support import Brand, Slides
from workspace import WorkspaceError

from runner import briefs, decks, worker_tools
from runner.steps import outline

INVENTORY = {'sha256': 'x', 'source': 'deck.pptx', 'slides': [
    {'number': 1, 'id': '256', 'title': 'Run Acme fast', 'hidden': False, 'objects': [
        {'id': '2', 'type': 'text', 'text': 'Run Acme fast', 'runs': ['Run Acme fast']},
        {'id': '3', 'type': 'text', 'text': 'One   batch\nat a time',
         'runs': ['One batch', ' at a time']}]},
    {'number': 2, 'id': '257', 'title': 'Why', 'hidden': False, 'objects': [
        {'id': '2', 'type': 'text', 'text': 'Why', 'runs': ['Why']},
        {'id': '3', 'type': 'text', 'text': 'Capacity holds', 'runs': ['Capacity holds']}]}]}


def content(ident, title, number, label='Capacity holds'):
    return {'id': ident, 'kind': 'content', 'title': title, 'understand': 'It holds.',
            'relation': 'none', 'points': [{'label': label, 'text': 'Capacity holds'}], 'notes': 'Say it.',
            'sources': [f'slide-{number}']}


def extracted(title='Run Acme fast'):
    return {'version': 1, 'title': 'Deck', 'slides': [
        content('first-slide', title, 1, 'One batch at a time'),
        content('second-slide', 'Why', 2)]}


class Case(unittest.TestCase):
    def deck(self, route='scratch', level=None, classified=None, inventory=True):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        self.run_ = {'schema': 1, 'id': 'd', 'title': 'Restarts', 'route': route,
                     'form': {'route': route, 'level': level, 'audience': 'Ops',
                              'goal': 'Teach', 'research': False},
                     'gates': {}, 'steps': {}, 'classified': classified}
        decks.write_run(self.root, self.run_)
        if inventory:
            (self.root / 'classify.json').write_text(json.dumps(INVENTORY))
        self.slides, self.brand = Slides(), Path('/brand/contract.json')
        return self.root, self.run_


class BriefTests(Case):
    def work(self, **kind):
        root, run = self.deck(**kind)
        return outline.outline_work(root, run, None, None, self.brand, slides=self.slides)

    def test_each_route_gets_its_own_brief(self):
        for kind, brief in (({'route': 'scratch'}, 'outline-brief'),
                            ({'route': 'document', 'classified': 'spec'}, 'outline-spec'),
                            ({'route': 'document', 'classified': 'material'}, 'outline-material'),
                            ({'route': 'existing', 'level': 'rework'}, 'restructure')):
            work = self.work(**kind)
            self.assertEqual(work.guidance, briefs.guidance(brief), brief)
            self.assertEqual(work.name, 'outline')
            self.assertEqual(work.prepared['artifacts']['outline']['kind'], 'outline')

    def test_a_second_round_carries_the_persons_note_and_the_last_error(self):
        root, run = self.deck()
        run['gates']['gate:outline'] = {'note': 'Fewer slides please'}
        (root / 'outline.json').write_text(json.dumps(extracted()))
        work = outline.outline_work(root, run, None, 'It was not JSON.', self.brand,
                                    slides=self.slides)
        self.assertIn('Fewer slides please', work.task)
        self.assertIn('It was not JSON.', work.task)
        self.assertIn('The current outline', work.prepared['inputs'])

    def test_extract_takes_the_level_and_the_rules_that_level_has(self):
        for level, counted in (('brand-only', True), ('polish', True), ('redesign', False),
                               ('rework', False)):
            root, run = self.deck('existing', level)
            work = outline.extract_work(root, run, None, None, self.brand, slides=self.slides)
            self.assertEqual(work.guidance, briefs.guidance('extract', level=level))
            rules = work.prepared['artifacts']['outline']['rules']
            self.assertEqual(len(rules), 2 if counted else 1, level)
            self.assertIn('Capacity holds', work.prepared['inputs']['Inventory'])


class RuleTests(Case):
    def test_verbatim_passes_copied_text_and_refuses_a_changed_word(self):
        rule = outline.verbatim_rule(INVENTORY)
        self.assertEqual(rule(extracted()), [])
        said = rule(extracted('Run Acme faster'))
        self.assertEqual(len(said), 1)
        self.assertIn('Slide 1 (first-slide)', said[0])
        self.assertIn('Run Acme faster', said[0])

    def test_verbatim_ignores_whitespace_and_reads_joined_runs(self):
        outline_ = extracted()
        outline_['slides'][0]['points'][0]['label'] = 'One batch  at a\ntime'
        self.assertEqual(outline.verbatim_rule(INVENTORY)(outline_), [])

    def test_the_writers_own_lines_are_not_compared(self):
        outline_ = extracted()
        outline_['slides'][0]['understand'] = 'Something new.'
        outline_['slides'][0]['notes'] = 'Say something new.'
        outline_['slides'][0]['focal'] = 'Something new'
        self.assertEqual(outline.verbatim_rule(INVENTORY)(outline_), [])

    def test_count_rule_refuses_a_dropped_slide_for_polish_only(self):
        rule = outline.count_rule(INVENTORY, 'polish')
        self.assertEqual(rule(extracted()), [])
        dropped = extracted()
        del dropped['slides'][1]
        self.assertIn('2 slides and the outline has 1', ' '.join(rule(dropped)))
        swapped = extracted()
        swapped['slides'].reverse()
        self.assertEqual(len(rule(swapped)), 2)
        self.assertIsNone(outline.count_rule(INVENTORY, 'redesign'))
        self.assertIsNone(outline.count_rule(INVENTORY, 'rework'))

    def test_both_rules_survive_the_trip_across_a_process(self):
        for rule in (outline.verbatim_rule(INVENTORY), outline.count_rule(INVENTORY, 'polish')):
            kept = json.loads(json.dumps(worker_tools.reference(rule)))
            again = worker_tools.rules_of({'rules': [kept]})[0]
            self.assertEqual(again(extracted()), rule(extracted()))


class HandedBackTests(Case):
    def test_an_outline_with_one_changed_word_is_refused_with_the_slide_named(self):
        root, run = self.deck('existing', 'redesign')
        work = outline.extract_work(root, run, None, None, self.brand, slides=self.slides)
        job = root / 'job'
        worker_tools.prepare(job, **work.prepared)
        tools = worker_tools.WorkerTools(job, slides=self.slides)
        ok, said = tools.submit_outline(json.dumps(extracted('Run Acme faster')))
        self.assertFalse(ok)
        self.assertIn('Slide 1 (first-slide)', said)
        self.assertEqual(tools.submit_outline(json.dumps(extracted())), (True, 'Accepted: outline.'))
        # the second try's task carries the sentence
        retry = outline.extract_work(root, run, None, said, self.brand, slides=self.slides)
        self.assertIn('Slide 1 (first-slide)', retry.task)


class KeepTests(Case):
    def test_keeping_writes_both_files_and_opens_the_gate_where_there_is_one(self):
        root, run = self.deck('scratch')
        outline.keep_outline(root, run, json.dumps(extracted()))
        self.assertEqual(json.loads((root / 'outline.json').read_text())['title'], 'Deck')
        text = (root / 'outline.md').read_text()
        self.assertIn('## 1. Run Acme fast', text)
        self.assertIn('Understand: It holds.', text)
        self.assertEqual(decks.read_run(root)['gates']['gate:outline']['state'], 'waiting')

    def test_a_route_without_the_gate_gets_none(self):
        root, run = self.deck('existing', 'polish')
        outline.keep_outline(root, run, extracted())
        self.assertNotIn('gate:outline', decks.read_run(root)['gates'])

    def test_a_rework_read_in_by_extract_waits_for_the_outline_step(self):
        root, run = self.deck('existing', 'rework')
        outline.keep_outline(root, run, extracted(), extracted=True)
        self.assertNotIn('gate:outline', decks.read_run(root)['gates'])
        outline.keep_outline(root, run, extracted())
        self.assertEqual(decks.read_run(root)['gates']['gate:outline']['state'], 'waiting')


class EditTests(Case):
    def test_reordering_two_slides_is_saved_and_the_readable_copy_follows(self):
        root, run = self.deck('scratch')
        outline.keep_outline(root, run, extracted())
        edited = list(reversed(json.loads((root / 'outline.json').read_text())['slides']))
        outline.apply_edits(root, run, edited, self.slides, self.brand)
        text = (root / 'outline.md').read_text()
        self.assertLess(text.index('## 1. Why'), text.index('## 2. Run Acme fast'))
        self.assertEqual([s['id'] for s in json.loads((root / 'outline.json').read_text())['slides']],
                         ['second-slide', 'first-slide'])

    def test_a_refusal_comes_back_as_a_sentence_and_nothing_is_written(self):
        root, run = self.deck('scratch')
        outline.keep_outline(root, run, extracted())
        before = (root / 'outline.json').read_text()
        edited = copy.deepcopy(extracted()['slides'])
        del edited[0]['notes']
        with self.assertRaisesRegex(WorkspaceError, 'first-slide: It has no notes'):
            outline.apply_edits(root, run, edited, self.slides, self.brand)
        self.slides.refuse['outline_check'] = ['Use outline version 1.']
        with self.assertRaisesRegex(WorkspaceError, 'version 1'):
            outline.apply_edits(root, run, extracted()['slides'], self.slides, self.brand)
        self.assertEqual((root / 'outline.json').read_text(), before)


if __name__ == '__main__':
    unittest.main()
