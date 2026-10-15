"""The engine: a deck walked through its steps by scripted workers, stopping at each gate,
with the slides tool, a brand skill and harness-research as stand-ins. Nothing real is
started, rendered or sent."""
import json
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import runner_support
from runner_support import OUTLINE, StudioCase, asks, fails
from workspace import WorkspaceError

from runner import decks, marks, stages
from runner.steps import build


def grave(slides):
    """A major finding about how the second slide is drawn."""
    return [{'slide': slides[1]['id'], 'question': 6, 'severity': 'major',
             'about': 'drawing', 'note': 'The two boxes crowd the left half of the slide.'}]


class DispatchTests(unittest.TestCase):
    def test_every_step_of_the_pipeline_has_what_the_engine_does_for_it(self):
        from runner import engine
        self.assertEqual(set(engine.RUN), {step.name for step in stages.PIPELINE})
        for name, method in engine.RUN.items():
            if name != 'rehearse':
                self.assertTrue(callable(getattr(engine.Engine, method)), name)


class ScratchTests(StudioCase):
    def test_a_scratch_deck_stops_at_each_gate_and_is_delivered(self):
        root = self.start()
        self.assertEqual(self.waiting(root), 'gate:outline')
        view = self.view(root)
        self.assertEqual(view['state'], 'waiting')
        self.assertEqual([slide['id'] for slide in view['gate']['slides']],
                         [slide['id'] for slide in OUTLINE['slides']])
        self.assertIn('## 1. Rolling restarts', view['gate']['text'])
        before = len(self.log())
        self.decide(root, 'gate:outline')
        self.assertEqual(self.waiting(root), 'gate:look')
        look = self.view(root)['gate']
        self.assertEqual((look['brand'], look['variant'], look['made_in']),
                         ('example', 'light', 'example (light)'))
        self.assertEqual(look['picture'], {'kind': 'look', 'ref': 'sample'})
        self.assertIn('This deck is made in example (light).', look['text'])
        self.assertTrue(self.engine.picture(root, 'look', 'sample').startswith(b'\x89PNG'))
        # No assistant drew it, and no look was proposed to choose from.
        self.assertEqual([seen for seen, job, spec in self.workers.jobs
                          if seen.startswith('look')], [])
        self.decide(root, 'gate:look')
        self.assertFalse((root / 'look.json').exists())
        kept = json.loads((root / 'outline.json').read_text())
        self.assertNotIn('direction', kept)
        self.assertIn('in example (light).', kept['approval'][0])
        self.assertEqual(self.waiting(root), 'gate:build')
        started = json.loads((root / build.START / 'outline.json').read_text())
        self.assertEqual(started['direction'], build.DIRECTION)
        shown = self.view(root)['gate']
        self.assertEqual([slide['number'] for slide in shown['slides']],
                         list(range(1, len(OUTLINE['slides']) + 1)))
        self.assertEqual(shown['slides'][0]['image'], {'kind': 'build', 'ref': 1})
        self.assertNotIn(str(root), json.dumps(shown))
        self.assertTrue(self.engine.picture(root, 'build', 2).startswith(b'\x89PNG'))
        self.assertTrue(self.engine.picture(root, 'build', 'contact-sheet')
                        .startswith(b'\x89PNG'))
        self.decide(root, 'gate:build')
        view = self.view(root)
        self.assertEqual(view['state'], 'finished')
        self.assertEqual(view['deliver']['revision'], 1)
        self.assertTrue(view['deliver']['url'].startswith('https://docs.google.com/'))
        self.assertIsNone(view['gate'])
        self.assertEqual([row['state'] for row in view['timeline']][-1], 'later')
        self.assertTrue(all(row['state'] == 'done' for row in view['timeline'][:-1]))
        decisions = [line for line in self.log()[before:]
                     if line.startswith('Rolling restarts: approve the ')]
        self.assertEqual(decisions, ['Rolling restarts: approve the outline',
                                     'Rolling restarts: approve the brand',
                                     'Rolling restarts: approve the deck'])
        name, data = self.engine.download(root)
        self.assertEqual(name, f'{root.name}.pptx')
        self.assertTrue(data.startswith(b'PK\x03\x04'))
        self.assertIn('Rolling restarts', (self.space.root / 'README.md').read_text())
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_every_decision_is_a_commit(self):
        root = self.start()
        for gate in ('gate:outline', 'gate:look', 'gate:build'):
            count = int(self.git('rev-list', '--count', 'HEAD'))
            head = self.git('rev-parse', 'HEAD')
            self.decide(root, gate)
            said = self.git('log', '--format=%s', f'{head}..HEAD').splitlines()
            self.assertIn(f'Rolling restarts: approve the {stages.BY_NAME[gate].label.split()[-1]}'
                          if gate != 'gate:build' else 'Rolling restarts: approve the deck',
                          said)
            self.assertGreater(int(self.git('rev-list', '--count', 'HEAD')), count)
            decided = self.git('show', '--format=', '--name-only', head + '..HEAD')
            self.assertIn('run.json', decided)

    def test_changes_at_the_outline_run_it_again_with_the_note(self):
        root = self.start()
        self.decide(root, 'gate:outline', 'changes', 'Make the objection its own section.')
        self.assertEqual(len(self.workers.of('outline')), 2)
        again = self.workers.of('outline')[-1]
        self.assertIn('Make the objection its own section.', again.task)
        self.assertIn("Read a person's note at a gate", again.guidance)
        gate = self.record(root)['gates']['gate:outline']
        self.assertEqual(gate['state'], 'waiting')
        self.assertEqual(gate['round'], 2)
        self.assertIn('Rolling restarts: ask for changes to the outline', self.log())

    def test_a_note_is_needed_to_ask_for_changes_and_only_a_waiting_gate_moves(self):
        root = self.start()
        with self.assertRaises(WorkspaceError) as caught:
            self.engine.decide(root, 'gate:outline', 'changes', '  ', None)
        self.assertEqual(str(caught.exception), 'Say what should change.')
        with self.assertRaises(WorkspaceError) as caught:
            self.engine.decide(root, 'gate:look', 'approve', None, None)
        self.assertIn('not waiting for a decision', str(caught.exception))
        with self.assertRaises(WorkspaceError):
            self.engine.decide(root, 'gate:classify', 'changes', 'No.', None)

    def test_another_brand_is_chosen_at_the_brand_and_its_cover_drawn_again(self):
        root = self.start()
        self.to_gate(root, 'gate:look')
        exported = json.loads((root / build.CONTRACT).read_text())
        self.assertEqual(exported['identity']['variant'], 'light')
        for extra, said in ((None, 'Choose the brand, and its variant'),
                            ({'brand': 'example', 'variant': 'light'}, 'already'),
                            ({'brand': 'example', 'variant': 'neon'}, 'neon')):
            with self.subTest(extra=extra):
                with self.assertRaises(WorkspaceError) as caught:
                    self.engine.decide(root, 'gate:look', 'changes', None, extra)
                self.assertIn(said, str(caught.exception))
                self.assertEqual(self.record(root)['form']['variant'], 'light')
        self.engine.decide(root, 'gate:look', 'changes', None,
                           {'brand': 'example', 'variant': 'dark'})
        self.assertEqual(self.waiting(root), 'gate:look')
        record, gate = self.record(root), self.view(root)['gate']
        self.assertEqual(record['form']['variant'], 'dark')
        self.assertEqual(record['gates']['gate:look']['round'], 2)
        self.assertEqual(gate['made_in'], 'example (dark)')
        self.assertEqual(gate['note'], 'Make it in example (dark).')
        self.assertIn('example (dark)', (root / 'intake.md').read_text())
        exported = json.loads((root / build.CONTRACT).read_text())
        self.assertEqual(exported['identity']['variant'], 'dark')
        self.assertIn('Rolling restarts: make it in example (dark)', self.log())
        self.decide(root, 'gate:look')
        self.assertEqual(self.waiting(root), 'gate:build')

    def test_an_edited_outline_is_checked_and_kept_with_the_approval(self):
        root = self.start()
        slides = self.view(root)['gate']['slides']
        moved = [*slides[:2], slides[3], slides[2], *slides[4:]]
        self.engine.decide(root, 'gate:outline', 'approve', None, {'edited': moved})
        kept = json.loads((root / 'outline.json').read_text())
        self.assertEqual([slide['id'] for slide in kept['slides']],
                         [slide['id'] for slide in moved])
        self.assertEqual(self.waiting(root), 'gate:look')

    def test_an_edited_outline_is_kept_before_its_worker_is_asked_for_changes(self):
        root = self.start()
        slides = self.view(root)['gate']['slides']
        moved = [*slides[:2], slides[3], slides[2], *slides[4:]]
        seen = []

        def again(tools, job):
            kept = json.loads((root / 'outline.json').read_text())
            seen.append([slide['id'] for slide in kept['slides']])
            return self.workers.outline(tools, job)

        self.workers.then('outline', again)
        self.engine.decide(root, 'gate:outline', 'changes', 'Shorten the close.',
                           {'edited': moved})
        self.assertEqual(seen, [[slide['id'] for slide in moved]])
        self.assertIn('Shorten the close.', self.workers.of('outline')[-1].task)

    def test_changes_to_the_deck_draw_only_the_sections_of_the_named_slides(self):
        root = self.start()
        self.to_gate(root, 'gate:build')
        drawn = len(self.workers.of('section'))
        self.engine.decide(root, 'gate:build', 'changes', 'Give slide 2 more room.',
                           {'slides': [2]})
        again = self.workers.of('section')[drawn:]
        self.assertEqual(len(again), 1)
        self.assertIn('Give slide 2 more room.', again[0].task)
        self.assertEqual(self.waiting(root), 'gate:build')
        self.assertEqual(self.record(root)['gates']['gate:build']['round'], 2)

    def test_changes_after_delivery_build_and_deliver_a_new_revision(self):
        root = self.start()
        self.to_end(root)
        self.assertEqual(self.state(root), 'finished')
        self.engine.decide(root, 'gate:build', 'changes', 'Shorter titles, please.', None)
        self.assertEqual(self.waiting(root), 'gate:build')
        self.assertIsNone(decks.delivered(root))
        self.decide(root, 'gate:build')
        view = self.view(root)
        self.assertEqual(view['deliver']['revision'], 2)
        self.assertEqual(len(view['deliver']['revisions']), 2)

    def test_a_review_that_finds_a_grave_drawing_has_its_section_drawn_again(self):
        self.workers.found = [grave]
        root = self.start()
        self.to_gate(root, 'gate:build')
        state = build.read_state(root)
        self.assertEqual(len(state['rounds']), 2)
        self.assertEqual(len(self.workers.of('review')), 2)
        self.assertTrue((root / 'reviews' / 'build-1.md').is_file())


class RetryTests(StudioCase):
    def test_a_step_that_fails_three_times_stops_and_retry_carries_on(self):
        self.workers.then('outline', fails(), fails(), fails('The model gave up again.'))
        root = self.start()
        view = self.view(root)
        self.assertEqual(view['state'], 'failed')
        self.assertIn('This step did not work in 3 tries: Draft the outline. The last one: '
                      'The model gave up again.', view['sentence'])
        self.assertEqual(view['problem']['action'], 'retry')
        self.assertEqual(len(self.workers.of('outline')), 3)
        self.assertIn('An earlier try at this job did not work',
                      self.workers.of('outline')[1].task)
        self.engine.act(root, 'retry')
        self.assertEqual(self.waiting(root), 'gate:outline')
        self.assertEqual(len(self.workers.of('outline')), 4)

    def test_a_draft_the_checks_refuse_is_tried_again_with_the_reason(self):
        def wrong(tools, job):
            tools.submit_outline(json.dumps({'version': 1, 'slides': []}))
        self.workers.then('outline', wrong)
        root = self.start()
        self.assertEqual(self.waiting(root), 'gate:outline')
        self.assertIn('did not pass the checks', self.workers.of('outline')[1].task)

    def test_an_agent_that_cannot_be_used_stops_at_once(self):
        self.workers.then('outline', fails('Not signed in.', reason='unavailable'))
        root = self.start()
        self.assertEqual(self.state(root), 'failed')
        self.assertIn('could not be used. Not signed in.', self.view(root)['sentence'])
        self.assertEqual(len(self.workers.of('outline')), 1)


class QuestionTests(StudioCase):
    def test_a_workers_question_waits_for_an_answer_which_goes_into_the_task(self):
        self.workers.then('outline', asks('Who presents it?'))
        root = self.start()
        view = self.view(root)
        self.assertEqual(view['state'], 'waiting')
        self.assertEqual(view['question']['text'], 'Who presents it?')
        self.engine.answer(root, view['question']['id'], 'A platform engineer.')
        self.assertEqual(self.waiting(root), 'gate:outline')
        self.assertIn('Answer: A platform engineer.', self.workers.of('outline')[-1].task)


class SharedDataTests(StudioCase):
    def test_a_data_folder_others_share_stops_the_deck_before_any_worker_with_a_sentence(self):
        from runner import agents
        import home
        shared = lambda: [home.data_root().parent]   # noqa: E731
        with mock.patch.object(agents, 'shared_temporary', shared):
            said = agents.data_shared()
            self.assertIn('a temporary folder other programs share', said)
            self.assertIn('PRESENTATION_STUDIO_DATA', said)
            self.assertNotIn('staging', said)
            self.assertEqual(self.engine.status()['problem'], said)
            root = self.start()
            record = self.record(root)
            self.assertEqual(self.state(root), 'stopped')
            self.assertEqual(record['halted']['why'], said)
            self.assertEqual(self.workers.jobs, [])
            self.assertFalse(any((entry or {}).get('failed')
                                 for entry in record['steps'].values()
                                 if isinstance(entry, dict)), 'no try was spent on it')
        self.assertIsNone(agents.data_shared())
        self.assertIsNone(self.engine.status()['problem'])


class HaltTests(StudioCase):
    def test_pause_stop_resume_and_what_is_refused(self):
        root = self.start()
        with self.assertRaises(WorkspaceError) as caught:
            self.engine.act(root, 'pause')
        self.assertIn('Only a deck that is working can be paused', str(caught.exception))
        with self.assertRaises(WorkspaceError):
            self.engine.act(root, 'retry')
        self.engine.act(root, 'stop')
        self.assertEqual(self.state(root), 'stopped')
        with self.assertRaises(WorkspaceError):
            self.engine.act(root, 'stop')
        self.engine.act(root, 'resume')
        self.assertEqual(self.waiting(root), 'gate:outline')

    def test_a_deck_that_spent_what_it_may_stops_and_asks(self):
        from dataclasses import replace
        self.settings.save(replace(self.settings.load(), deck_dollars=1.0))
        self.workers.cost = 0.75
        self.workers.then('outline', asks('One thing first?'))
        root = self.start()
        self.assertEqual(self.record(root)['limits'], {'step_seconds': 900, 'dollars': 1.0})
        self.engine.answer(root, self.view(root)['question']['id'], 'Yes.')
        self.assertEqual(self.waiting(root), 'gate:outline')
        self.decide(root, 'gate:outline')
        # The brand's sample is drawn by the runner, not an agent, so nothing is spent on it.
        self.assertEqual(self.waiting(root), 'gate:look')
        self.decide(root, 'gate:look')
        view = self.view(root)
        self.assertEqual(view['state'], 'stopped')
        self.assertIn('This deck has spent $1.50', view['sentence'])
        self.assertEqual(view['problem']['action'], 'resume')
        self.assertEqual(self.workers.of('section'), [])
        self.engine.act(root, 'resume')
        self.assertEqual(self.waiting(root), 'gate:build')

    def test_undo_takes_back_the_last_step(self):
        root = self.start()
        self.assertEqual(self.log()[-1], 'Rolling restarts: keep the outline')
        self.engine.act(root, 'undo')
        self.assertEqual(len(self.workers.of('outline')), 2)
        self.assertEqual(self.waiting(root), 'gate:outline')
        self.assertEqual(self.log()[-1], 'Rolling restarts: keep the outline')


class BrandTests(StudioCase):
    def test_a_brand_that_changed_stops_the_deck_before_the_next_step_that_uses_it(self):
        root = self.start()
        rules = self.brand.run.home / 'references' / 'brand-rules.md'
        rules.write_text(rules.read_text() + 'Round corners now.\n')
        self.decide(root, 'gate:outline')
        view = self.view(root)
        self.assertEqual(view['state'], 'stopped')
        self.assertTrue(view['sentence'].startswith('The brand changed since this deck began'))
        self.assertFalse((root / 'work' / 'look' / 'sample.png').exists())

    def without_a_brand_skill(self):
        """No brand skill on this computer, as the engine looks at it afresh."""
        self.installed, self.brand = self.brand, None
        self.engine.deck_needs(fresh=True)

    def test_without_a_brand_skill_a_deck_runs_until_it_needs_its_brand(self):
        from runner import engine
        self.without_a_brand_skill()
        root = self.start(research=True, brand='', variant='')
        self.assertIn('your brand, chosen when the brand skill is installed',
                      (root / 'intake.md').read_text())
        self.assertEqual(self.waiting(root), 'gate:research-plan')
        self.decide(root, 'gate:research-plan')
        self.assertEqual(self.waiting(root), 'gate:research')
        self.decide(root, 'gate:research')
        view = self.view(root)
        self.assertEqual((view['state'], view['sentence']), ('stopped', engine.NO_BRAND))
        self.assertEqual(view['problem']['action'], 'retry')
        self.assertEqual(self.workers.of('outline'), [], 'nothing that needs the brand ran')
        self.brand = self.installed
        self.engine.act(root, 'retry')
        self.assertEqual(self.waiting(root), 'gate:outline')
        form = json.loads((root / 'run.json').read_text())['form']
        self.assertEqual((form['brand'], form['variant']), ('example', 'light'),
                         'the first brand the brand skill lists, and its first variant')

    def test_a_brand_named_in_settings_is_the_one_a_deck_with_none_chosen_gets(self):
        from dataclasses import replace
        self.settings.save(replace(self.settings.load(), brand='example', variant='dark'))
        self.without_a_brand_skill()
        root = self.start(brand='', variant='')
        self.assertEqual(self.state(root), 'stopped')
        self.brand = self.installed
        self.engine.act(root, 'retry')
        form = json.loads((root / 'run.json').read_text())['form']
        self.assertEqual((form['brand'], form['variant']), ('example', 'dark'))

    def test_a_brand_skill_named_where_there_is_none_is_said_as_it_is(self):
        from runner import engine
        self.without_a_brand_skill()
        with mock.patch.dict('os.environ', {'BRAND_SKILL_RUNTIME': str(self.base / 'nowhere')}):
            root = self.start(brand='', variant='')
        view = self.view(root)
        self.assertNotEqual(view['sentence'], engine.NO_BRAND)
        self.assertEqual(view['sentence'], f"BRAND_SKILL_RUNTIME names {self.base / 'nowhere'}, "
                         'which does not hold a brand skill. Point it at an installed one, or '
                         'unset it.')

    def test_a_brand_the_brand_skill_does_not_offer_stops_the_deck(self):
        from runner import decks as named
        self.without_a_brand_skill()
        for form, says in (
                ({'brand': 'globex', 'variant': ''},
                 named.NOT_OFFERED.format(brand='globex', listed='example')),
                ({'brand': 'example', 'variant': 'neon'},
                 named.NO_VARIANT.format(variant='neon', brand='example',
                                         listed='light, dark'))):
            self.brand = None
            root = self.start(title=f"Restarts in {form['variant'] or form['brand']}", **form)
            self.brand = self.installed
            self.engine.act(root, 'retry')
            view = self.view(root)
            self.assertEqual((view['state'], view['sentence']), ('stopped', says))
            kept = json.loads((root / 'run.json').read_text())['form']
            self.assertEqual((kept['brand'], kept['variant']),
                             (form['brand'], form['variant'] or None), 'never switched')
            self.assertEqual(self.workers.of('outline'), [])

    def test_the_brand_chosen_for_a_deck_is_said_in_its_intake(self):
        self.without_a_brand_skill()
        root = self.start(brand='', variant='')
        self.brand = self.installed
        self.engine.act(root, 'retry')
        self.assertIn('## Brand\nexample (light)\n', (root / 'intake.md').read_text())
        self.assertNotIn('chosen when the brand skill is installed',
                         (root / 'intake.md').read_text())

    def test_without_a_brand_skill_an_existing_deck_is_still_listed_slide_by_slide(self):
        self.without_a_brand_skill()
        root = self.start(route='existing', level='polish', brand='', variant='',
                          source={'kind': 'upload', 'name': 'old.pptx'},
                          uploads={'old.pptx': ExistingTests.DECK})
        self.assertEqual(self.waiting(root), 'gate:classify')


class ResearchTests(StudioCase):
    def test_research_is_planned_approved_done_and_reported(self):
        root = self.start(research=True)
        self.assertEqual(self.waiting(root), 'gate:research-plan')
        gate = self.view(root)['gate']
        self.assertEqual([q['id'] for q in gate['questions']], ['instance-min', 'health-checks'])
        self.decide(root, 'gate:research-plan')
        self.assertEqual(self.waiting(root), 'gate:research')
        self.assertEqual(len(self.workers.of('question')), 2)
        report = self.view(root)['gate']['text']
        self.assertIn('2 of 2 questions have an answer the sources support.', report)
        self.decide(root, 'gate:research')
        self.assertEqual(self.waiting(root), 'gate:outline')
        self.assertIn('Research report', self.workers.of('outline')[0].task)

    def test_changes_at_the_research_redo_the_questions_the_note_names(self):
        root = self.start(research=True)
        self.to_gate(root, 'gate:research')
        self.engine.decide(root, 'gate:research', 'changes', 'Look again at health-checks.',
                           None)
        asked = [spec['finding'] for kind, job, spec in self.workers.jobs
                 if kind.startswith('question:')]
        self.assertEqual(asked[-1], 'health-checks')
        self.assertEqual(len(asked), 3)
        self.assertEqual(self.waiting(root), 'gate:research')

    def test_marks_at_the_research_are_kept_on_its_stop_and_a_note_alone_clears_them(self):
        root = self.start(research=True)
        self.to_gate(root, 'gate:research')
        self.engine.decide(root, 'gate:research', 'changes', 'Find a second page.',
                           {'again': {'health-checks': ''}})
        gate = self.record(root)['gates']['gate:research']
        self.assertEqual((gate['again'], gate['free']),
                         ({'health-checks': ''}, 'Find a second page.'))
        self.assertEqual(gate['note'],
                         '- Research `health-checks` again.\n\nFind a second page.')
        self.assertEqual(self.waiting(root), 'gate:research')
        self.engine.decide(root, 'gate:research', 'changes', 'Look again at health-checks.',
                           None)
        gate = self.record(root)['gates']['gate:research']
        self.assertEqual((gate['again'], gate['free'], gate['note']),
                         (None, None, 'Look again at health-checks.'))

    def test_each_finding_s_headline_is_kept_with_the_research(self):
        root = self.start(research=True)
        self.to_gate(root, 'gate:research')
        record = json.loads((root / '.harness-research' / 'research.json').read_text())
        self.assertEqual({ident: result.get('headline')
                          for ident, result in record['results'].items()},
                         {'instance-min': 'The page answers instance-min.',
                          'health-checks': 'The page answers health-checks.'})

    def test_the_research_stops_list_each_question_and_finding(self):
        root = self.start(research=True)
        plan = self.view(root)['gate']
        self.assertEqual(plan['questions'][0], {
            'id': 'instance-min', 'title': 'Instance min',
            'question': 'How many instances keep capacity during a restart?',
            'search': 'rolling restart minimum instances'})
        self.decide(root, 'gate:research-plan')
        found = self.view(root)['gate']
        first = found['items'][0]
        self.assertEqual({key: first[key] for key in ('id', 'title', 'status', 'headline',
                                                      'left_out', 'unknown')},
                         {'id': 'instance-min', 'title': 'Instance min', 'status': 'supported',
                          'headline': 'The page answers instance-min.', 'left_out': False,
                          'unknown': ''})
        self.assertEqual(set(first['sources'][0]), {'title', 'origin', 'quote'})
        self.assertEqual(first['sources'][0]['quote'], runner_support.QUOTE)
        self.assertEqual(first['sources'][0]['origin'], runner_support.URL)
        self.assertNotIn(str(root), json.dumps(found))
        # A finding kept before headlines were asked for is given its summary's first
        # sentence.
        kept = root / '.harness-research' / 'research.json'
        record = json.loads(kept.read_text())
        del record['results']['instance-min']['headline']
        record['results']['instance-min']['summary'] = (
            'What the page says about instance-min. More besides.')
        kept.write_text(json.dumps(record))
        self.assertEqual(self.view(root)['gate']['items'][0]['headline'],
                         'What the page says about instance-min.')


class PlanMarkTests(StudioCase):
    def questions(self, root):
        return [item['id'] for item in
                json.loads((root / 'research' / 'plan.json').read_text())['items']]

    def test_dropped_questions_go_with_the_approval(self):
        root = self.start(research=True)
        self.engine.decide(root, 'gate:research-plan', 'approve', None,
                           {'dropped': ['health-checks']})
        self.assertEqual(self.questions(root), ['instance-min'])
        self.assertNotIn('health-checks', (root / 'research' / 'plan.md').read_text())
        self.assertEqual(len(self.workers.of('question')), 1)
        self.assertEqual(self.waiting(root), 'gate:research')

    def test_rewording_and_adding_go_back_to_the_planner_as_one_note(self):
        root = self.start(research=True)
        self.engine.decide(root, 'gate:research-plan', 'changes', 'Keep it short.', {
            'dropped': ['health-checks'],
            'reword': {'instance-min': 'How many instances keep capacity?'},
            'add': ['What does a restart cost?']})
        task = self.workers.of('research-plan')[-1].task
        self.assertIn('- Reword `instance-min` as: How many instances keep capacity?', task)
        self.assertIn('- Add a question: What does a restart cost?', task)
        self.assertIn('Keep it short.', task)
        # The drop was applied before the planner ran again.
        self.assertIn('"id": "instance-min"', task)
        self.assertNotIn('"id": "health-checks"', task)
        gate = self.record(root)['gates']['gate:research-plan']
        self.assertEqual((gate['state'], gate['round']), ('waiting', 2))

    def test_marks_that_say_nothing_or_need_a_worker_with_approve_are_refused(self):
        root = self.start(research=True)
        for decision, extra, said in (
                ('approve', {'add': ['Why?']}, marks.AS_CHANGES),
                ('approve', {'dropped': ['instance-min', 'health-checks']}, marks.ALL_DROPPED),
                ('changes', {'dropped': ['nowhere']}, 'There is no question nowhere here.'),
                ('changes', {}, 'Say what should change.')):
            with self.subTest(extra=extra):
                with self.assertRaises(WorkspaceError) as caught:
                    self.engine.decide(root, 'gate:research-plan', decision, None, extra)
                self.assertIn(said, str(caught.exception))
        self.assertEqual(self.questions(root), ['instance-min', 'health-checks'])
        self.assertEqual(self.waiting(root), 'gate:research-plan')


def unsettled(workers, ident):
    """A research worker that leaves `ident` open and answers every other question."""
    def act(tools, job):
        if tools.job['finding'] != ident:
            return workers.question(tools, job)
        return tools.submit_finding(ident, 'insufficient', 'No page says.',
                                    headline='No page says what starts the next batch.',
                                    limits='Only one page was found.', evidence=[])
    return act


class FindingMarkTests(StudioCase):
    def researched(self):
        self.workers.then('question', unsettled(self.workers, 'health-checks'),
                          unsettled(self.workers, 'health-checks'))
        root = self.start(research=True)
        self.decide(root, 'gate:research-plan')
        self.assertEqual(self.waiting(root), 'gate:research')
        return root

    def asked(self, before):
        """The questions researched since `before` question jobs had started."""
        return [spec['finding'] for kind, job, spec in self.workers.jobs
                if kind.startswith('question:')][before:]

    def test_the_report_is_written_from_each_finding(self):
        root = self.researched()
        report = (root / 'research' / 'report.md').read_text()
        for said in ('1 of 2 questions has an answer the sources support.',
                     'Not settled (1):', '## Instance min (`instance-min`)',
                     'The page answers instance-min.', 'Not known: Only one page was found.',
                     f'"{runner_support.QUOTE}"'):
            self.assertIn(said, report)

    def test_left_out_findings_go_with_the_approval_and_leave_the_report(self):
        root = self.researched()
        self.engine.decide(root, 'gate:research', 'approve', None,
                           {'left_out': ['health-checks']})
        report = (root / 'research' / 'report.md').read_text()
        self.assertIn('1 of 1 question has an answer the sources support.', report)
        self.assertIn('Left out by you (1):\n- Health checks', report)
        self.assertNotIn('No page says', report)
        self.assertEqual(self.record(root)['research']['left_out'], ['health-checks'])
        self.assertEqual(self.waiting(root), 'gate:outline')

    def test_research_again_redoes_only_the_marked_question_with_its_line(self):
        root = self.researched()
        before = len(self.workers.of('question'))
        self.engine.decide(root, 'gate:research', 'changes', 'Be brief.', {
            'left_out': [], 'again': {'health-checks': 'Look for the platform docs.'}})
        self.assertEqual(self.asked(before), ['health-checks'])
        task = self.workers.of('question')[-1].task
        self.assertIn('researched again. What they said about it:\n\nLook for the platform '
                      'docs.', task)
        self.assertIn('Be brief.', task)
        gate = self.view(root)['gate']
        self.assertEqual((gate['name'], gate['round']), ('gate:research', 2))

    def test_a_question_added_after_the_research_keeps_the_other_findings(self):
        root = self.researched()
        before = len(self.workers.of('question'))
        self.engine.decide(root, 'gate:research', 'changes', None,
                           {'add': ['What does a restart cost?']})
        self.assertEqual(self.asked(before), ['what-does-a-restart-cost'])
        task = self.workers.of('question')[-1].task
        self.assertIn('The person added your question after reading the research.', task)
        self.assertNotIn('researched again', task)
        statuses = {item['id']: item['status'] for item in self.view(root)['gate']['items']}
        self.assertEqual(statuses, {'instance-min': 'supported', 'health-checks': 'insufficient',
                                    'what-does-a-restart-cost': 'supported'})

    def test_findings_a_changed_plan_lost_are_researched_again(self):
        from stand_ins import research as research_stand_in
        root = self.researched()
        before = len(self.workers.of('question'))
        # As when a file the research rests on changed: harness-research keeps nothing.
        with mock.patch.object(research_stand_in.StandIn, '_kept', lambda *given: {}):
            self.engine.decide(root, 'gate:research', 'changes', None,
                               {'add': ['What does a restart cost?']})
        self.assertEqual(sorted(self.asked(before)),
                         ['health-checks', 'instance-min', 'what-does-a-restart-cost'])
        self.assertNotIn('pending', self.view(root)['gate']['verdicts'].values())
        self.assertNotIn('Not researched', (root / 'research' / 'report.md').read_text())

    def test_a_left_out_question_is_not_researched_again_for_a_note(self):
        root = self.researched()
        before = len(self.workers.of('question'))
        self.engine.decide(root, 'gate:research', 'changes', 'Be brief.',
                           {'left_out': ['health-checks']})
        # The note names no question, so each question kept is researched again, but never
        # the one left out, though it is unsettled and the note the runner writes names it.
        self.assertEqual(self.asked(before), ['instance-min'])
        task = self.workers.of('question')[-1].task
        self.assertIn('Be brief.', task)
        self.assertNotIn('Leave out', task)
        self.assertEqual(self.waiting(root), 'gate:research')
        report = (root / 'research' / 'report.md').read_text()
        self.assertIn('Left out by you (1):\n- Health checks', report)
        self.assertNotIn('No page says', report)

    def test_a_question_added_to_a_full_plan_is_refused_and_nothing_is_written(self):
        root = self.researched()
        plan = json.loads((root / 'research' / 'plan.json').read_text())
        plan['items'] += [{'id': f'more-{number}', 'question': f'More {number}?',
                           'public_query': None, 'claim': None} for number in range(28)]
        (root / 'research' / 'plan.json').write_text(json.dumps(plan, indent=2))
        kept = (root / 'research' / 'plan.json').read_text()
        with self.assertRaises(WorkspaceError) as caught:
            self.engine.decide(root, 'gate:research', 'changes', None,
                               {'add': ['What does a restart cost?']})
        self.assertEqual(str(caught.exception), 'A plan holds at most 30 questions.')
        self.assertEqual((root / 'research' / 'plan.json').read_text(), kept)
        self.assertEqual(self.waiting(root), 'gate:research')

    def test_marks_that_need_a_worker_go_as_changes(self):
        root = self.researched()
        with self.assertRaises(WorkspaceError) as caught:
            self.engine.decide(root, 'gate:research', 'approve', None,
                               {'again': {'health-checks': ''}})
        self.assertEqual(str(caught.exception), marks.AS_CHANGES)


class OutlineMarkTests(StudioCase):
    def test_slides_marked_for_changes_reach_the_outline_worker(self):
        root = self.start()
        slides = self.view(root)['gate']['slides']
        moved = [slides[0], slides[2], slides[1], *slides[3:]]
        # The scripted workers draw the outline they are given, as it now stands.
        self.workers.outline_said = {**self.workers.outline_said, 'slides': moved}
        read = []

        def draw(tools, job):
            read.append(json.loads(tools.read_input('The current outline')[1]))
            self.workers.outline(tools, job)
        self.workers.then('outline', draw)
        self.engine.decide(root, 'gate:outline', 'changes', None, {
            'edited': moved, 'slides': {slides[1]['id']: 'Split it in two.'}})
        # The worker found the person's edit already kept when it began.
        self.assertEqual([[one['id'] for one in outline['slides']] for outline in read],
                         [[one['id'] for one in moved]])
        kept = json.loads((root / 'outline.json').read_text())
        self.assertEqual([one['id'] for one in kept['slides']], [one['id'] for one in moved])
        task = self.workers.of('outline')[-1].task
        self.assertIn(f"- Slide `{slides[1]['id']}`: Split it in two.", task)
        self.assertEqual(self.record(root)['gates']['gate:outline']['round'], 2)

    def test_a_slide_the_outline_does_not_have_is_refused(self):
        root = self.start()
        with self.assertRaises(WorkspaceError) as caught:
            self.engine.decide(root, 'gate:outline', 'changes', None,
                               {'slides': {'no-such-slide': 'Split it.'}})
        self.assertEqual(str(caught.exception), 'There is no slide no-such-slide here.')
        self.assertEqual(len(self.workers.of('outline')), 1)


class DocumentTests(StudioCase):
    def test_a_pasted_document_is_classified_and_a_correction_switches_the_branch(self):
        root = self.start(route='document', research=True,
                          source={'kind': 'paste', 'text': '- a\n- b\n- c\n- d\n- e\n'})
        self.assertFalse((root / 'sources' / 'incoming').exists())
        self.assertNotIn('- a', (root / 'run.json').read_text())
        gate = self.view(root)['gate']
        self.assertEqual((gate['name'], gate['verdict']), ('gate:classify', 'material'))
        self.assertEqual(gate['reason'], 'Notes to build a talk from.')
        self.engine.decide(root, 'gate:classify', 'approve', None, {'kind': 'spec'})
        self.assertEqual(self.record(root)['classified'], 'spec')
        self.assertEqual(self.waiting(root), 'gate:outline')
        self.assertEqual(self.workers.of('research-plan'), [])

    def test_an_upload_waits_under_sources_and_is_taken_in(self):
        read = []

        def reads(tools, job):
            read.append(tools.read_input('notes')[1])
            self.workers.classification(tools, job)

        self.workers.then('classification', reads)
        root = self.start(route='document', source={'kind': 'upload', 'name': 'notes.md'},
                          uploads={'notes.md': b'# Notes\n\nCapacity holds with two.\n'})
        self.assertEqual(self.waiting(root), 'gate:classify')
        self.assertIn('Capacity holds with two.', read[0])
        self.assertFalse((root / 'sources' / 'incoming').exists())
        self.assertEqual(self.view(root)['gate']['documents'][0]['name'], 'notes.md')

    def test_an_upload_that_was_not_sent_starts_nothing(self):
        before = self.log()
        with self.assertRaises(WorkspaceError) as caught:
            self.start(route='document', source={'kind': 'upload', 'name': 'notes.md'})
        self.assertIn('"notes.md" was not sent', str(caught.exception))
        self.assertEqual(self.log(), before)
        self.assertEqual(self.engine.every(), [])


class ExistingTests(StudioCase):
    DECK = b'PK\x03\x04' + b'stand-in deck'

    def test_the_inventory_shows_the_original_slides(self):
        root = self.start(route='existing', level='polish',
                          source={'kind': 'upload', 'name': 'old.pptx'},
                          uploads={'old.pptx': self.DECK})
        gate = self.view(root)['gate']
        self.assertEqual(gate['name'], 'gate:classify')
        self.assertEqual([row['number'] for row in gate['inventory']], [1, 2, 3])
        self.assertEqual(gate['pictures'][0], {'kind': 'original', 'ref': 1})
        self.assertTrue(self.engine.picture(root, 'original', 2).startswith(b'\x89PNG'))

    def test_a_google_deck_while_google_is_not_reached_starts_nothing(self):
        self.slides.run.drive = False
        before = self.log()
        with self.assertRaises(WorkspaceError) as caught:
            self.start(route='existing', level='polish',
                       source={'kind': 'google', 'link': 'abc123'})
        self.assertIn('Sign in to Google', str(caught.exception))
        self.assertEqual(self.log(), before)


class PictureTests(StudioCase):
    def test_only_pictures_the_steps_recorded_are_served(self):
        root = self.start()
        self.to_gate(root, 'gate:build')
        (root / 'secret.png').write_bytes(runner_support.png())
        for kind, ref in (('build', 99), ('build', '../secret'), ('look', 7),
                          ('original', 1)):
            with self.subTest(kind=kind, ref=ref):
                with self.assertRaises((FileNotFoundError, WorkspaceError)):
                    self.engine.picture(root, kind, ref)
        with self.assertRaises(WorkspaceError):
            self.engine.picture(root, 'secret', 1)


class LockTests(StudioCase):
    def test_a_render_in_hand_never_holds_up_a_decision_on_another_deck(self):
        slow, other = self.start(), self.start(title='Another deck')
        entered, release, real = threading.Event(), threading.Event(), build.render

        def held(root, *args, **named):
            if Path(root) == slow:
                entered.set()
                release.wait(30)
            return real(root, *args, **named)

        with mock.patch.object(build, 'render', held):
            self.decide(slow)                       # the outline; the brand waits next
            going = threading.Thread(target=self.decide, args=(slow,))
            going.start()                           # the brand; the build runs to its render
            try:
                self.assertTrue(entered.wait(60), 'the render was reached')
                clock = time.monotonic()
                self.engine.decide(other, 'gate:outline', 'changes', 'Shorter, please.')
                self.assertLess(time.monotonic() - clock, 10,
                                "a decision waited for another deck's render")
                self.assertEqual(self.waiting(other), 'gate:outline')
            finally:
                release.set()
                going.join(60)
        self.assertEqual(self.waiting(slow), 'gate:build')


class ListTests(StudioCase):
    def test_decks_are_listed_by_what_they_need(self):
        waiting = self.start()
        done = self.start(title='Second deck')
        self.to_end(done)
        listed = self.engine.decks()
        self.assertEqual([entry['id'] for entry in listed['needs']], [waiting.name])
        self.assertEqual([entry['id'] for entry in listed['finished']], [done.name])
        self.assertTrue(listed['finished'][0]['link'].startswith('https://'))
        self.assertEqual(listed['working'], [])
        self.assertEqual(listed['elsewhere'], [])


class DrivenTests(StudioCase):
    def test_a_deck_folder_reached_through_a_link_or_dots_is_not_driven(self):
        root = self.start()
        space = self.engine.space().root
        self.assertEqual(self.engine.driven(root), root)
        self.assertEqual(self.engine.every(), [root])
        outside = self.base / 'elsewhere' / 'outside'
        outside.mkdir(parents=True)
        decks.write_run(outside, {'schema': 1, 'id': 'outside'})
        linked = space / 'linked'
        linked.symlink_to(outside, target_is_directory=True)
        self.assertIsNone(self.engine.driven(linked))
        self.assertIsNone(self.engine.driven(space / '..' / space.name / root.name))
        self.assertIsNone(self.engine.driven(space / 'linked' / '..' / root.name))
        self.assertEqual(self.engine.every(), [root])


if __name__ == '__main__':
    unittest.main()
