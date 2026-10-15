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
from unittest import mock

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
        if wanted.get('bare'):   # drawn as before: a shape, any picture given, no words
            shape = {'type': 'box', 'id': f"{spec['prefix']}shape"}
            slides.append({'id': wanted['id'], 'title': wanted['title'],
                           'sources': wanted['sources'], 'notes': wanted['notes'],
                           'canvas': {'type': 'stack', 'direction': 'column',
                                      'children': [wanted['image'], shape]}
                           if wanted.get('image') else shape})
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

def png(wide: int = 16, high: int = 9) -> bytes:
    """A grey picture of `wide` by `high` pixels."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data \
            + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\x00' + b'\x80' * wide for _ in range(high))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', wide, high, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
SHAPE = ('<p:sp><p:nvSpPr><p:cNvPr id="5" name="Arrow"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
         '<p:spPr/></p:sp>')
EMPTY_TITLE = ('<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr/><p:nvPr>'
               '<p:ph type="title"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:p/></p:txBody>'
               '</p:sp>')
HIDDEN = ('<p:sp><p:nvSpPr><p:cNvPr id="6" name="Note" hidden="1"/><p:cNvSpPr/><p:nvPr/>'
          '</p:nvSpPr><p:spPr/></p:sp>')


def picture_xml(ident: int, rel: str, crop: str = '', video: bool = False) -> str:
    media = (f'<a:videoFile r:link="rId9"/>' if video else '')
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{ident}" name="Picture {ident}" descr="Racks"/>'
            f'<p:cNvPicPr/><p:nvPr>{media}</p:nvPr></p:nvPicPr><p:blipFill>'
            f'<a:blip r:embed="{rel}"/>{crop}</p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/>'
            '<a:ext cx="9144000" cy="5143500"/></a:xfrm></p:spPr></p:pic>')


def original(path: Path, count: int, pictured: int | None, media: str = 'image1.png',
             data: bytes | None = None, shapes: str | None = None, target: str | None = None,
             corrupt: bool = False) -> None:
    """A deck of `count` slides as PowerPoint writes one. Slide `pictured` shows `shapes`,
    by default one picture, kept as ppt/media/`media` (`data`, a 16 by 9 PNG unless said)
    and named by `target`; every other slide shows a word. `corrupt` spoils the picture's
    compressed bytes in the file."""
    ids = ''.join(f'<p:sldId id="{255 + n}" r:id="rId{n}"/>' for n in range(1, count + 1))
    rels = ''.join(f'<Relationship Id="rId{n}" Type="{R}/slide" Target="slides/slide{n}.xml"/>'
                   for n in range(1, count + 1))
    data = png() if data is None else data
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as deck:
        deck.writestr('ppt/presentation.xml', f'<p:presentation xmlns:p="{P}" xmlns:r="{R}">'
                      f'<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>')
        deck.writestr('ppt/_rels/presentation.xml.rels',
                      f'<Relationships xmlns="{REL}">{rels}</Relationships>')
        for n in range(1, count + 1):
            shown = (picture_xml(4, 'rId2') if shapes is None else shapes) if n == pictured \
                else ('<p:sp><p:nvSpPr><p:cNvPr id="2" name="Text"/><p:cNvSpPr/><p:nvPr/>'
                      '</p:nvSpPr><p:txBody><a:p><a:r><a:t>Words</a:t></a:r></a:p>'
                      '</p:txBody></p:sp>')
            deck.writestr(f'ppt/slides/slide{n}.xml',
                          f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld>'
                          f'<p:spTree>{shown}</p:spTree></p:cSld></p:sld>')
            if n == pictured:
                deck.writestr(f'ppt/slides/_rels/slide{n}.xml.rels',
                              f'<Relationships xmlns="{REL}"><Relationship Id="rId2" '
                              f'Type="{R}/image" Target="{target or "../media/" + media}"/>'
                              '</Relationships>')
        deck.writestr(f'ppt/media/{media}', data)
    if corrupt:
        with zipfile.ZipFile(path) as deck:
            info = deck.getinfo(f'ppt/media/{media}')
        raw = bytearray(path.read_bytes())
        start = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        raw[start:start + 8] = b'\xff' * 8
        path.write_bytes(bytes(raw))


class WordlessTests(Deck):
    """At brand only and polish, a slide whose original shows no words is set on a template
    layout that shows no title when its one picture can be carried there; otherwise it is
    drawn as before, under its title, with a note at the gate."""
    route = 'existing'
    BARE = 'when-capacity-holds'   # the third slide
    PICTURE = {'id': '4', 'type': 'pic', 'text': '', 'runs': [], 'alt': 'Racks of servers'}

    def setUp(self):
        super().setUp()
        self.outline = copy.deepcopy(OUTLINE)
        self.outline['slides'][2] = {
            'id': self.BARE, 'kind': 'content', 'relation': 'none', 'points': [],
            'title': BY_ID[self.BARE]['title'], 'understand': 'A picture of the racks.',
            'notes': BY_ID[self.BARE]['notes'], 'sources': BY_ID[self.BARE]['sources']}
        self.count = len(self.outline['slides'])
        self.objects([self.PICTURE])
        (self.root / 'sources').mkdir()
        original(self.root / existing.SOURCE, self.count, 3)

    def objects(self, found: list[dict], number: int = 3) -> None:
        """The inventory, with `found` the objects of slide `number`."""
        slides = [{'number': n, 'id': str(255 + n), 'title': 'Words', 'objects': [
            {'id': '2', 'type': 'sp', 'text': 'Words', 'runs': ['Words']}]}
            for n in range(1, self.count + 1)]
        slides[number - 1] = {'number': number, 'id': str(255 + number), 'title': '',
                              'objects': found}
        (self.root / 'classify.json').write_text(json.dumps({'slides': slides}))

    def at(self, level, outline=None):
        self.run_['form']['level'] = level
        (self.root / 'outline.json').write_text(json.dumps(outline or self.outline))

    def began(self) -> dict:
        return build.read_state(self.root)['start']

    def delivered_words(self) -> list[str]:
        """The words written on each slide of the delivered deck."""
        build.render(self.root, self.run_, self.slides)
        with zipfile.ZipFile(build.delivered_deck(self.root, self.run_)) as deck:
            return [deck.read(f'ppt/slides/slide{n}.xml').decode()
                    for n in range(1, self.count + 1)]

    def carried(self) -> None:
        """Build at brand only; slide 3 is set on the layout with its picture, wordless."""
        self.at('brand-only')
        self.built()
        placed = self.began()['wordless']
        self.assertEqual(placed, {self.BARE: {'layout': 'Quote', 'picture': {
            'src': 'pictures/slide-3.png', 'alt': 'Racks of servers'}}})
        self.assertEqual(self.began()['titled'], {})
        words = self.delivered_words()
        self.assertNotIn('<a:t>', words[2], 'no words at all on that slide')
        self.assertIn(BY_ID['what-it-does']['title'], words[1])

    def falls_back(self, note=build.TITLED, image=True) -> None:
        """Build at brand only; slide 3 is drawn as before, under its title, with its
        picture as a fixed image where `image`, and the gate says so on that slide."""
        self.at('brand-only')
        self.built()
        began = self.began()
        self.assertEqual(began['wordless'], {})
        self.assertEqual(list(began['titled']), [self.BARE])
        self.assertEqual(began['titled'][self.BARE]['note'], note)
        self.assertIs('image' in began['titled'][self.BARE], image)
        compiled = self.root / build.read_state(self.root)['rounds'][-1]['compiled']
        scene = json.loads((compiled / 'scene.json').read_text())
        elements = [element for slide in scene['slides'] if slide['id'] == self.BARE
                    for element in slide['elements']]
        self.assertTrue(any(element['id'].endswith('shape') for element in elements))
        self.assertIs(any(element.get('type') == 'image' for element in elements), image)
        notes = {slide['number']: slide.get('note')
                 for slide in build.gate_view(self.root, self.run_)['slides']}
        self.assertEqual({number: said for number, said in notes.items() if said}, {3: note})
        self.assertIn(BY_ID[self.BARE]['title'], self.delivered_words()[2])

    # --- carried onto a layout without a title

    def test_brand_only_and_polish_set_it_on_a_layout_without_a_title(self):
        self.carried()
        self.assertEqual((self.root / build.START / 'pictures' / 'slide-3.png').read_bytes(),
                         png())
        self.at('polish')
        self.built()
        self.assertIn(self.BARE, self.began()['wordless'])
        self.assertNotIn('<a:t>', self.delivered_words()[2])

    def test_a_picture_cropped_to_the_slot_s_shape_is_carried(self):
        crop = '<a:srcRect t="21875" b="21875"/>'   # a square cut to 16 by 9
        original(self.root / existing.SOURCE, self.count, 3, data=png(16, 16),
                 shapes=picture_xml(4, 'rId2', crop))
        self.carried()

    def test_a_target_named_from_the_package_root_is_carried(self):
        original(self.root / existing.SOURCE, self.count, 3, target='/ppt/media/image1.png')
        self.carried()

    def test_a_picture_under_an_empty_title_placeholder_is_carried(self):
        self.objects([{'id': '2', 'type': 'sp', 'text': '', 'runs': []}, self.PICTURE])
        original(self.root / existing.SOURCE, self.count, 3,
                 shapes=EMPTY_TITLE + picture_xml(4, 'rId2'))
        self.carried()

    def test_a_picture_beside_a_hidden_shape_is_carried(self):
        self.objects([self.PICTURE, {'id': '6', 'type': 'sp', 'text': '', 'runs': []}])
        original(self.root / existing.SOURCE, self.count, 3,
                 shapes=picture_xml(4, 'rId2') + HIDDEN)
        self.carried()

    def test_the_composer_is_told_the_layout_and_may_not_change_it(self):
        self.at('brand-only')
        build.start(self.root, self.run_, self.slides, self.contract)
        section = next(entry['id'] for entry in self.began()['sections']
                       if self.BARE in entry['slides'])
        work = build.section_work(self.root, self.run_, section, None, None)
        spec = work.prepared['artifacts']['section']
        mine = next(slide for slide in spec['slides'] if slide['id'] == self.BARE)
        self.assertEqual(mine['layout'], 'Quote')
        self.assertIn('Quote', work.task)
        self.assertNotIn(str(self.root), work.task)
        self.assertIn('copy it exactly as given',
                      (self.root / build.START / 'given' / f'{section}.md').read_text())
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

    # --- drawn as before, under its title

    def test_a_picture_of_another_shape_than_the_slot_keeps_it_under_its_title(self):
        original(self.root / existing.SOURCE, self.count, 3, data=png(9, 16))
        self.falls_back()

    def test_the_composer_must_place_the_fixed_picture(self):
        original(self.root / existing.SOURCE, self.count, 3, data=png(9, 16))
        self.at('brand-only')
        build.start(self.root, self.run_, self.slides, self.contract)
        section = next(entry['id'] for entry in self.began()['sections']
                       if self.BARE in entry['slides'])
        work = build.section_work(self.root, self.run_, section, None, None)
        spec = work.prepared['artifacts']['section']
        mine = next(slide for slide in spec['slides'] if slide['id'] == self.BARE)
        self.assertEqual(mine['image'], {'type': 'image', 'id': mine['image']['id'],
                                         'src': 'pictures/slide-3.png',
                                         'alt': 'Racks of servers', 'fit': 'contain'})
        self.assertIn(json.dumps(mine['image']), work.task)
        handed = json.loads(drawn(spec))
        self.assertEqual(build.kept(handed, spec), [])
        at = [slide['id'] for slide in handed['slides']].index(self.BARE)
        for canvas in ({'type': 'box', 'id': f"{spec['prefix']}shape"},
                       {'type': 'stack', 'direction': 'column', 'children': [
                           {**mine['image'], 'fit': 'cover'}]}):
            wrong = copy.deepcopy(handed)
            wrong['slides'][at]['canvas'] = canvas
            self.assertTrue(build.kept(wrong, spec), canvas)

    def test_a_picture_under_an_empty_title_without_a_fitting_slot_keeps_it(self):
        self.objects([{'id': '2', 'type': 'sp', 'text': '', 'runs': []}, self.PICTURE])
        original(self.root / existing.SOURCE, self.count, 3, data=png(9, 16),
                 shapes=EMPTY_TITLE + picture_xml(4, 'rId2'))
        self.falls_back()

    def test_without_image_nodes_the_note_says_it_is_drawn_afresh(self):
        original(self.root / existing.SOURCE, self.count, 3, data=png(9, 16))
        real = self.slides.compose_contract
        with mock.patch.object(self.slides, 'compose_contract',
                               lambda brand: real(brand).replace('image', 'picture')):
            self.falls_back(build.REDRAWN, image=False)

    def test_two_pictures_are_drawn_as_before(self):
        self.objects([self.PICTURE, {**self.PICTURE, 'id': '5'}])
        original(self.root / existing.SOURCE, self.count, 3,
                 shapes=picture_xml(4, 'rId2') + picture_xml(5, 'rId2'))
        self.falls_back(build.REDRAWN, image=False)

    def test_a_picture_with_a_shape_is_drawn_as_before(self):
        self.objects([self.PICTURE, {'id': '5', 'type': 'sp', 'text': '', 'runs': []}])
        original(self.root / existing.SOURCE, self.count, 3,
                 shapes=picture_xml(4, 'rId2') + SHAPE)
        self.falls_back(build.REDRAWN, image=False)

    def test_a_video_s_poster_frame_is_drawn_as_before(self):
        original(self.root / existing.SOURCE, self.count, 3,
                 shapes=picture_xml(4, 'rId2', video=True))
        self.falls_back(build.REDRAWN, image=False)

    def test_a_slide_of_shapes_alone_keeps_its_drawing_under_its_title(self):
        self.objects([{'id': '5', 'type': 'sp', 'text': '', 'runs': []}])
        original(self.root / existing.SOURCE, self.count, 3, shapes=SHAPE)
        self.falls_back(build.REDRAWN, image=False)

    def test_a_picture_the_slides_tool_cannot_place_is_drawn_as_before(self):
        original(self.root / existing.SOURCE, self.count, 3, media='image1.emf',
                 data=b'\x01\x00\x00\x00 an enhanced metafile')
        self.falls_back(build.REDRAWN, image=False)

    def test_a_damaged_picture_is_drawn_as_before_and_the_build_goes_on(self):
        original(self.root / existing.SOURCE, self.count, 3, corrupt=True)
        self.assertIsNone(existing.original_picture(self.root, 3, self.base / 'out'))
        self.falls_back(build.REDRAWN, image=False)

    def test_a_template_without_a_title_less_layout_with_a_picture_slot(self):
        self.slides.run.layouts = tuple(layout for layout in self.slides.run.layouts
                                        if layout[1] or not layout[3])
        self.falls_back()

    def test_a_template_with_no_layout_without_a_title_goes_on(self):
        self.slides.run.layouts = tuple(layout for layout in self.slides.run.layouts
                                        if layout[1])
        self.falls_back()
        self.assertIsNone(decks.read_run(self.root).get('halted'))

    def test_a_slot_whose_size_cannot_be_read(self):
        with mock.patch.object(existing, 'template_slot', lambda *given: None):
            self.falls_back()

    def test_a_lead_slide_with_no_words_is_left_to_its_layout(self):
        self.objects([self.PICTURE], number=1)
        original(self.root / existing.SOURCE, self.count, 1)
        self.at('brand-only')
        build.start(self.root, self.run_, self.slides, self.contract)
        self.assertEqual((self.began()['wordless'], self.began()['titled']), ({}, {}))

    def test_redesign_draws_its_title_as_before(self):
        self.at('redesign', OUTLINE)
        self.built()
        self.assertEqual((self.began()['wordless'], self.began()['titled']), ({}, {}))
        self.assertIn(BY_ID[self.BARE]['title'], self.delivered_words()[2])
        self.assertFalse(any(slide.get('note') for slide in
                             build.gate_view(self.root, self.run_)['slides']))


if __name__ == '__main__':
    unittest.main()
