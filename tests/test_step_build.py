"""Building a deck: its brand, its sections and their composers, the whole deck and its
review, the sections a review sends back, the render and what gate:build shows. The slides
tool and the brand skill are the stand-ins; the workers are played through their tools."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import runner_support
from runner_support import OUTLINE
from workspace import WorkspaceError

from runner import decks, worker_tools
from runner.steps import build, existing
from stand_ins.slides import sketch

BY_ID = {slide['id']: slide for slide in OUTLINE['slides']}


def drawn(spec: dict, extra=None) -> str:
    """A section as a composer might hand it in: each slide sketched plainly, with every
    approved word, and `extra` nodes added below each slide's drawing."""
    slides = []
    for wanted in spec['slides']:
        slide = sketch(BY_ID[wanted['id']], spec['prefix'])
        if extra:
            slide['canvas'] = {'type': 'stack', 'direction': 'column',
                               'children': [slide['canvas'], *extra]}
        slides.append(slide)
    return json.dumps({'version': 1, 'title': spec['title'], 'direction': spec['direction'],
                       'slides': slides})


class Deck(unittest.TestCase):
    """A deck folder with the stand-in tools, its brand exported and its outline approved."""
    route, level = 'scratch', None

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        self.root = self.base / 'presentations' / 'restarts'
        self.root.mkdir(parents=True)
        form = {'route': self.route, 'title': 'Rolling restarts', 'brand': 'example',
                'variant': 'light', 'output': 'google',
                **({'level': self.level} if self.level else {})}
        self.run_ = {'schema': 1, 'id': 'restarts', 'title': 'Rolling restarts',
                     'route': self.route, 'form': form, 'gates': {}, 'steps': {},
                     'revisions': [], 'halted': None}
        decks.write_run(self.root, self.run_)
        self.slides = runner_support.stand_in_slides()
        self.brand = runner_support.stand_in_brand()
        (self.root / 'outline.json').write_text(json.dumps(OUTLINE), encoding='utf-8')
        self.contract = build.export_brand(self.root, self.run_, self.brand)
        self.jobs = 0

    def job(self, work) -> worker_tools.WorkerTools:
        self.jobs += 1
        folder = self.base / 'jobs' / str(self.jobs)
        worker_tools.prepare(folder, **work.prepared)
        return worker_tools.WorkerTools(folder, slides=self.slides, brand=self.brand)

    def draw(self, section: str) -> None:
        """Play one section's composer: preview a plain drawing of it and hand it in."""
        work = build.section_work(self.root, self.run_, section, None, None)
        tools = self.job(work)
        section_drawn = drawn(work.prepared['artifacts']['section'])
        outcome = tools.preview_section(section_drawn)
        self.assertTrue(outcome[0], outcome[1])
        self.assertTrue(tools.submit_section(section_drawn, changed='Nothing.')[0])
        build.keep_section(self.root, self.run_, section,
                           worker_tools.collect(tools.folder))

    def built(self) -> dict:
        build.start(self.root, self.run_, self.slides, self.contract)
        for section in build.to_draw(self.root):
            self.draw(section)
        return build.whole(self.root, self.run_, self.slides, 'local')

    def review(self, findings) -> list:
        """Play the reviewer: look at every slide, then hand in `findings(slides)`."""
        work = build.review_work(self.root, self.run_)
        tools = self.job(work)
        listed = work.prepared['review']['slides']
        for slide in listed:
            self.assertTrue(tools.look_at_slide(slide['number'])[0])
        outcome = tools.submit_assessment(json.dumps(findings(listed)), '[]')
        self.assertTrue(outcome[0], outcome[1])
        return build.keep_review(self.root, self.run_, worker_tools.collect(tools.folder))


def grave(slides):
    """A major finding about how the second slide is drawn."""
    return [{'slide': slides[1]['id'], 'question': 6, 'severity': 'major',
             'about': 'drawing', 'note': 'The two boxes crowd the left half of the slide.'}]


class BrandTests(Deck):
    def test_the_brand_is_exported_once_and_reused(self):
        for name in ('brand-contract.json', 'DESIGN.md', 'VOICE.md', 'version.txt'):
            self.assertTrue((self.root / 'brand' / name).is_file(), name)
        revision = json.loads(self.contract.read_text())['revision']
        self.assertEqual((self.root / build.VERSION).read_text().strip(), revision)
        again = build.export_brand(self.root, self.run_, self.brand)
        self.assertEqual(again, self.contract)
        self.assertEqual(sum(call[:2] == ['contract', 'export']
                             for call in self.brand.run.calls), 1)
        self.assertIn(['contract', 'check'], [call[:2] for call in self.brand.run.calls])
        self.assertIsNone(decks.read_run(self.root)['halted'])

    def test_a_brand_that_changed_stops_the_deck(self):
        rules = self.brand.run.home / 'references' / 'brand-rules.md'
        rules.write_text(rules.read_text() + 'Round corners now.\n')
        with self.assertRaises(build.BrandChanged) as caught:
            build.export_brand(self.root, self.run_, self.brand)
        self.assertIn('The brand changed since this deck began', str(caught.exception))
        halted = decks.read_run(self.root)['halted']
        self.assertTrue(halted['why'].startswith('The brand changed since this deck began'))


class StartTests(Deck):
    route = 'existing'

    def started(self, level):
        self.run_['form']['level'] = level
        build.start(self.root, self.run_, self.slides, self.contract)
        given = self.root / build.START / 'given'
        return json.loads((given / 'outline.json').read_text()), \
            (given / 'section-1.md').read_text()

    def test_each_level_adds_its_own_house_line(self):
        for level in ('brand-only', 'polish', 'redesign'):
            whole, brief = self.started(level)
            self.assertEqual(whole['house'][-1], build.FREEDOM[level], level)
            self.assertIn(build.FREEDOM[level], brief, level)
            others = [line for name, line in build.FREEDOM.items() if name != level]
            self.assertFalse(any(line in whole['house'] for line in others), level)
        whole, brief = self.started('rework')
        self.assertEqual(whole['house'], list(build.HOUSE))
        self.assertIn('Add no icons', build.FREEDOM['brand-only'])

    def test_start_adds_the_direction_layouts_and_approval(self):
        whole, brief = self.started('rework')
        self.assertEqual(whole['direction'], build.DIRECTION)
        self.assertEqual(set(whole['layouts']), {'cover', 'closing'})
        self.assertTrue(whole['approval'])
        self.assertIn('submit_section', brief)
        self.assertNotIn(str(self.root), brief)
        state = build.read_state(self.root)
        self.assertEqual(build.to_draw(self.root),
                         [entry['id'] for entry in state['start']['sections']])


class LoopTests(Deck):
    def test_sections_are_drawn_put_together_and_pictured(self):
        made = self.built()
        self.assertEqual(build.to_draw(self.root), [])
        shots = json.loads((build.shots(self.root) / 'shots.json').read_text())
        self.assertEqual([one['number'] for one in shots['slides']],
                         [slide['number'] for slide in made['slides']])
        self.assertEqual(len(made['slides']), len(OUTLINE['slides']))
        self.assertEqual((self.root / 'contact-sheet.png').read_bytes()[:8], build.PNG)
        self.assertEqual(made['changed'], [])

    def test_review_sends_sections_back_at_most_twice(self):
        self.built()
        rounds = []
        for _ in range(3):
            found = self.review(grave)
            back = build.repair_sections(found)
            self.assertTrue(back)
            rounds.append(build.to_draw(self.root))
            for section in build.to_draw(self.root):
                work = build.section_work(self.root, self.run_, section, None, None)
                self.assertIn('what the review found', work.prepared['inputs'])
                self.assertTrue(work.prepared['look'])
                self.draw(section)
            if build.to_draw(self.root) == [] and rounds[-1]:
                build.whole(self.root, self.run_, self.slides, 'local')
        self.assertTrue(rounds[0] and rounds[1])
        self.assertEqual(rounds[2], [])
        for number in (1, 2, 3):
            self.assertTrue((self.root / 'reviews' / f'build-{number}.md').is_file())
        last = (self.root / 'reviews' / 'build-3.md').read_text()
        self.assertIn('What is left is yours to decide', last)
        self.assertIn('major', (self.root / 'reviews' / 'build-1.md').read_text())

    def test_a_clear_review_sends_nothing_back(self):
        self.built()
        self.assertEqual(self.review(lambda slides: []), [])
        self.assertEqual(build.to_draw(self.root), [])
        self.assertIn('nothing major', (self.root / 'reviews' / 'build-1.md').read_text())

    def test_render_and_gate_view(self):
        self.built()
        self.review(grave)
        deck = build.render(self.root, self.run_, self.slides, brand=self.brand)
        self.assertEqual(deck, self.root / build.DECK)
        last = build.read_state(self.root)['rounds'][-1]
        # The deck delivered is the one previewed and reviewed, not a fresh render.
        self.assertEqual(deck.read_bytes(), (self.root / last['file']).read_bytes())
        self.assertEqual(build._digest(deck), last['deck'])
        self.assertNotIn(['compose', 'render'], [call[:2] for call in self.slides.run.calls])
        self.assertEqual(build.delivered_deck(self.root, self.run_), deck)
        shown = build.gate_view(self.root, self.run_)
        self.assertEqual(shown['round'], 1)
        self.assertEqual(shown['pairs'], [])
        self.assertEqual(shown['contactSheet'], str(self.root / 'contact-sheet.png'))
        second = shown['slides'][1]
        self.assertEqual(second['findings'][0]['severity'], 'major')
        self.assertTrue(Path(second['image']).is_file())
        self.assertIsInstance(shown['audit']['warnings'], int)
        self.assertIn('status', shown['audit'])
        self.assertEqual(decks.read_run(self.root)['gates']['gate:build']['state'], 'waiting')

    def test_without_the_brand_skill_the_audit_says_why(self):
        self.built()
        build.render(self.root, self.run_, self.slides)
        shown = build.gate_view(self.root, self.run_)
        self.assertIsNone(shown['audit'])
        self.assertTrue(shown['auditNote'])

    def test_a_section_drawn_again_marks_its_slides_changed(self):
        self.built()
        self.review(grave)
        for section in build.to_draw(self.root):
            work = build.section_work(self.root, self.run_, section, None, None)
            tools = self.job(work)
            again = drawn(work.prepared['artifacts']['section'], extra=[{'type': 'rule'}])
            outcome = tools.preview_section(again)
            self.assertTrue(outcome[0], outcome[1])
            self.assertTrue(tools.submit_section(again)[0])
            build.keep_section(self.root, self.run_, section,
                               worker_tools.collect(tools.folder))
        made = build.whole(self.root, self.run_, self.slides, 'local')
        self.assertTrue(made['changed'])
        self.assertEqual(build.gate_view(self.root, self.run_)['changed'], made['changed'])


class DeliveredDeckTests(Deck):
    def test_a_previewed_deck_that_changed_is_not_delivered(self):
        self.built()
        last = build.read_state(self.root)['rounds'][-1]
        (self.root / last['file']).write_bytes(b'PK\x03\x04 something else')
        with self.assertRaises(WorkspaceError) as caught:
            build.render(self.root, self.run_, self.slides)
        self.assertIn('not here as it was', str(caught.exception))
        self.assertFalse((self.root / build.DECK).exists())

    def test_a_new_round_takes_the_earlier_deck_away(self):
        self.built()
        build.render(self.root, self.run_, self.slides)
        build.whole(self.root, self.run_, self.slides, 'local')
        self.assertFalse((self.root / build.DECK).exists())
        with self.assertRaises(WorkspaceError):
            build.delivered_deck(self.root, self.run_)

    def test_a_deck_left_on_disk_is_not_delivered_unrecorded(self):
        (self.root / build.DECK).parent.mkdir(parents=True, exist_ok=True)
        (self.root / build.DECK).write_bytes(b'PK\x03\x04 left behind')
        with self.assertRaises(WorkspaceError):
            build.delivered_deck(self.root, self.run_)


class PairsTests(Deck):
    route = 'existing'

    def originals(self):
        folder = self.root / existing.ORIGINAL_SHOTS
        folder.mkdir(parents=True)
        listed = []
        for number in range(1, len(OUTLINE['slides']) + 1):
            (folder / f'{number}.png').write_bytes(runner_support.png(number))
            listed.append({'number': number, 'image': f'{number}.png'})
        (folder / 'shots.json').write_text(json.dumps({'slides': listed}))

    def test_polish_shows_before_and_after(self):
        self.run_['form']['level'] = 'polish'
        self.originals()
        self.built()
        pairs = build.gate_view(self.root, self.run_)['pairs']
        self.assertEqual(len(pairs), len(OUTLINE['slides']))
        self.assertTrue(all(Path(pair['after']).is_file() for pair in pairs))

    def test_rework_shows_none(self):
        self.run_['form']['level'] = 'rework'
        self.originals()
        self.built()
        self.assertEqual(build.gate_view(self.root, self.run_)['pairs'], [])


class SelectedTests(unittest.TestCase):
    def selected(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / 'deck'
        root.mkdir()
        run = {'schema': 1, 'id': 'd', 'title': 'Old', 'route': 'existing',
               'form': {'route': 'existing', 'level': 'selected', 'selected': 'slide 2'},
               'gates': {}, 'steps': {}}
        decks.write_run(root, run)
        slides = runner_support.stand_in_slides()
        existing.fetch(root, {'kind': 'upload', 'name': 'old.pptx',
                              'data': b'PK\x03\x04stand-in'}, slides, False)
        existing.inventory(root, run, slides, 'local')
        found = json.loads((root / 'classify.json').read_text())
        item = found['slides'][1]['objects'][0]
        existing.keep_patch(root, json.dumps({'sourceSha256': found['sha256'], 'operations': [
            {'slide': 2, 'object': item['id'], 'expectedHash': item['contentHash'],
             'text': 'Run Acme faster'}]}))
        return root, run, slides, found

    def test_selected_renders_the_patched_deck_with_its_pictures(self):
        root, run, slides, found = self.selected()
        deck = build.render(root, run, slides)
        self.assertEqual(deck, root / existing.PATCHED)
        self.assertEqual(build.delivered_deck(root, run), deck)
        shown = build.gate_view(root, run)
        self.assertEqual([slide['number'] for slide in shown['slides']],
                         [slide['number'] for slide in found['slides']])
        self.assertTrue(all(pair['after'] for pair in shown['pairs']))


    def test_its_pictures_reuse_the_one_preview_file_in_drive(self):
        root, run, slides, _ = self.selected()
        build.render(root, run, slides, renderer='drive')
        kept = json.loads((root / 'work' / 'build' / 'drive-preview.json').read_text())
        build.render(root, run, slides, renderer='drive')
        previews = [ident for ident in slides.run.files if ident.startswith('stand-in-preview')]
        self.assertEqual(previews, [kept['id']])
        self.assertEqual(slides.run.files[kept['id']]['uploads'], 2)
        asked = [call for call in slides.run.calls if call[:1] == ['review']]
        self.assertIn(kept['id'], asked[-1])

    def test_a_picture_that_fails_leaves_no_patched_deck(self):
        root, run, slides, _ = self.selected()
        slides.run.fails['review'] = 'The renderer stopped.'
        with self.assertRaises(WorkspaceError):
            build.render(root, run, slides)
        self.assertFalse((root / existing.PATCHED).exists())
        with self.assertRaises(WorkspaceError):
            build.delivered_deck(root, run)


class RefusalTests(Deck):
    def test_steps_out_of_order_are_refused(self):
        with self.assertRaises(WorkspaceError):
            build.section_work(self.root, self.run_, 'section-1', None, None)
        with self.assertRaises(WorkspaceError):
            build.review_work(self.root, self.run_)
        build.start(self.root, self.run_, self.slides, self.contract)
        with self.assertRaises(WorkspaceError) as caught:
            build.whole(self.root, self.run_, self.slides, 'local')
        self.assertIn('not drawn yet', str(caught.exception))
        with self.assertRaises(WorkspaceError):
            build.section_work(self.root, self.run_, 'section-9', None, None)

    def test_brand_only_and_polish_composers_draw_only_the_approved_words(self):
        build.start(self.root, self.run_, self.slides, self.contract)
        for route, level, strict in (('existing', 'brand-only', True),
                                     ('existing', 'polish', True),
                                     ('existing', 'redesign', False), ('scratch', None, False)):
            run = copy.deepcopy(self.run_)
            run['route'], run['form']['level'] = route, level
            work = build.section_work(self.root, run, 'section-1', None, None)
            self.assertIs(work.prepared['artifacts']['section']['strict'], strict, level)

    def test_a_slide_whose_original_shows_no_words_is_bare_at_brand_only(self):
        build.start(self.root, self.run_, self.slides, self.contract)
        given = json.loads((self.root / build.START / 'given' / 'outline.json').read_text())
        first = next(slide for slide in given['slides'] if slide.get('kind') == 'content')
        number = given['slides'].index(first) + 1
        slides = [{'number': n, 'title': 'Words', 'objects': [
            {'id': '2', 'type': 'sp', 'text': 'Words', 'runs': ['Words']}]}
            for n in range(1, len(given['slides']) + 1)]
        slides[number - 1] = {'number': number, 'title': '', 'objects': []}
        (self.root / 'classify.json').write_text(json.dumps({'slides': slides}))
        for level, bare in (('brand-only', True), ('polish', True), ('redesign', False)):
            run = copy.deepcopy(self.run_)
            run['route'], run['form']['level'] = 'existing', level
            spec = build.section_work(self.root, run, 'section-1', None, None) \
                .prepared['artifacts']['section']
            marked = {slide['id']: slide['bare'] for slide in spec['slides']}
            self.assertIs(marked.get(first['id'], False), bare, level)

    def test_a_gate_note_reaches_the_composer(self):
        self.built()
        run = copy.deepcopy(self.run_)
        run['gates']['gate:build'] = {'state': 'changes', 'note': 'Make the cover calmer.'}
        work = build.section_work(self.root, run, 'section-1', None, None)
        self.assertIn('Make the cover calmer.', work.task)


if __name__ == '__main__':
    unittest.main()
