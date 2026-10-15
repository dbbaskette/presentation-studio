import re
import unittest

import helpers  # noqa: F401
from runner import briefs, worker_tools

TOOLS = set(worker_tools.NAMES) | {'search_icons'}


class BriefTests(unittest.TestCase):
    def test_every_kind_loads(self):
        for kind in briefs.KINDS:
            with self.subTest(kind=kind):
                self.assertGreater(len(briefs.guidance(kind)), 200)

    def test_briefs_name_only_worker_tools(self):
        for kind in briefs.KINDS:
            named = set(re.findall(r'`([a-z_]+)`', briefs.guidance(kind)))
            self.assertLessEqual({n for n in named if '_' in n}, TOOLS, kind)

    def test_levels_and_repair(self):
        for level in briefs.LEVELS:
            self.assertIn('## The freedom', briefs.guidance('extract', level=level))
        self.assertEqual(briefs.guidance('section', repair=True), briefs.read('section-repair'))
        with self.assertRaises(ValueError):
            briefs.guidance('look', level='polish')

    def test_no_commands_or_paths(self):
        for kind in briefs.KINDS:
            text = briefs.guidance(kind)
            self.assertNotIn('harness-slides.mjs', text, kind)
            self.assertNotRegex(text, r'(?m)^\s*node ', kind)

    def test_extract_states_the_verbatim_rule(self):
        self.assertIn('exactly', briefs.guidance('extract', level='brand-only'))

    def test_no_training_words(self):
        for kind in briefs.KINDS:
            self.assertNotRegex(briefs.guidance(kind).lower(),
                                r'blueprint|learner|yoodli|training|objective', kind)

    OUTLINE_BRIEFS = ('outline-brief', 'outline-material', 'outline-spec', 'extract', 'restructure')

    def test_rhythms_and_kinds_are_the_contracts(self):
        for kind in self.OUTLINE_BRIEFS:
            self.assertNotRegex(briefs.guidance(kind), r'dense, light|ten words', kind)
        for kind in ('outline-brief', 'outline-material', 'outline-spec'):
            text = briefs.guidance(kind)
            for word in ('anchor', 'dense', 'breathing', '`cover`', '`section`',
                         '`closing`', '`content`'):
                self.assertIn(word, text, kind)
            self.assertNotRegex(text, r'\blight\b', kind)

    def test_each_level_has_its_note(self):
        notes = {'brand-only': 'The freedom: brand only', 'polish': 'The freedom: polish',
                 'redesign': 'The freedom: redesign', 'rework': 'The freedom: rework'}
        for level, note in notes.items():
            text = briefs.guidance('extract', level=level)
            self.assertIn(note, text)
            self.assertEqual(sum(n in text for n in notes.values()), 1)

    def test_sources_cite_original_slides(self):
        for level in briefs.LEVELS:
            text = briefs.guidance('extract', level=level)
            self.assertIn('slide-<n>', text)
            self.assertNotIn('existing_deck', text)
        self.assertIn('slide-<n>', briefs.guidance('restructure'))
        self.assertNotIn('existing_deck', briefs.guidance('restructure'))

    def test_hand_back_names(self):
        self.assertIn('`classification`', briefs.guidance('classify'))
        self.assertIn('`look`', briefs.guidance('look'))
        self.assertIn('`patch`', briefs.guidance('patch'))
        self.assertNotIn('preview_section', briefs.guidance('look'))


if __name__ == '__main__':
    unittest.main()
