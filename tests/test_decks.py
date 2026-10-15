import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from runner import decks, gitstate
from workspace import WorkspaceError

BRANDS = [{'brand': 'acme', 'variants': ['light']},
          {'brand': 'globex', 'variants': ['light', 'dark']}]


def form(**over):
    sent = {'route': 'scratch', 'title': 'Spring AI on Acme', 'audience': 'Platform teams',
            'goal': 'Show the path to production', 'brand': 'acme', 'variant': 'light',
            'output': 'google', 'research': False}
    sent.update(over)
    return sent


UPLOAD = {'kind': 'upload', 'name': 'a.pptx'}


class FormTests(unittest.TestCase):
    def test_scratch_form(self):
        checked = decks.check_form(form(), BRANDS)
        self.assertEqual(checked['route'], 'scratch')
        self.assertEqual(checked['output'], 'google')

    def test_a_brand_with_no_variants_takes_none(self):
        brands = [{'brand': 'plain', 'variants': []}]
        for variant in (None, ''):
            checked = decks.check_form(form(brand='plain', variant=variant), brands)
            self.assertIsNone(checked['variant'])
        with self.assertRaisesRegex(WorkspaceError, 'has no "dark" variant'):
            decks.check_form(form(brand='plain', variant='dark'), brands)

    def test_unknown_route(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='video'), BRANDS)

    def test_existing_needs_a_level(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='existing', source=UPLOAD), BRANDS)

    def test_selected_needs_what_to_change(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='existing', level='selected', source=UPLOAD), BRANDS)

    def test_selected_keeps_its_text(self):
        checked = decks.check_form(form(route='existing', level='selected', source=UPLOAD,
                                        selected='Slide 3: shorter'), BRANDS)
        self.assertEqual(checked['selected'], 'Slide 3: shorter')

    def test_no_research_for_existing(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='existing', level='polish', research=True,
                                  source=UPLOAD), BRANDS)

    def test_unknown_variant(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(variant='dark'), BRANDS)

    def test_unknown_brand(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(brand='nope'), BRANDS)

    def test_title_limit(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(title='x' * 121), BRANDS)

    def test_missing_title(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(title='  '), BRANDS)

    def test_document_needs_a_source_and_keeps_only_a_reference(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='document'), BRANDS)
        checked = decks.check_form(form(route='document',
                                        source={'kind': 'paste', 'text': 'secret body'}), BRANDS)
        self.assertEqual(checked['source'], {'kind': 'paste'})

    def test_existing_refuses_pasted_source(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='existing', level='polish',
                                  source={'kind': 'paste', 'text': 'x'}), BRANDS)

    def test_minutes(self):
        self.assertEqual(decks.check_form(form(minutes='30'), BRANDS)['minutes'], 30)
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(minutes=241), BRANDS)


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.space = gitstate.local(Path(tempfile.mkdtemp()) / 'ws')

    def test_create_writes_intake_run_and_readme(self):
        root = decks.create(self.space, decks.check_form(form(), BRANDS))
        self.assertEqual(root.name, 'spring-ai-on-acme')
        run = decks.read_run(root)
        self.assertEqual(run['route'], 'scratch')
        self.assertIn('# Spring AI on Acme', (root / 'README.md').read_text())
        self.assertIn('Platform teams', (root / 'intake.md').read_text())

    def test_create_commits(self):
        root = decks.create(self.space, decks.check_form(form(), BRANDS))
        self.assertTrue(gitstate.known(self.space, root))
        self.assertEqual(gitstate.changed(self.space), [])

    def test_same_title_twice_gets_a_new_id(self):
        first = decks.create(self.space, decks.check_form(form(), BRANDS))
        second = decks.create(self.space, decks.check_form(form(), BRANDS))
        self.assertEqual(second.name, first.name + '-2')

    def test_run_round_trip(self):
        root = decks.create(self.space, decks.check_form(form(), BRANDS))
        run = decks.read_run(root)
        run['gates']['outline'] = {'state': 'waiting', 'round': 1}
        decks.write_run(root, run)
        self.assertEqual(decks.read_run(root)['gates']['outline']['state'], 'waiting')

    def test_index_lists_decks(self):
        decks.create(self.space, decks.check_form(form(), BRANDS))
        decks.write_index(self.space)
        self.assertIn('Spring AI on Acme', (self.space.root / 'README.md').read_text())


class DeliveredTests(unittest.TestCase):
    def setUp(self):
        self.space = gitstate.local(Path(tempfile.mkdtemp()) / 'ws')
        self.root = decks.create(self.space, decks.check_form(form(), BRANDS))
        self.run = decks.read_run(self.root)

    def test_readme_shows_the_google_link(self):
        text = decks.readme(self.run, {'output': 'google', 'url': 'https://slides.example/x',
                                       'fileId': 'x', 'pptx': None, 'revision': 1, 'at': 't'})
        self.assertIn('https://slides.example/x', text)
        self.assertIn('finished', text)

    def test_readme_shows_the_pptx_name(self):
        text = decks.readme(self.run, {'output': 'pptx', 'url': None, 'fileId': None,
                                       'pptx': 'talk.pptx', 'revision': 1, 'at': 't'})
        self.assertIn('talk.pptx', text)

    def test_index_and_state_follow_deliver_json(self):
        self.assertEqual(decks.state(self.run, self.root), 'in progress')
        (self.root / decks.DELIVER).write_text(json.dumps(
            {'output': 'google', 'url': 'https://slides.example/x', 'fileId': 'x',
             'pptx': None, 'revision': 1, 'at': 't'}))
        self.assertEqual(decks.state(self.run, self.root), 'finished')
        row = decks.index(self.space)
        self.assertIn('https://slides.example/x', row)
        self.assertIn('spring-ai-on-acme/README.md', row)
        self.assertIn('finished', row)

    def test_index_for_pptx(self):
        (self.root / decks.DELIVER).write_text(json.dumps({'output': 'pptx', 'pptx': 'a.pptx'}))
        self.assertIn('PowerPoint file', decks.index(self.space))
