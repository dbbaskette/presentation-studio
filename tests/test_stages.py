import unittest

import helpers  # noqa: F401
from runner import stages


def run(route, level=None, research=False, classified=None):
    form = {'route': route, 'research': research}
    if level:
        form['level'] = level
    return {'route': route, 'form': form, 'classified': classified, 'gates': {}, 'steps': {}}


def names(r):
    return [s.name for s in stages.steps(r)]


class SkipMapTests(unittest.TestCase):
    CASES = [
        (run('scratch'), ['intake-source', 'outline', 'gate:outline', 'brand',
                          'look-preview', 'gate:look', 'build-start', 'build-sections',
                          'build-whole', 'build-review', 'build-repair', 'build-render',
                          'gate:build', 'deliver', 'rehearse']),
        (run('existing', 'brand-only'), ['intake-source', 'inventory', 'gate:classify',
                                         'extract', 'brand', 'build-start', 'build-sections',
                                         'build-whole', 'build-review', 'build-repair',
                                         'build-render', 'gate:build', 'deliver', 'rehearse']),
        (run('existing', 'selected'), ['intake-source', 'inventory', 'gate:classify', 'brand',
                                       'patch', 'build-render', 'gate:build', 'deliver',
                                       'rehearse']),
        (run('existing', 'rework'), ['intake-source', 'inventory', 'gate:classify', 'extract',
                                     'outline', 'gate:outline', 'brand', 'look-preview',
                                     'gate:look', 'build-start', 'build-sections', 'build-whole',
                                     'build-review', 'build-repair', 'build-render',
                                     'gate:build', 'deliver', 'rehearse']),
    ]

    def test_cases(self):
        for r, expected in self.CASES:
            with self.subTest(route=r['route'], level=r['form'].get('level')):
                self.assertEqual(names(r), expected)

    def test_research_only_when_asked(self):
        self.assertIn('research-plan', names(run('scratch', research=True)))
        self.assertNotIn('research-plan', names(run('scratch')))

    def test_document_research_only_for_material(self):
        self.assertNotIn('research', names(run('document', research=True, classified='spec')))
        self.assertIn('research', names(run('document', research=True, classified='material')))

    def test_polish_and_brand_only_skip_look(self):
        for level in ('brand-only', 'polish'):
            self.assertNotIn('gate:look', names(run('existing', level)))
        self.assertIn('gate:look', names(run('existing', 'redesign')))


class SurveyTests(unittest.TestCase):
    def test_first_step_is_next(self):
        self.assertEqual(stages.survey(run('scratch')).next.name, 'intake-source')

    def test_waiting_gate(self):
        r = run('scratch')
        r['steps'] = {'intake-source': {'done': True}, 'outline': {'done': True}}
        r['gates'] = {'gate:outline': {'state': 'waiting'}}
        found = stages.survey(r)
        self.assertEqual(found.waiting, 'gate:outline')

    def test_changes_go_back_to_the_feeding_step(self):
        r = run('scratch')
        r['steps'] = {'intake-source': {'done': True}, 'outline': {'done': True}}
        r['gates'] = {'gate:outline': {'state': 'changes', 'note': 'shorter'}}
        r = stages.reopen(r, 'gate:outline')
        self.assertEqual(stages.survey(r).next.name, 'outline')

    def test_finished_deck_has_no_next(self):
        r = run('existing', 'selected')
        for s in stages.steps(r):
            if s.kind == 'gate':
                r['gates'][s.name] = {'state': 'approved'}
            else:
                r['steps'][s.name] = {'done': True}
        self.assertIsNone(stages.survey(r).next)

    def test_rehearse_is_later_in_the_timeline(self):
        rows = stages.timeline(run('scratch'))
        self.assertEqual(rows[-1]['state'], 'later')


class FeedAndReopenTests(unittest.TestCase):
    def test_feeders(self):
        self.assertEqual(stages.feeder(run('existing', 'polish'), 'gate:classify'), 'inventory')
        self.assertEqual(stages.feeder(run('document'), 'gate:classify'), 'classify')
        self.assertEqual(stages.feeder(run('existing', 'selected'), 'gate:build'), 'patch')
        r = run('scratch')
        self.assertEqual(stages.feeder(r, 'gate:build'), 'build-sections')
        r['gates'] = {'gate:build': {'state': 'changes', 'slides': [3]}}
        self.assertEqual(stages.feeder(r, 'gate:build'), 'build-repair')
        # Another brand is chosen at the brand's gate: its cover is drawn again, by the runner.
        self.assertEqual(stages.feeder(r, 'gate:look'), 'look-preview')
        self.assertEqual(stages.BY_NAME['look-preview'].kind, 'code')

    def test_reopen_clears_later_work_and_approvals(self):
        r = run('scratch')
        r['steps'] = {s.name: {'done': True} for s in stages.steps(r) if s.kind != 'gate'}
        r['gates'] = {n: {'state': 'approved'} for n in ('gate:outline', 'gate:look', 'gate:build')}
        r['gates']['gate:outline'] = {'state': 'changes', 'note': 'shorter'}
        out = stages.reopen(r, 'gate:outline')
        self.assertTrue(r['steps']['outline']['done'])  # the original is untouched
        self.assertFalse(out['steps']['outline']['done'])
        self.assertFalse(out['steps']['build-render']['done'])
        self.assertTrue(out['steps']['intake-source']['done'])
        self.assertEqual(out['gates']['gate:look']['state'], 'absent')
        self.assertEqual(out['gates']['gate:outline'], {'state': 'changes', 'note': 'shorter'})

    def test_halted_and_wording(self):
        r = run('scratch')
        r['halted'] = {'why': 'out of credit'}
        self.assertEqual(stages.survey(r).halted, 'out of credit')
        for s in stages.PIPELINE:
            for word in ('artifact', 'stale', 'lineage', '{'):
                self.assertNotIn(word, (s.label + s.doing).lower())
