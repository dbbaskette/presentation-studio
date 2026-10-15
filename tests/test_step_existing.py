"""Existing decks: fetching, the inventory and its pictures, and selected changes. The
slides tool is the stand-in; nothing is installed."""
import json
import tempfile
import unittest
from pathlib import Path

import runner_support
from workspace import WorkspaceError

from runner import decks, worker_tools
from runner.steps import existing, outline

DECK = b'PK\x03\x04' + b'stand-in deck'


def tree(root):
    return sorted(str(path.relative_to(root)) for path in Path(root).rglob('*'))


class Case(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name) / 'deck'
        self.root.mkdir()
        self.run_ = {'schema': 1, 'id': 'd', 'title': 'Old', 'route': 'existing',
                     'form': {'route': 'existing', 'level': 'selected',
                              'selected': 'Fix slides 2 and 3-3 wording'},
                     'gates': {}, 'steps': {}}
        decks.write_run(self.root, self.run_)
        self.slides = runner_support.stand_in_slides()

    def taken(self):
        existing.fetch(self.root, {'kind': 'upload', 'name': 'old.pptx', 'data': DECK},
                       self.slides, False)
        return existing.inventory(self.root, self.run_, self.slides, 'local')


class FetchTests(Case):
    def test_bad_signature_is_refused_and_nothing_written(self):
        before = tree(self.root)
        with self.assertRaises(WorkspaceError) as caught:
            existing.fetch(self.root, {'kind': 'upload', 'name': 'a.pptx', 'data': b'%PDF'},
                           self.slides, True)
        self.assertIn('not a PowerPoint', str(caught.exception))
        self.assertEqual(tree(self.root), before)

    def test_too_large_is_refused(self):
        big = b'PK\x03\x04' + bytes(existing.LIMIT)
        with self.assertRaises(WorkspaceError) as caught:
            existing.fetch(self.root, {'kind': 'upload', 'name': 'a.pptx', 'data': big},
                           self.slides, True)
        self.assertIn('100 MB', str(caught.exception))
        self.assertFalse((self.root / existing.SOURCE).exists())

    def test_upload_is_kept(self):
        path = existing.fetch(self.root, {'kind': 'upload', 'name': 'a.pptx', 'data': DECK},
                              self.slides, False)
        self.assertEqual(path.read_bytes(), DECK)

    def test_google_not_ready_is_refused_and_folder_unchanged(self):
        before = tree(self.root)
        with self.assertRaises(WorkspaceError) as caught:
            existing.fetch(self.root, {'kind': 'google', 'link': 'abc123'}, self.slides, False)
        self.assertEqual(str(caught.exception), existing.NOT_READY)
        self.assertEqual(tree(self.root), before)

    def test_google_exports_a_url_or_an_id(self):
        for link in ('abc123', 'https://docs.google.com/presentation/d/abc123/edit'):
            path = existing.fetch(self.root, {'kind': 'google', 'link': link}, self.slides,
                                  True)
            self.assertEqual(path.read_bytes()[:4], b'PK\x03\x04')
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()),
                         ['original.json', 'original.pptx'])


class InventoryTests(Case):
    def test_writes_inventory_table_pictures_and_gate(self):
        run = self.taken()
        found = outline.inventory_of(self.root)
        self.assertEqual(found['source'], 'old.pptx')
        self.assertEqual([s['number'] for s in found['slides']], [1, 2, 3])
        item = found['slides'][1]['objects'][0]
        self.assertEqual(sorted(item), sorted(existing.OBJECT_KEYS))
        self.assertTrue(item['contentHash'])
        self.assertIn('| 2 | Run Tanzu fast |', (self.root / 'classify.md').read_text())
        self.assertEqual(run['gates']['gate:classify']['state'], 'waiting')
        self.assertEqual(decks.read_run(self.root)['gates']['gate:classify']['round'], 1)
        shots = json.loads((self.root / 'work/original/shots.json').read_text())
        self.assertEqual([s['number'] for s in shots['slides']], [1, 2, 3])
        for one in shots['slides']:
            self.assertTrue((self.root / 'work/original' / one['image']).is_file())

    def test_inventory_twice_redraws(self):
        self.taken()
        existing.inventory(self.root, self.run_, self.slides, 'local')
        self.assertEqual(self.run_['gates']['gate:classify']['round'], 2)


class PatchTests(Case):
    def setUp(self):
        super().setUp()
        self.taken()
        self.inv = outline.inventory_of(self.root)
        item = self.inv['slides'][1]['objects'][0]
        self.spec = existing._spec(self.inv, [2])
        self.op = {'slide': 2, 'object': item['id'], 'expectedHash': item['contentHash'],
                   'text': 'Run Tanzu faster'}

    def plan(self, *ops, sha=None):
        return json.dumps({'sourceSha256': sha or self.inv['sha256'], 'operations': list(ops)})

    def test_named_slides(self):
        for text, want in (('slide 3', [3]), ('slides 4 and 7', [4, 7]), ('3, 5-6', [3, 5, 6]),
                           ('Please tidy slides 2, 4 & 6', [2, 4, 6]), ('no numbers', [])):
            self.assertEqual(existing.named_slides(text), want, text)

    def test_valid_plan_passes(self):
        problems, checks, _, _ = existing.check_patch(self.plan(self.op), self.spec)
        self.assertEqual(problems, [])
        self.assertEqual(checks[0]['status'], 'passed')

    def test_refuses_unnamed_slide_wrong_hash_object_and_sha(self):
        for op, text in (({**self.op, 'slide': 3}, 'not named'),
                         ({**self.op, 'expectedHash': 'x'}, 'expectedHash'),
                         ({**self.op, 'object': '99'}, 'no object'),
                         ({**self.op, 'alt': 'a'}, 'exactly one')):
            problems, *_ = existing.check_patch(self.plan(op), self.spec)
            self.assertTrue(any(text in p for p in problems), (text, problems))
        problems, *_ = existing.check_patch(self.plan(self.op, sha='bad'), self.spec)
        self.assertTrue(any('hash' in p for p in problems))

    def test_registered_for_workers(self):
        self.assertIs(worker_tools.VALIDATORS['patch'], existing.check_patch)

    def test_work_carries_spec_and_refuses_when_no_slide_named(self):
        work = existing.patch_work(self.root, self.run_, None, None)
        spec = work.prepared['artifacts']['patch']
        self.assertEqual((work.name, spec['kind'], spec['named']), ('patch', 'patch', [2, 3]))
        self.assertIn(f"2:{self.op['object']}", spec['objects'])
        self.assertNotIn('1:2', spec['objects'])
        self.run_['form']['selected'] = 'make it nicer'
        with self.assertRaises(WorkspaceError) as caught:
            existing.patch_work(self.root, self.run_, None, None)
        self.assertIn('slides', str(caught.exception))

    def test_apply_patch_makes_the_copy(self):
        existing.keep_patch(self.root, self.plan(self.op))
        path = existing.apply_patch(self.root, self.run_, self.slides)
        self.assertEqual(path, self.root / 'work/patched.pptx')
        after = self.slides.pptx_inspect(path)
        self.assertEqual(after['slides'][1]['objects'][0]['text'], 'Run Tanzu faster')

    def test_apply_patch_removes_a_copy_that_changed_too_much(self):
        existing.keep_patch(self.root, self.plan(self.op))

        class Loud:
            def pptx_patch(inner, deck, plan, output):
                output.write_bytes(DECK)
                return {}

            def pptx_compare(inner, deck, after, allow):
                return {'preserved': False, 'failures': [
                    {'slide': self.inv['slides'][0]['id'], 'object': '2',
                     'code': 'text-changed'}]}
        with self.assertRaises(WorkspaceError) as caught:
            existing.apply_patch(self.root, self.run_, Loud())
        self.assertIn('slide 1, object 2: text-changed', str(caught.exception))
        self.assertFalse((self.root / existing.PATCHED).exists())


class PairsTests(Case):
    def test_lines_up_numbers(self):
        self.taken()
        after = self.root / 'work/build/preview'
        after.mkdir(parents=True)
        (after / 'two.png').write_bytes(b'x')
        (after / 'shots.json').write_text(json.dumps(
            {'slides': [{'number': 2, 'image': 'two.png'}]}))
        rows = existing.pairs(self.root, self.run_)
        self.assertEqual([r['number'] for r in rows], [1, 2, 3])
        self.assertIsNone(rows[0]['after'])
        self.assertEqual(rows[1]['after'], str(after / 'two.png'))
        self.assertTrue(Path(rows[1]['before']).is_file())

    def test_rework_has_none(self):
        self.taken()
        self.run_['form']['level'] = 'rework'
        self.assertEqual(existing.pairs(self.root, self.run_), [])


if __name__ == '__main__':
    unittest.main()
