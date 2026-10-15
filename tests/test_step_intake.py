"""Intake: documents taken in, the classifier's job and verdict, and the person's correction.
Nothing here starts gcloud or reaches the network."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import runner_support  # noqa: F401  puts the runner on the import path
from workspace import WorkspaceError

import gdrive
from runner import decks, documents, stages, worker_tools
from runner.steps import Work, intake


class Drive:
    def __init__(self, text):
        self.text, self.asked = text, []

    def export_text(self, ident):
        self.asked.append(ident)
        return self.text


class IntakeCase(unittest.TestCase):
    def deck(self, route='document', research=False):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        run = {'schema': 1, 'id': 'd', 'title': 'Restarts', 'route': route,
               'form': {'route': route, 'research': research, 'audience': 'Ops', 'goal': 'Teach'},
               'gates': {}, 'steps': {}, 'classified': None}
        decks.write_run(root, run)
        return root, run


class TakeTests(IntakeCase):
    def test_upload_is_kept_and_readable(self):
        root, _ = self.deck()
        entry = intake.take_document(root, {'kind': 'upload', 'name': 'notes.md',
                                            'data': b'# Notes\n\nHello.\n'})
        self.assertTrue(entry['readable'])
        self.assertIn('Hello', documents.text_of(root, entry))

    def test_paste_is_kept_as_pasted_text(self):
        root, _ = self.deck()
        entry = intake.take_document(root, {'kind': 'paste', 'text': 'Some notes.'})
        self.assertEqual(entry['name'], 'pasted-text.md')

    def test_google_link_is_exported(self):
        root, _ = self.deck()
        drive = Drive('Rolling restarts\n')
        entry = intake.take_document(
            root, {'kind': 'google', 'link': 'https://docs.google.com/document/d/AbC_1/edit'},
            drive=drive)
        self.assertEqual(drive.asked, ['AbC_1'])
        self.assertIn('Rolling', documents.text_of(root, entry))

    def test_missing_gcloud_names_the_sign_in(self):
        root, _ = self.deck()
        drive = gdrive.Drive(run=mock.Mock(side_effect=FileNotFoundError()))
        with self.assertRaises(WorkspaceError) as caught:
            intake.take_document(root, {'kind': 'google', 'link': 'AbC_1'}, drive=drive)
        self.assertIn('gcloud auth login --enable-gdrive-access', str(caught.exception))

    def test_unreadable_document_is_refused_with_why(self):
        root, _ = self.deck()
        with self.assertRaises(WorkspaceError) as caught:
            intake.take_document(root, {'kind': 'upload', 'name': 'broken.docx',
                                        'data': b'not a zip'})
        self.assertIn('broken.docx', str(caught.exception))
        self.assertEqual(documents.listed(root), [])


class VerdictTests(IntakeCase):
    def check(self, **given):
        return intake.check_classification(json.dumps(given), {})[0]

    def test_spec_with_slides(self):
        self.assertEqual(self.check(kind='spec', reason='Slide headings.', slides=12), [])

    def test_material_without_slides(self):
        self.assertEqual(self.check(kind='material', reason='Notes.', slides=None), [])

    def test_spec_without_slides_is_refused(self):
        self.assertTrue(self.check(kind='spec', reason='Slide headings.', slides=None))

    def test_unknown_kind_is_refused(self):
        self.assertTrue(self.check(kind='essay', reason='x', slides=None))

    def test_registered_for_workers(self):
        self.assertIs(worker_tools.VALIDATORS['classify'], intake.check_classification)

    def test_work(self):
        root, run = self.deck()
        intake.take_document(root, {'kind': 'paste', 'text': 'Some notes.'})
        work = intake.classify_work(root, run, None, 'It timed out.')
        self.assertIsInstance(work, Work)
        self.assertEqual(work.name, 'classification')
        self.assertEqual(work.prepared['artifacts'], {'classification': {'kind': 'classify'}})
        self.assertEqual([t.strip() for t in work.prepared['inputs'].values()], ['Some notes.'])
        self.assertIn('It timed out.', work.task)
        worker_tools.prepare(root / 'job', **work.prepared)

    def test_keep_writes_the_note_the_gate_and_the_record(self):
        root, run = self.deck()
        intake.keep_classification(root, run, {'kind': 'spec', 'reason': 'Slide headings.',
                                               'slides': 12})
        note = (root / 'classify.md').read_text()
        self.assertIn('spec', note)
        self.assertIn('12', note)
        self.assertEqual(run['gates']['gate:classify'], {'state': 'waiting', 'round': 1})
        self.assertEqual(decks.read_run(root)['classified'], 'spec')


class CorrectionTests(IntakeCase):
    def test_correction_switches_branch_and_keeps_the_document(self):
        root, run = self.deck(route='document', research=True)
        intake.take_document(root, {'kind': 'paste', 'text': '- a\n- b\n- c\n- d\n- e\n'})
        intake.keep_classification(root, run, {'kind': 'material', 'reason': 'Short notes.',
                                               'slides': None})
        self.assertIn('research', [s.name for s in stages.steps(run)])
        run = intake.correct(root, run, 'spec')
        self.assertEqual(run['classified'], 'spec')
        self.assertEqual(len(documents.listed(root)), 1)
        self.assertNotIn('research', [s.name for s in stages.steps(run)])
        self.assertEqual(run['gates']['gate:classify']['state'], 'approved')

    def test_correction_resets_research_and_later_work_and_is_written(self):
        root, run = self.deck(research=True)
        run['classified'] = 'material'
        run['steps'] = {n: {'done': True} for n in
                        ('classify', 'research-plan', 'research', 'research-report', 'outline')}
        run['gates'] = {'gate:research-plan': {'state': 'approved'},
                        'gate:research': {'state': 'approved'},
                        'gate:outline': {'state': 'approved'}}
        intake.keep_classification(root, run, {'kind': 'material', 'reason': 'Notes.',
                                               'slides': None})
        run = intake.correct(root, run, 'spec')
        for name in ('research-plan', 'research', 'research-report', 'outline'):
            self.assertFalse(run['steps'][name]['done'], name)
        self.assertTrue(run['steps']['classify']['done'])
        self.assertEqual(run['gates']['gate:research']['state'], 'absent')
        self.assertEqual(run['gates']['gate:outline']['state'], 'absent')
        self.assertEqual(decks.read_run(root), run)
        note = (root / 'classify.md').read_text()
        self.assertIn('Corrected by you', note)
        self.assertIn('Notes.', note)


if __name__ == '__main__':
    unittest.main()
