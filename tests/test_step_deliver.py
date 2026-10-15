"""Delivering a deck, and asking for changes after it is delivered. The slides tool is the
stand-in: what it keeps "in Drive" is its `files`."""
import json
import tempfile
import unittest
from pathlib import Path

import runner_support
from workspace import WorkspaceError

from runner import decks, stages
from runner.steps import build, deliver


class Case(unittest.TestCase):
    output = 'google'

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.space = Path(holder.name).resolve() / 'presentations'
        self.root = self.space / 'restarts'
        self.root.mkdir(parents=True)
        self.run_ = {'schema': 1, 'id': 'restarts', 'title': 'Rolling restarts',
                     'route': 'scratch',
                     'form': {'route': 'scratch', 'title': 'Rolling restarts',
                              'brand': 'example', 'variant': 'light', 'output': self.output},
                     'gates': {'gate:build': {'state': 'approved'}}, 'steps': {},
                     'revisions': [], 'halted': None}
        decks.write_run(self.root, self.run_)
        deck = self.root / build.DECK
        deck.parent.mkdir(parents=True)
        deck.write_bytes(b'PK\x03\x04 a rendered deck')
        self.slides = runner_support.stand_in_slides()
        self.tool = self.slides.run

    def imports(self) -> int:
        return sum(call[:2] == ['drive', 'import'] for call in self.tool.calls)


class GoogleTests(Case):
    def test_google_makes_a_slides_file_and_records_its_link(self):
        record = deliver.deliver(self.root, self.run_, self.slides)
        self.assertEqual(record['output'], 'google')
        self.assertTrue(record['fileId'] and record['url'])
        self.assertIsNone(record['pptx'])
        self.assertNotIn('notice', record)
        self.assertEqual(json.loads((self.root / decks.DELIVER).read_text()), record)
        run = decks.read_run(self.root)
        self.assertEqual(run['revisions'], [{'revision': 1, 'at': record['at'],
                                             'url': record['url']}])
        self.assertIn(record['url'], (self.root / 'README.md').read_text())
        self.assertIn(record['url'], (self.space / 'README.md').read_text())
        self.assertEqual(self.tool.files[record['fileId']]['name'], 'Rolling restarts')

    def test_without_google_the_deck_is_a_powerpoint_file(self):
        self.tool.drive = False
        record = deliver.deliver(self.root, self.run_, self.slides)
        self.assertEqual(record['output'], 'pptx')
        self.assertEqual(record['notice'], deliver.NOT_CONNECTED)
        self.assertEqual(record['notice'],
                         "Google isn't connected, so this deck was made as a PowerPoint file.")
        self.assertEqual(record['pptx'], 'work/deck.pptx')
        self.assertIsNone(record['url'])
        self.assertEqual(self.imports(), 0)
        self.assertIn('PowerPoint file', (self.space / 'README.md').read_text())
        self.assertEqual(decks.read_run(self.root)['revisions'][0]['pptx'], 'work/deck.pptx')

    def test_a_deck_not_rendered_is_refused(self):
        (self.root / build.DECK).unlink()
        with self.assertRaises(WorkspaceError):
            deliver.deliver(self.root, self.run_, self.slides)
        self.assertFalse((self.root / decks.DELIVER).exists())


class PowerPointTests(Case):
    output = 'pptx'

    def test_pptx_asks_nothing_of_google(self):
        record = deliver.deliver(self.root, self.run_, self.slides)
        self.assertEqual((record['output'], record['pptx']), ('pptx', 'work/deck.pptx'))
        self.assertNotIn('notice', record)
        self.assertEqual([call for call in self.tool.calls if call != ['--version']], [])


class AgainTests(Case):
    def test_changes_after_delivery_make_a_new_file_when_the_old_one_is_gone(self):
        """Review Focus 3."""
        for step in stages.steps(self.run_):
            if step.kind == 'gate':
                self.run_['gates'][step.name] = {'state': 'approved'}
            else:
                self.run_['steps'][step.name] = {'done': True}
        first = deliver.deliver(self.root, self.run_, self.slides)
        run = deliver.again(self.root, decks.read_run(self.root), self.slides,
                            'Make the cover calmer.')
        self.assertEqual(run['gates']['gate:build']['state'], 'changes')
        self.assertEqual(run['gates']['gate:build']['note'], 'Make the cover calmer.')
        self.assertFalse(run['steps'].get('deliver', {}).get('done'))
        self.assertFalse((self.root / decks.DELIVER).exists())
        self.assertEqual(decks.state(run, self.root), 'changes asked at gate:build')
        self.assertEqual(stages.survey(run).next.name, 'build-sections')
        # The person deleted the first file in Drive: the slides tool reports it missing.
        self.tool.gone.add(first['fileId'])
        run['gates']['gate:build'] = {'state': 'approved'}
        second = deliver.deliver(self.root, run, self.slides)
        self.assertEqual(self.imports(), 2)
        self.assertNotEqual(second['fileId'], first['fileId'])
        self.assertEqual(second['revision'], 2)
        self.assertEqual(json.loads((self.root / decks.DELIVER).read_text())['url'],
                         second['url'])
        self.assertEqual(self.tool.files[second['fileId']]['name'],
                         'Rolling restarts (revision 2)')
        kept = decks.read_run(self.root)['revisions']
        self.assertEqual([entry['url'] for entry in kept], [first['url'], second['url']])
        self.assertIn(second['url'], (self.space / 'README.md').read_text())
        self.assertNotIn(first['url'], (self.space / 'README.md').read_text())

    def test_again_has_every_section_drawn_with_the_note(self):
        build.write_state(self.root, {**build.EMPTY, 'start': {
            'folder': 'work/build/start', 'brand': 'b', 'sections': [
                {'id': 'section-1', 'file': 'section-1.json', 'slides': ['a']},
                {'id': 'section-2', 'file': 'section-2.json', 'slides': ['b']}]},
            'sections': {'section-1': {'file': 'x', 'round': 0},
                         'section-2': {'file': 'y', 'round': 0}},
            'rounds': [{'slides': []}], 'repaired': 2})
        self.assertEqual(build.to_draw(self.root), [])
        deliver.deliver(self.root, self.run_, self.slides)
        deliver.again(self.root, decks.read_run(self.root), self.slides, 'Calmer.')
        self.assertEqual(build.to_draw(self.root), ['section-1', 'section-2'])
        self.assertEqual(build.read_state(self.root)['repaired'], 0)

    def test_again_needs_a_note_and_a_delivered_deck(self):
        with self.assertRaises(WorkspaceError):
            deliver.again(self.root, self.run_, self.slides, 'Calmer.')
        deliver.deliver(self.root, self.run_, self.slides)
        with self.assertRaises(WorkspaceError):
            deliver.again(self.root, decks.read_run(self.root), self.slides, '  ')


if __name__ == '__main__':
    unittest.main()
