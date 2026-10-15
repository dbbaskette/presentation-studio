"""What a person marks at a stop reviewed item by item: checked, and the note it becomes."""
import unittest

import helpers  # noqa: F401
from workspace import WorkspaceError

from runner import marks

QUESTIONS = ['instance-min', 'health-checks']
SLIDES = ['cover-restarts', 'what-it-does']


class CheckTests(unittest.TestCase):
    def test_a_stop_not_reviewed_item_by_item_has_no_marks(self):
        self.assertEqual(marks.check('gate:build', 'approve', {'slides': [2]}, []), {})

    def test_plan_marks_are_cleaned(self):
        marked = marks.check('gate:research-plan', 'changes', {
            'dropped': ['health-checks', 'health-checks'],
            'reword': {'instance-min': '  How many   instances? '},
            'add': ['  What does it cost? ']}, QUESTIONS)
        self.assertEqual(marked, {'dropped': ['health-checks'],
                                  'reword': {'instance-min': 'How many instances?'},
                                  'add': ['What does it cost?']})

    def test_plan_refusals(self):
        for extra, said in (
                ({'dropped': ['nowhere']}, 'There is no question nowhere here.'),
                ({'dropped': QUESTIONS}, marks.ALL_DROPPED),
                ({'reword': {'instance-min': '  '}}, 'Say what should change for instance-min.'),
                ({'dropped': ['instance-min'], 'reword': {'instance-min': 'Again?'}},
                 'instance-min is both dropped and reworded'),
                ({'add': ['']}, 'A question to add is empty.'),
                ({'add': ['Why?'] * 11}, 'Add at most 10 questions at once.'),
                ({'dropped': 'health-checks'}, 'Name each question by its ID.')):
            with self.subTest(extra=extra):
                with self.assertRaises(WorkspaceError) as caught:
                    marks.check('gate:research-plan', 'changes', extra, QUESTIONS)
                self.assertIn(said, str(caught.exception))

    def test_only_drops_go_with_approve_at_the_plan(self):
        self.assertEqual(marks.check('gate:research-plan', 'approve',
                                     {'dropped': ['health-checks']}, QUESTIONS),
                         {'dropped': ['health-checks']})
        with self.assertRaises(WorkspaceError) as caught:
            marks.check('gate:research-plan', 'approve', {'add': ['Why?']}, QUESTIONS)
        self.assertEqual(str(caught.exception), marks.AS_CHANGES)

    def test_research_marks_keep_an_empty_left_out_and_an_empty_line(self):
        marked = marks.check('gate:research', 'changes',
                             {'left_out': [], 'again': {'health-checks': ''}}, QUESTIONS)
        self.assertEqual(marked, {'left_out': [], 'again': {'health-checks': ''}})
        self.assertEqual(marks.check('gate:research', 'approve', {}, QUESTIONS), {})

    def test_research_refusals(self):
        for extra, said in (
                ({'left_out': QUESTIONS}, marks.ALL_LEFT_OUT),
                ({'left_out': ['instance-min'], 'again': {'instance-min': ''}},
                 'instance-min is both left out and researched again'),
                ({'again': {'nowhere': ''}}, 'There is no question nowhere here.')):
            with self.subTest(extra=extra):
                with self.assertRaises(WorkspaceError) as caught:
                    marks.check('gate:research', 'changes', extra, QUESTIONS)
                self.assertIn(said, str(caught.exception))
        with self.assertRaises(WorkspaceError):
            marks.check('gate:research', 'approve', {'again': {'instance-min': ''}}, QUESTIONS)

    def test_outline_marks_need_a_line_and_go_as_changes(self):
        self.assertEqual(marks.check('gate:outline', 'changes',
                                     {'slides': {'what-it-does': 'Split it.'}}, SLIDES),
                         {'slides': {'what-it-does': 'Split it.'}})
        for extra in ({'slides': {'what-it-does': ''}}, {'slides': {'nowhere': 'Split.'}}):
            with self.subTest(extra=extra), self.assertRaises(WorkspaceError):
                marks.check('gate:outline', 'changes', extra, SLIDES)
        with self.assertRaises(WorkspaceError):
            marks.check('gate:outline', 'approve', {'slides': {'what-it-does': 'Split.'}},
                        SLIDES)

    def test_what_asks_a_worker(self):
        self.assertFalse(marks.asks({}))
        self.assertFalse(marks.asks({'left_out': ['instance-min']}))
        self.assertTrue(marks.asks({'again': {'instance-min': ''}}))
        self.assertTrue(marks.asks({'dropped': ['instance-min']}))


class NoteTests(unittest.TestCase):
    def test_the_note_lists_each_mark_then_the_person_s_own_words(self):
        said = marks.note('gate:research-plan', {
            'reword': {'instance-min': 'How many instances?'}, 'add': ['What does it cost?'],
            'dropped': ['health-checks']}, 'Keep it short.')
        self.assertEqual(said, '- Reword `instance-min` as: How many instances?\n'
                               '- Add a question: What does it cost?\n'
                               '- `health-checks` is dropped: leave it out.\n\n'
                               'Keep it short.')

    def test_research_and_outline_notes(self):
        self.assertEqual(marks.note('gate:research', {
            'again': {'instance-min': 'Use the docs.', 'health-checks': ''},
            'add': ['Why?'], 'left_out': ['other']}, None),
            '- Research `instance-min` again: Use the docs.\n'
            '- Research `health-checks` again.\n- Add a question: Why?\n'
            '- Leave out `other`.')
        self.assertEqual(marks.note('gate:outline', {'slides': {'what-it-does': 'Split it.'}},
                                    None), '- Slide `what-it-does`: Split it.')

    def test_no_marks_and_no_words_is_no_note(self):
        self.assertIsNone(marks.note('gate:outline', {}, None))
        self.assertEqual(marks.note('gate:outline', {}, 'Shorter.'), 'Shorter.')


class WordsTests(unittest.TestCase):
    def test_a_title_is_read_from_an_id(self):
        self.assertEqual(marks.title('licensing-cost'), 'Licensing cost')
        self.assertEqual(marks.title('market-players-2'), 'Market players 2')

    def test_a_new_id_is_made_from_the_question_and_never_taken(self):
        self.assertEqual(marks.new_id('What does a rolling restart cost?', []),
                         'what-does-a-rolling-restart')
        self.assertEqual(marks.new_id('What does a rolling restart cost?',
                                      ['what-does-a-rolling-restart']),
                         'what-does-a-rolling-restart-2')
        self.assertEqual(marks.new_id('???', []), 'question')

    def test_the_first_sentence(self):
        self.assertEqual(marks.first_sentence('One thing. Then another.'), 'One thing.')
        self.assertEqual(marks.first_sentence('  No stop at all '), 'No stop at all')
        self.assertEqual(marks.first_sentence(None), '')


if __name__ == '__main__':
    unittest.main()
