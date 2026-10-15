"""The brand a deck is made in, shown as its cover before any slide is designed, and another
brand chosen in its place. The slides tool and the brand skill are the stand-ins."""
import json
import tempfile
import unittest
from pathlib import Path

import runner_support
from runner_support import OUTLINE
from workspace import WorkspaceError

from runner import decks
from runner.steps import build, look

BRANDS = [{'brand': 'example', 'name': 'Example Co', 'variants': ['light', 'dark']}]


class Case(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / 'deck'
        self.root.mkdir()
        form = {'route': 'scratch', 'title': 'Rolling restarts', 'brand': 'example',
                'variant': 'light', 'audience': 'Ops', 'goal': '', 'minutes': None,
                'output': 'google', 'research': False}
        self.run_ = {'schema': 1, 'id': 'd', 'title': 'Rolling restarts', 'route': 'scratch',
                     'form': form,
                     'gates': {'gate:outline': {'state': 'approved', 'note': 'Keep it short.'}},
                     'steps': {}, 'look': None}
        decks.write_run(self.root, self.run_)
        (self.root / 'intake.md').write_text(decks.intake(form), encoding='utf-8')
        (self.root / 'outline.json').write_text(json.dumps(OUTLINE), encoding='utf-8')
        self.slides = runner_support.stand_in_slides()
        self.brand = runner_support.stand_in_brand()   # its folder lasts as long as it does
        self.contract = build.export_brand(self.root, self.run_, self.brand)


class SampleTests(Case):
    def test_the_cover_is_drawn_alone_in_the_brand_s_own_colours(self):
        listed = self.slides.layouts(self.contract).get('layouts')
        made = look.composition(OUTLINE, 'Rolling restarts', listed)
        cover = OUTLINE['slides'][0]
        self.assertEqual(made['direction'], build.DIRECTION)
        (slide,) = made['slides']
        self.assertEqual((slide['id'], slide['title'], slide['subtitle']),
                         (cover['id'], cover['title'], cover['subtitle']))
        self.assertEqual(slide['layout'], build.layouts(listed, [cover])['cover'])

    def test_an_outline_with_no_cover_is_shown_the_deck_s_title_on_one(self):
        listed = self.slides.layouts(self.contract).get('layouts')
        bare = {**OUTLINE, 'slides': [one for one in OUTLINE['slides']
                                      if one.get('kind') != 'cover']}
        (slide,) = look.composition(bare, 'Rolling restarts', listed)['slides']
        self.assertEqual((slide['id'], slide['title']), ('cover', OUTLINE['title']))
        self.assertNotIn('subtitle', slide)

    def test_the_sample_is_pictured_and_the_gate_waits(self):
        drawn = look.preview_sample(self.root, self.run_, self.slides, 'local')
        self.assertEqual(drawn, self.root / look.SAMPLE)
        self.assertEqual(drawn.read_bytes()[:8], build.PNG)
        said = (self.root / 'look.md').read_text()
        self.assertIn('This deck is made in example (light).', said)
        self.assertIn('each slide is designed on its own', said)
        gate = decks.read_run(self.root)['gates']['gate:look']
        self.assertEqual((gate['state'], gate['round']), ('waiting', 1))

    def test_a_sample_that_will_not_draw_says_so_and_leaves_nothing(self):
        (self.root / build.CONTRACT).unlink()
        with self.assertRaises(WorkspaceError) as caught:
            look.draw_sample(self.root, self.run_, self.slides, 'local')
        self.assertIn('Your cover could not be drawn in the brand.', str(caught.exception))
        self.assertFalse((self.root / look.FOLDER).exists())


class RebrandTests(Case):
    def test_another_variant_is_named_and_the_old_contract_removed(self):
        form = look.rebrand(self.root, self.run_, 'example', 'dark', BRANDS)
        self.assertEqual((form['brand'], form['variant']), ('example', 'dark'))
        self.assertEqual(self.run_['form']['variant'], 'dark')
        self.assertIn('example (dark)', (self.root / 'intake.md').read_text())
        self.assertFalse((self.root / build.BRAND).exists())

    def test_a_brand_with_no_variant_named_takes_its_first(self):
        self.run_['form']['brand'] = 'other'
        form = look.rebrand(self.root, self.run_, 'example', None, BRANDS)
        self.assertEqual(form['variant'], 'light')

    def test_what_is_not_offered_and_what_it_is_already_are_refused(self):
        for brand, variant, said in (('', None, 'Choose the brand'),
                                     ('nobody', None, 'nobody'),
                                     ('example', 'neon', 'neon'),
                                     ('example', 'light', 'already')):
            with self.subTest(brand=brand, variant=variant):
                with self.assertRaises(WorkspaceError) as caught:
                    look.rebrand(self.root, self.run_, brand, variant, BRANDS)
                self.assertIn(said, str(caught.exception))
                self.assertEqual(self.run_['form']['variant'], 'light')
                self.assertTrue((self.root / build.CONTRACT).is_file())


class ApproveTests(Case):
    def test_the_approval_is_written_into_the_outline_with_no_direction(self):
        outline = {**OUTLINE, 'direction': {'focal': 'accentAqua', 'neutral': 'canvasPrimary',
                                            'motif': 'Open columns on every slide.'}}
        (self.root / 'outline.json').write_text(json.dumps(outline), encoding='utf-8')
        look.approve(self.root, self.run_, note='Looks right.')
        kept = json.loads((self.root / 'outline.json').read_text())
        self.assertNotIn('direction', kept)
        self.assertIn('in example (light).', kept['approval'][0])
        self.assertEqual(kept['approval'][1:], ['Keep it short.', 'Looks right.'])
        gate = decks.read_run(self.root)['gates']['gate:look']
        self.assertEqual((gate['state'], gate['note']), ('approved', 'Looks right.'))
        self.assertFalse((self.root / 'look.json').exists())

    def test_every_slide_is_designed_in_the_brand_s_own_colours(self):
        look.approve(self.root, self.run_)
        build.start(self.root, self.run_, self.slides, self.contract)
        started = json.loads((self.root / build.START / 'outline.json').read_text())
        self.assertEqual(started['direction'], build.DIRECTION)
        self.assertNotIn('motif', started['direction'])


if __name__ == '__main__':
    unittest.main()
