"""Building a deck: its brand, its sections and their composers, the whole deck and its
review, the sections a review sends back, the render and what gate:build shows. The slides
tool and the brand skill are the stand-ins; the workers are played through their tools."""
import copy
import json
import struct
import tempfile
import unittest
import zipfile
import zlib
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
        if wanted.get('layout'):   # set by the runner: copied as it is given
            slides.append({key: wanted[key] for key in ('id', 'title', 'sources', 'layout',
                                                        'picture', 'notes')
                           if wanted.get(key)})
            continue
        if wanted.get('bare'):   # drawn as before: a shape, and no words
            slides.append({'id': wanted['id'], 'title': wanted['title'],
                           'sources': wanted['sources'], 'notes': wanted['notes'],
                           'canvas': {'type': 'box', 'id': f"{spec['prefix']}shape"}})
            continue
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



# --- a slide that had no words -------------------------------------------------------------

def png() -> bytes:
    """A picture of one grey pixel."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data \
            + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\x80')) + chunk(b'IEND', b''))


P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'


def original(path: Path, count: int, pictured: int | None, media: str = 'image1.png') -> None:
    """A deck of `count` slides as PowerPoint writes one, with a picture alone on slide
    `pictured`, kept as ppt/media/`media`."""
    ids = ''.join(f'<p:sldId id="{255 + n}" r:id="rId{n}"/>' for n in range(1, count + 1))
    rels = ''.join(f'<Relationship Id="rId{n}" Type="{R}/slide" Target="slides/slide{n}.xml"/>'
                   for n in range(1, count + 1))
    with zipfile.ZipFile(path, 'w') as deck:
        deck.writestr('ppt/presentation.xml', f'<p:presentation xmlns:p="{P}" xmlns:r="{R}">'
                      f'<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>')
        deck.writestr('ppt/_rels/presentation.xml.rels',
                      f'<Relationships xmlns="{REL}">{rels}</Relationships>')
        for n in range(1, count + 1):
            shape = (f'<p:pic><p:nvPicPr><p:cNvPr id="4" name="Picture 3" descr="Racks"/>'
                     '<p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId2"/>'
                     '</p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/>'
                     '<a:ext cx="9144000" cy="5143500"/></a:xfrm></p:spPr></p:pic>'
                     if n == pictured else '<p:sp><p:txBody><a:p><a:r><a:t>Words</a:t></a:r>'
                     '</a:p></p:txBody></p:sp>')
            deck.writestr(f'ppt/slides/slide{n}.xml',
                          f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld>'
                          f'<p:spTree>{shape}</p:spTree></p:cSld></p:sld>')
            if n == pictured:
                deck.writestr(f'ppt/slides/_rels/slide{n}.xml.rels',
                              f'<Relationships xmlns="{REL}"><Relationship Id="rId2" '
                              f'Type="{R}/image" Target="../media/{media}"/>'
                              '</Relationships>')
        deck.writestr(f'ppt/media/{media}', png() if media.endswith('.png')
                      else b'\x01\x00\x00\x00 an enhanced metafile')


class WordlessTests(Deck):
    """At brand only and polish, a slide whose original shows no words is set on a template
    layout that shows no title, and draws nothing."""
    route = 'existing'
    BARE = 'when-capacity-holds'   # the third slide

    def setUp(self):
        super().setUp()
        self.outline = copy.deepcopy(OUTLINE)
        self.outline['slides'][2] = {
            'id': self.BARE, 'kind': 'content', 'relation': 'none', 'points': [],
            'title': BY_ID[self.BARE]['title'], 'understand': 'A picture of the racks.',
            'notes': BY_ID[self.BARE]['notes'], 'sources': BY_ID[self.BARE]['sources']}
        count = len(self.outline['slides'])
        slides = [{'number': n, 'id': str(255 + n), 'title': 'Words', 'objects': [
            {'id': '2', 'type': 'sp', 'text': 'Words', 'runs': ['Words']}]}
            for n in range(1, count + 1)]
        slides[2] = {'number': 3, 'id': '258', 'title': '', 'objects': [
            {'id': '4', 'type': 'pic', 'text': '', 'runs': [], 'alt': 'Racks of servers'}]}
        (self.root / 'classify.json').write_text(json.dumps({'slides': slides}))
        (self.root / 'sources').mkdir()
        original(self.root / existing.SOURCE, count, 3)

    def at(self, level, outline=None):
        self.run_['form']['level'] = level
        (self.root / 'outline.json').write_text(json.dumps(outline or self.outline))

    def delivered_words(self) -> list[str]:
        """The words written on each slide of the delivered deck."""
        build.render(self.root, self.run_, self.slides)
        with zipfile.ZipFile(build.delivered_deck(self.root, self.run_)) as deck:
            return [deck.read(f'ppt/slides/slide{n}.xml').decode()
                    for n in range(1, len(self.outline['slides']) + 1)]

    def test_brand_only_and_polish_set_it_on_a_layout_without_a_title(self):
        for level in ('brand-only', 'polish'):
            with self.subTest(level=level):
                self.at(level)
                self.built()
                placed = build.read_state(self.root)['start']['wordless']
                self.assertEqual(list(placed), [self.BARE])
                self.assertEqual(placed[self.BARE]['layout'], 'Quote')   # it has a picture slot
                picture = placed[self.BARE]['picture']
                self.assertEqual(picture['alt'], 'Racks of servers')
                self.assertEqual(Path(picture['src']).read_bytes(), png())
                words = self.delivered_words()
                self.assertNotIn(BY_ID[self.BARE]['title'], words[2])
                self.assertNotIn('<a:t>', words[2], 'no words at all on that slide')
                self.assertIn(BY_ID['what-it-does']['title'], words[1])

    def test_the_composer_is_told_the_layout_and_may_not_change_it(self):
        self.at('brand-only')
        build.start(self.root, self.run_, self.slides, self.contract)
        section = next(entry['id'] for entry in build.read_state(self.root)['start']['sections']
                       if self.BARE in entry['slides'])
        work = build.section_work(self.root, self.run_, section, None, None)
        spec = work.prepared['artifacts']['section']
        mine = next(slide for slide in spec['slides'] if slide['id'] == self.BARE)
        self.assertEqual(mine['layout'], 'Quote')
        self.assertIn('Quote', work.task)
        handed = json.loads(drawn(spec))
        self.assertEqual(build.kept(handed, spec), [])
        at = [slide['id'] for slide in handed['slides']].index(self.BARE)
        for change in ({'layout': 'Blank'}, {'picture': None},
                       {'canvas': {'type': 'text', 'id': f"{spec['prefix']}x",
                                   'text': BY_ID[self.BARE]['title']}},
                       {'subtitle': 'Racks of servers'}):
            wrong = copy.deepcopy(handed)
            wrong['slides'][at].update(change)
            wrong['slides'][at] = {key: value for key, value in wrong['slides'][at].items()
                                   if value is not None}
            self.assertTrue(build.kept(wrong, spec), change)
        others = copy.deepcopy(handed)
        other = next(slide for slide in others['slides'] if slide['id'] != self.BARE)
        other['layout'] = 'Quote'
        self.assertTrue(build.kept(others, spec), 'a slide the runner did not set')

    def falls_back(self) -> list[str]:
        """Build the deck at brand only, and check the slide fell back to its earlier
        drawing: a shape and its approved title, with a note at the gate. Returns the words
        on each slide of the delivered deck."""
        self.at('brand-only')
        self.built()
        began = build.read_state(self.root)['start']
        self.assertEqual(began['wordless'], {})
        self.assertEqual(began['titled'], [self.BARE])
        compiled = self.root / build.read_state(self.root)['rounds'][-1]['compiled']
        scene = json.loads((compiled / 'scene.json').read_text())
        drawn_ids = [element['id'] for slide in scene['slides'] if slide['id'] == self.BARE
                     for element in slide['elements']]
        self.assertTrue(any(ident.endswith('shape') for ident in drawn_ids), drawn_ids)
        notes = {slide['number']: slide.get('note')
                 for slide in build.gate_view(self.root, self.run_)['slides']}
        self.assertEqual(notes[3], "This slide is drawn with a title because its picture "
                                   "can't be carried onto a layout without one.")
        self.assertEqual([number for number, note in notes.items() if note], [3])
        words = self.delivered_words()
        self.assertIn(BY_ID[self.BARE]['title'], words[2])
        return words

    def test_a_slide_of_shapes_alone_keeps_its_drawing_under_its_title(self):
        original(self.root / existing.SOURCE, len(self.outline['slides']), None)
        self.falls_back()

    def test_a_picture_the_slides_tool_cannot_place_falls_back(self):
        original(self.root / existing.SOURCE, len(self.outline['slides']), 3, 'image1.emf')
        self.falls_back()

    def test_a_template_without_a_title_less_layout_with_a_picture_slot_falls_back(self):
        self.slides.run.layouts = tuple(layout for layout in self.slides.run.layouts
                                        if layout[1] or not layout[3])
        self.falls_back()

    def test_a_template_with_no_layout_without_a_title_falls_back_and_goes_on(self):
        self.slides.run.layouts = tuple(layout for layout in self.slides.run.layouts
                                        if layout[1])
        self.falls_back()
        self.assertIsNone(decks.read_run(self.root).get('halted'))

    def test_redesign_draws_its_title_as_before(self):
        self.at('redesign', OUTLINE)
        self.built()
        began = build.read_state(self.root)['start']
        self.assertEqual((began.get('wordless'), began.get('titled')), ({}, []))
        self.assertIn(BY_ID[self.BARE]['title'], self.delivered_words()[2])
        self.assertFalse(any(slide.get('note') for slide in
                             build.gate_view(self.root, self.run_)['slides']))

if __name__ == '__main__':
    unittest.main()
