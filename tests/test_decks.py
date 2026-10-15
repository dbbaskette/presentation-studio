import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from runner import decks, gitstate
from workspace import WorkspaceError

BRANDS = [{'brand': 'tanzu', 'variants': ['light']},
          {'brand': 'vmware', 'variants': ['light', 'dark']}]


def form(**over):
    sent = {'route': 'scratch', 'title': 'Spring AI on Tanzu', 'audience': 'Platform teams',
            'goal': 'Show the path to production', 'brand': 'tanzu', 'variant': 'light',
            'output': 'google', 'research': False}
    sent.update(over)
    return sent


UPLOAD = {'kind': 'upload', 'name': 'a.pptx'}


class FormTests(unittest.TestCase):
    def test_scratch_form(self):
        checked = decks.check_form(form(), BRANDS)
        self.assertEqual(checked['route'], 'scratch')
        self.assertEqual(checked['output'], 'google')

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
        self.assertEqual(root.name, 'spring-ai-on-tanzu')
        run = decks.read_run(root)
        self.assertEqual(run['route'], 'scratch')
        self.assertIn('# Spring AI on Tanzu', (root / 'README.md').read_text())
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
        self.assertIn('Spring AI on Tanzu', (self.space.root / 'README.md').read_text())
