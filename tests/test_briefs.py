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


if __name__ == '__main__':
    unittest.main()
