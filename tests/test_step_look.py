"""The look of a deck: the options a worker proposes, their pictures, and the person's
choice. The slides tool and the brand skill are the stand-ins."""
import json
import tempfile
import unittest
from pathlib import Path

import runner_support
from runner_support import OUTLINE
from stand_ins.slides import sketch
from workspace import WorkspaceError

from runner import decks, worker_tools
from runner.steps import build, look

FIRST = OUTLINE['slides'][1]
DIRECTIONS = ({'focal': 'headingPrimary', 'neutral': 'canvasSecondary'},
              {'focal': 'accentAqua', 'neutral': 'canvasPrimary', 'motif': 'A thin rule.'},
              {'focal': 'inkDeep', 'neutral': 'canvasSecondary',
               'meanings': {'accentAqua': 'a gain'}})


def options(count=3, **changed):
    made = [{'name': name, 'direction': direction, 'why': f'{name} suits an ops audience.',
             'composition': sketch(FIRST, 'l1_')}
            for name, direction in zip(('Calm grid', 'Bold rule', 'Quiet ink'), DIRECTIONS)]
    for option in made[:count]:
        option.update(changed)
    return {'options': made[:count]}


class Case(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / 'deck'
        self.root.mkdir()
        self.run_ = {'schema': 1, 'id': 'd', 'title': 'Rolling restarts', 'route': 'scratch',
                     'form': {'route': 'scratch', 'brand': 'example', 'variant': 'light',
                              'audience': 'Ops'},
                     'gates': {'gate:outline': {'state': 'approved', 'note': 'Keep it short.'}},
                     'steps': {}, 'look': None}
        decks.write_run(self.root, self.run_)
        (self.root / 'outline.json').write_text(json.dumps(OUTLINE), encoding='utf-8')
        self.slides = runner_support.stand_in_slides()
        self.scratch = Path(holder.name).resolve() / 'scratch'
        self.brand = runner_support.stand_in_brand()   # its folder lasts as long as it does
        self.contract = build.export_brand(self.root, self.run_, self.brand)

    def check(self, given, spec):
        return look.check_look(json.dumps(given), spec, self.slides, self.scratch)

    def spec(self):
        return look.look_work(self.root, self.run_, None, None, self.contract,
                              slides=self.slides).prepared['artifacts']['look']


class CheckTests(Case):
    def test_one_option_is_refused_and_three_accepted(self):
        spec = self.spec()
        problems, *_ = self.check(options(1), spec)
        self.assertEqual(problems, ['Offer two or three options, not 1.'])
        problems, checks, _, _ = self.check(options(3), spec)
        self.assertEqual(problems, [])
        self.assertEqual([check['status'] for check in checks], ['passed', 'passed'])

    def test_an_option_that_does_not_compile_is_refused(self):
        broken = options(2)
        broken['options'][1]['composition'] = {**sketch(FIRST, 'l1_'),
                                               'canvas': {'type': 'teapot'}}
        problems, *_ = self.check(broken, self.spec())
        self.assertTrue(problems)
        self.assertTrue(all(problem.startswith('Option 2 ("Bold rule") does not compile')
                            for problem in problems), problems)

    def test_a_worker_hands_it_back_through_submit_artifact(self):
        work = look.look_work(self.root, self.run_, None, None, self.contract,
                              slides=self.slides)
        self.assertEqual(work.name, 'look')
        self.assertIn('The outline', work.prepared['inputs'])
        self.assertIn("The brand's composition contract", work.prepared['inputs'])
        self.assertIn('The layouts', work.prepared['inputs'])
        self.assertIn(f"`{FIRST['id']}`", work.task)
        folder = self.root.parent / 'job'
        worker_tools.prepare(folder, **work.prepared)
        tools = worker_tools.WorkerTools(folder, slides=self.slides)
        said = tools.submit_artifact('look', json.dumps(options(1)))
        self.assertFalse(said[0])
        self.assertIn('two or three', said[1])
        self.assertTrue(tools.submit_artifact('look', json.dumps(options(2)))[0])
        self.assertIs(worker_tools.VALIDATORS['look'], look.check_look)
        job = json.loads((folder / 'job.json').read_text())
        self.assertEqual(job['checks']['look'], {'call': 'runner.steps.look:check_look',
                                                 'extension': '.json', 'drawn': True})

    def test_colours_slide_and_names_are_checked(self):
        spec = self.spec()
        for wrong, text in (
                (options(direction={'focal': 'hotPink', 'neutral': 'canvasPrimary'}),
                 'not a colour the brand names'),
                (options(direction={'focal': 'inkDeep', 'neutral': 'inkDeep'}), 'different'),
                (options(direction={'focal': 'inkDeep', 'neutral': 'canvasPrimary',
                                    'shade': 1}), 'leave out shade'),
                (options(composition={**sketch(FIRST, 'l1_'), 'id': 'other'}), 'its ID'),
                (options(name='Same'), 'a name of its own')):
            problems, *_ = self.check(wrong, spec)
            self.assertTrue(any(text in problem for problem in problems), (text, problems))
        problems, *_ = look.check_look('not json', spec, self.slides, self.scratch)
        self.assertIn('not valid JSON', problems[0])


class PreviewTests(Case):
    def test_each_option_is_pictured_and_listed(self):
        look.keep_look(self.root, self.run_, json.dumps(options(3)))
        shown = look.preview_options(self.root, self.run_, self.slides, 'local')
        self.assertEqual([one['name'] for one in shown],
                         ['Calm grid', 'Bold rule', 'Quiet ink'])
        for number, one in enumerate(shown, start=1):
            image = Path(one['image'])
            self.assertEqual(image, self.root / 'work' / 'look' / str(number) / 'picture.png')
            self.assertEqual(image.read_bytes()[:8], build.PNG)
        listed = (self.root / 'look.md').read_text()
        self.assertIn('## 3. Quiet ink', listed)
        self.assertIn('A thin rule.', listed)
        self.assertEqual(decks.read_run(self.root)['gates']['gate:look']['state'], 'waiting')

    def test_an_option_that_will_not_draw_is_named(self):
        broken = options(2)
        broken['options'][1]['composition'] = {**sketch(FIRST, 'l1_'),
                                               'canvas': {'type': 'teapot'}}
        look.keep_look(self.root, self.run_, json.dumps(broken))
        with self.assertRaises(WorkspaceError) as caught:
            look.preview_options(self.root, self.run_, self.slides, 'local')
        self.assertIn('"Bold rule" could not be drawn', str(caught.exception))
        self.assertFalse((self.root / 'work' / 'look' / '2').exists())


class ChooseTests(Case):
    def test_the_choice_is_written_into_the_outline(self):
        look.keep_look(self.root, self.run_, json.dumps(options(3)))
        look.choose(self.root, self.run_, 'bold rule', note='This one, please.')
        chosen = json.loads((self.root / 'look.json').read_text())
        self.assertEqual(chosen, {'chosen': 'Bold rule', 'direction': DIRECTIONS[1],
                                  'why': 'Bold rule suits an ops audience.'})
        outline = json.loads((self.root / 'outline.json').read_text())
        self.assertEqual(outline['direction'], DIRECTIONS[1])
        self.assertIn('Keep it short.', outline['approval'])
        self.assertIn('This one, please.', outline['approval'])
        run = decks.read_run(self.root)
        self.assertEqual(run['gates']['gate:look']['state'], 'approved')
        self.assertEqual(run['look'], 'Bold rule')

    def test_an_unknown_choice_is_refused(self):
        look.keep_look(self.root, self.run_, json.dumps(options(2)))
        with self.assertRaises(WorkspaceError) as caught:
            look.choose(self.root, self.run_, 'Loud')
        self.assertIn('"Calm grid"', str(caught.exception))
        self.assertFalse((self.root / 'look.json').exists())

    def test_the_chosen_direction_reaches_the_build(self):
        look.keep_look(self.root, self.run_, json.dumps(options(3)))
        look.choose(self.root, self.run_, 'Quiet ink')
        build.start(self.root, self.run_, self.slides, self.contract)
        whole = json.loads((self.root / build.START / 'given' / 'outline.json').read_text())
        self.assertEqual(whole['direction'], DIRECTIONS[2])


if __name__ == '__main__':
    unittest.main()
