"""The engine with a team: one driver for each deck, staying in step, turns, notifications,
publishing, deleting and bringing a deck in. Ported from Training Studio's engine-driven
team tests (the page-driven ones are in test_runner_page.TeamPageTests).

Two people are two data folders and two git identities on this computer, against one bare
repository. Nothing starts an agent, shows a real notification or touches the network.
"""
import json
import threading
import time
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest import mock

from runner_support import FORM, StudioCase, TeamCase

import home
import hub
from runner import gitstate, settings, team
from runner import engine as engines
from workspace import WorkspaceError

STAMP = r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$'
STARTED = 'Rolling restarts: set up its run, driven by Alex'


class Team(TeamCase):
    def started(self, person=None, **changes) -> Path:
        person = person or self.alex
        with self.be(person):
            return Path(person.engine.start({**FORM, **changes})['path'])

    def seen(self, person, root: Path) -> dict:
        with self.be(person):
            return person.engine.view(self.theirs(person, root))

    def fetch(self, person) -> dict:
        return self.as_(person, person.engine.fetch)

    def drive(self, person, root: Path, action: str = 'take') -> dict:
        return self.as_(person, person.engine.drive, self.theirs(person, root), action)

    def approve(self, person, root: Path, gate: str | None = None) -> dict:
        with self.be(person):
            return self.decide(self.theirs(person, root), gate, engine=person.engine)

    def head(self, person) -> str:
        return self.git('rev-parse', 'HEAD', repo=person.space.repo)

    def kept(self, person) -> list[str]:
        return self.git('for-each-ref', '--format=%(refname)', 'refs/presentation-studio/kept/',
                        repo=person.space.repo).splitlines()


class DriverTests(Team):
    def test_starting_a_deck_takes_it_and_shares_the_claim_before_any_work(self):
        sent = []
        self.workers.then('outline', lambda tools, job: (
            sent.extend(self.shared()), self.workers.outline(tools, job))[1])
        root = self.started()
        self.assertEqual(sent[0], STARTED, 'the claim was shared before the first worker ran')
        driver = self.record(root)['driver']
        self.assertEqual((driver['name'], driver['computer']), ('Alex', team.computer()))
        self.assertRegex(driver['since'], STAMP)
        view = self.seen(self.alex, root)
        self.assertEqual((view['mine'], view['driver']),
                         (True, {'name': 'Alex', 'here': True, 'since': driver['since']}))
        self.assertEqual((view['taken'], view['notice'], view['queue']), (None, None, None))

    def test_a_teammate_reads_a_deck_and_cannot_change_it(self):
        root = self.started()
        self.assertEqual(self.fetch(self.blake)['reached'], True)
        theirs = self.theirs(self.blake, root)
        view = self.seen(self.blake, root)
        self.assertEqual((view['mine'], view['driver']['name'], view['driver']['here']),
                         (False, 'Alex', False))
        self.assertIn('Alex is running this deck from another computer', view['sentence'])
        self.assertTrue(view['timeline'], 'its steps can be read')
        engine = self.blake.engine
        with self.be(self.blake):
            for change in (lambda: engine.hold(theirs),
                           lambda: engine.act(theirs, 'stop'),
                           lambda: engine.answer(theirs, 'abc', 'An answer'),
                           lambda: engine.publish(theirs),
                           lambda: engine.decide(theirs, 'gate:outline', 'approve'),
                           lambda: engine.drive(theirs, 'hand-over')):
                with self.assertRaisesRegex(engines.Elsewhere, 'Alex has been running this '
                                            'deck from another computer since'):
                    change()
            self.assertEqual(engine.decks()['elsewhere'][0]['needs'], False)
            engine.resume()
        self.assertEqual(self.head(self.blake), self.git('rev-parse', 'main', repo=self.remote),
                         'nothing was written to it there')
        self.assertEqual(len(self.workers.jobs), 1, 'and nothing was worked on there')

    def test_a_second_claim_the_repository_refuses_is_dropped_and_says_who_has_it(self):
        root = self.started()
        self.drive(self.alex, root, 'hand-over')
        self.fetch(self.blake)
        theirs, real, raced = self.theirs(self.blake, root), gitstate.commit, []

        def alex_gets_there_first(space, message, paths=None):
            made = real(space, message, paths)
            if not raced and 'takes this deck' in message:
                raced.append(True)
                with self.be(self.alex):
                    self.alex.engine.drive(root, 'take')
            return made

        before = self.head(self.blake)
        with mock.patch.object(gitstate, 'commit', alex_gets_there_first), \
                self.be(self.blake), \
                self.assertRaisesRegex(engines.Elsewhere, 'Alex took this deck first, on '
                                       '.* so your claim was dropped'):
            self.blake.engine.drive(theirs, 'take')
        self.assertEqual(raced, [True])
        view = self.seen(self.blake, root)
        self.assertEqual((view['mine'], view['driver']['name'], view['taken']),
                         (False, 'Alex', None))
        self.assertEqual(self.head(self.blake), self.git('rev-parse', 'main', repo=self.remote))
        self.assertNotEqual(self.head(self.blake), before)
        self.assertEqual(self.kept(self.blake), [])
        self.assertNotIn('Blake takes this deck', '\n'.join(self.shared()))
        self.assertEqual(self.seen(self.alex, root)['mine'], True)

    def test_a_deck_someone_took_since_the_page_looked_is_not_taken_over_unasked(self):
        root = self.started()
        self.drive(self.alex, root, 'hand-over')
        self.fetch(self.blake)
        self.drive(self.alex, root)
        with self.assertRaisesRegex(engines.Elsewhere, 'Alex took this deck on .* after this '
                                    'page last looked'):
            self.drive(self.blake, root)
        self.assertEqual(self.seen(self.blake, root)['driver']['name'], 'Alex')
        self.assertEqual(self.drive(self.blake, root)['mine'], True, 'now they mean it')

    def test_taking_over_stops_the_other_runner_which_keeps_what_it_had(self):
        with self.be(self.alex):
            gitstate.share_when('asked')
        root = self.started()
        self.approve(self.alex, root, 'gate:outline')
        unshared = self.head(self.alex)
        self.assertEqual(self.shared()[0], STARTED)
        self.fetch(self.blake)
        taken = self.drive(self.blake, root)
        self.assertEqual((taken['mine'], taken['driver']['name'], taken['driver']['here']),
                         (True, 'Blake', True))
        self.assertEqual(self.shared()[0], 'Rolling restarts: Blake takes this deck over from '
                         'Alex')
        self.assertEqual(self.seen(self.blake, root)['gate']['name'], 'gate:outline',
                         "Blake's runner carried on from what was shared")

        self.assertEqual(self.fetch(self.alex)['reached'], True)
        view = self.seen(self.alex, root)
        self.assertEqual((view['mine'], view['driver']['name']), (False, 'Blake'))
        self.assertEqual(view['taken']['by'], 'Blake')
        self.assertEqual(self.kept(self.alex), [view['taken']['kept']])
        self.assertEqual(self.git('rev-parse', view['taken']['kept'], repo=self.alex.space.repo),
                         unshared, 'what this computer had made is kept')
        self.assertIn('Blake took this deck over on', view['notice'])
        self.assertIn('What this computer had made and not yet shared is kept on this '
                      'computer, and can be brought back.', view['notice'])
        self.assertNotIn('refs/', view['notice'])
        with self.assertRaisesRegex(engines.Elsewhere, 'Blake has been running'):
            self.approve(self.alex, root, 'gate:outline')
        jobs = len(self.workers.jobs)
        with self.be(self.alex):
            self.alex.engine.resume()
            self.assertEqual(self.alex.engine.share()['shared'], True)
        self.assertEqual(len(self.workers.jobs), jobs, 'it works on it no more')
        self.assertEqual([said for said in self.shared() if said.startswith('Rolling')][0],
                         'Rolling restarts: Blake takes this deck over from Alex',
                         "nothing of Alex's was put on top of Blake's")
        self.approve(self.blake, root, 'gate:outline')
        self.fetch(self.alex)
        self.assertEqual(self.drive(self.alex, root)['taken'], None, 'taking it back clears it')

    def test_a_teammates_deck_says_what_was_last_shared_and_never_what_it_does_now(self):
        with self.be(self.alex):
            gitstate.share_when('asked')
        root = self.started()   # the claim is shared; the outline drafted since is not
        self.fetch(self.blake)
        view = self.seen(self.blake, root)
        self.assertEqual((view['state'], view['mine'], view['workers'], view['queue']),
                         ('elsewhere', False, [], None))
        last = view['last_shared']
        self.assertEqual((sorted(last), last['by']), (['at', 'by', 'says'], 'Alex'))
        self.assertRegex(last['at'], STAMP)
        self.assertEqual(last['says'], 'Then, the next step was to get your starting '
                         'material.')
        self.assertEqual(view['sentence'], (
            'Alex is running this deck from another computer. What is here is what was '
            f"last shared, on {team.day(last['at'])}. {last['says']} It may have moved on "
            'since.'))
        self.assertEqual(self.seen(self.alex, root)['last_shared'], None)
        self.as_(self.alex, self.engine.share)
        self.fetch(self.blake)
        view = self.seen(self.blake, root)
        self.assertEqual((view['state'], view['last_shared']['says']),
                         ('elsewhere', 'Then, the outline was waiting for a decision.'))

    def test_handing_over_leaves_a_deck_for_anyone_to_take(self):
        root = self.started()
        handed = self.drive(self.alex, root, 'hand-over')
        self.assertEqual((handed['mine'], handed['driver'], handed['state'], handed['sentence']),
                         (False, None, 'stopped', team.NOBODY))
        self.assertEqual(self.shared()[0], 'Rolling restarts: Alex hands this deck over')
        with self.assertRaisesRegex(engines.Elsewhere, 'Nobody is running this deck'):
            self.approve(self.alex, root, 'gate:outline')
        self.fetch(self.blake)
        self.assertEqual(self.seen(self.blake, root)['driver'], None)
        self.assertEqual(self.drive(self.blake, root)['mine'], True)
        self.assertEqual(self.shared()[0], 'Rolling restarts: Blake takes this deck')
        self.approve(self.blake, root, 'gate:outline')
        self.assertEqual(self.seen(self.blake, root)['gate']['name'], 'gate:look')

    def test_a_delivered_deck_has_no_driver_and_is_taken_to_change_it(self):
        root = self.started()
        with self.be(self.alex):
            self.to_end(root)
        view = self.seen(self.alex, root)
        self.assertEqual((view['state'], view['driver'], view['mine']),
                         ('finished', None, False))
        self.fetch(self.blake)
        theirs = self.seen(self.blake, root)
        self.assertEqual((theirs['state'], theirs['driver']), ('finished', None))
        self.assertTrue(theirs['deliver']['url'])
        with self.be(self.blake), self.assertRaisesRegex(engines.Elsewhere, 'Nobody is running'):
            self.blake.engine.decide(self.theirs(self.blake, root), 'gate:build', 'changes',
                                     'Shorter.')
        self.drive(self.blake, root)
        with self.be(self.blake):
            self.blake.engine.decide(self.theirs(self.blake, root), 'gate:build', 'changes',
                                     'Shorter.')
        self.assertEqual(self.seen(self.blake, root)['gate']['name'], 'gate:build')

    def test_a_deck_taken_at_its_look_draws_the_looks_again_here(self):
        root = self.started()
        self.approve(self.alex, root, 'gate:outline')
        self.drive(self.alex, root, 'hand-over')
        self.fetch(self.blake)
        theirs = self.theirs(self.blake, root)
        self.assertFalse((theirs / 'work').exists(), 'what it made on the way stays there')
        self.drive(self.blake, root)
        view = self.seen(self.blake, root)
        self.assertEqual(view['gate']['name'], 'gate:look')
        self.assertTrue(view['gate']['options'])
        with self.be(self.blake):
            self.blake.engine.picture(theirs, 'look', 1)
        self.assertIn('Rolling restarts: carry on here: design the look, preview the look '
                      'again', self.git('log', '--format=%s', repo=self.blake.space.repo))

    def test_an_upload_kept_on_the_computer_that_started_the_deck_stops_it_elsewhere(self):
        with self.be(self.alex):
            root = Path(self.engine.start(
                {**FORM, 'route': 'document',
                 'source': {'kind': 'upload', 'name': 'notes.md'}},
                {'notes.md': b'# Notes\n\nCapacity holds with two.\n'})['path'])
        self.drive(self.alex, root, 'hand-over')
        self.fetch(self.blake)
        view = self.drive(self.blake, root)
        self.assertEqual((view['mine'], view['state']), (True, 'stopped'))
        self.assertIn('was uploaded on the computer that started it, and is never shared',
                      view['sentence'])
        self.assertEqual(view['problem']['action'], None)

    def google_deck(self) -> Path:
        """A deck from Google Slides whose inventory Alex approved before handing it over.
        Its extract fails with these workers, which leaves it stopped on a problem."""
        with self.be(self.alex):
            root = Path(self.engine.start(
                {**FORM, 'route': 'existing', 'level': 'polish',
                 'source': {'kind': 'google', 'link': 'abc123'}})['path'])
            self.engine.decide(root, 'gate:classify', 'approve')
        self.drive(self.alex, root, 'hand-over')
        self.fetch(self.blake)
        return root

    def test_a_deck_taken_after_its_inventory_draws_the_original_slides_again(self):
        root = self.google_deck()
        theirs = self.theirs(self.blake, root)
        self.assertFalse((theirs / 'work').exists())
        self.drive(self.blake, root)
        with self.be(self.blake):
            self.blake.engine.act(theirs, 'retry')
            picture = self.blake.engine.picture(theirs, 'original', 1)
        self.assertTrue(picture.startswith(b'\x89PNG'))
        self.assertEqual(self.record(theirs)['gates']['gate:classify']['state'], 'approved',
                         'the inventory was not put to the person again')

    def test_a_google_deck_that_changed_since_it_was_read_stops_the_deck_taken_over(self):
        from stand_ins import slides as stand_in
        root = self.google_deck()
        real = stand_in.invented
        with mock.patch.object(stand_in, 'invented', lambda title: real(f'{title}, edited')):
            self.drive(self.blake, root)
            view = self.as_(self.blake, self.blake.engine.act, self.theirs(self.blake, root),
                            'retry')
        self.assertEqual((view['state'], view['problem']['action']), ('stopped', None))
        self.assertIn('The deck in Google Slides changed since this deck was read from it',
                      view['sentence'])
        self.assertIn('Start a new deck from it', view['sentence'])

    def test_a_deck_cannot_be_taken_while_the_repository_cannot_be_reached(self):
        root = self.started()
        self.fetch(self.blake)
        before = self.head(self.blake)
        self.remote.rename(self.base / 'moved-away.git')
        with self.assertRaisesRegex(WorkspaceError, 'could not be reached, so this deck '
                                    'cannot be taken now'):
            self.drive(self.blake, root)
        self.assertEqual((self.head(self.blake), self.seen(self.blake, root)['mine']),
                         (before, False))

    def test_a_deck_started_while_the_repository_is_away_is_still_started(self):
        self.remote.rename(self.base / 'moved-away.git')
        root = self.started()
        self.assertEqual(self.seen(self.alex, root)['mine'], True)
        self.assertEqual(self.seen(self.alex, root)['gate']['name'], 'gate:outline')
        self.assertIn('could not be reached', self.as_(self.alex, self.engine.shared)['notice'])

    def test_a_rule_broken_by_hand_is_reported_and_put_right_by_taking_over(self):
        root = self.started()
        clone = self.base / 'by-hand'
        self.git('clone', '--quiet', str(self.remote), str(clone), repo=self.base)
        record = clone / 'presentations' / root.name / 'run.json'
        record.write_text(json.dumps(json.loads(record.read_text())))
        self.git('commit', '--quiet', '-am', 'Edited by hand', repo=clone)
        self.git('push', '--quiet', 'origin', 'HEAD:main', repo=clone)
        found = self.as_(self.alex, self.engine.share)
        self.assertEqual(found['shared'], False)
        self.assertIn('"Rolling restarts" was changed on this computer and on another at the '
                      'same time', found['notice'])
        self.assertEqual(self.seen(self.alex, root)['notice'], found['notice'])
        mine = self.head(self.alex)
        taken = self.drive(self.alex, root)
        self.assertEqual(taken['mine'], True)
        self.assertIn('carries on from the shared version', taken['notice'])
        self.assertEqual([self.git('rev-parse', ref, repo=self.alex.space.repo)
                          for ref in self.kept(self.alex)], [mine])
        self.assertEqual(self.as_(self.alex, self.engine.share)['shared'], True)
        self.assertEqual(self.seen(self.alex, root)['notice'], None)

    def test_undo_takes_back_only_what_was_not_shared(self):
        root = self.started()   # the claim is shared; the work up to the gate is not yet
        before = self.head(self.alex)
        with self.be(self.alex):
            self.engine.act(root, 'undo')
            self.assertEqual(self.git('rev-parse', 'HEAD~1', repo=self.alex.space.repo),
                             self.git('rev-parse', f'{before}~1', repo=self.alex.space.repo),
                             'the last step was taken back, and done again')
            self.assertEqual(self.engine.share()['shared'], True)
            with self.assertRaisesRegex(WorkspaceError, 'cannot be undone'):
                self.engine.act(root, 'undo')


class SameTitleTests(Team):
    """Review Focus 4: two computers start a deck with the same title at the same moment."""

    def test_the_second_start_is_refused_naming_the_teammate_and_nothing_is_merged(self):
        first = self.started()
        with self.assertRaisesRegex(WorkspaceError, 'Alex started a deck in '
                                    'presentations/rolling-restarts at the same moment'):
            self.started(self.blake)
        self.assertEqual(self.head(self.blake), self.git('rev-parse', 'main', repo=self.remote))
        theirs = self.theirs(self.blake, first)
        self.assertEqual(json.loads((theirs / 'run.json').read_text())['driver']['name'], 'Alex')
        shared = json.loads(self.git('show', f'main:presentations/{first.name}/run.json',
                                     repo=self.remote))
        self.assertEqual(shared['driver']['name'], 'Alex')
        self.assertEqual(self.git('log', '--format=%an', 'main', '--',
                                  f'presentations/{first.name}', repo=self.remote).split(),
                         ['Alex', 'Alex'], 'only one person ever wrote that folder')
        again = self.started(self.blake)    # Blake's copy now knows the name is taken
        self.assertEqual(again.name, 'rolling-restarts-2')
        self.as_(self.blake, self.blake.engine.share)
        names = self.git('ls-tree', '--name-only', 'main', 'presentations/', repo=self.remote)
        self.assertIn('presentations/rolling-restarts', names.split())
        self.assertIn('presentations/rolling-restarts-2', names.split())

    def test_two_decks_started_while_away_are_never_one_folder(self):
        moved = self.base / 'moved-away.git'
        self.remote.rename(moved)
        mine = self.started()
        theirs = self.started(self.blake)
        self.assertEqual(mine.name, theirs.name)
        moved.rename(self.remote)
        self.assertTrue(self.as_(self.alex, self.alex.engine.share)['shared'])
        self.assertTrue(self.as_(self.blake, self.blake.engine.share)['shared'])
        names = self.git('ls-tree', '--name-only', 'main', 'presentations/',
                         repo=self.remote).split()
        self.assertIn('presentations/rolling-restarts', names)
        self.assertIn('presentations/rolling-restarts-2', names)
        for name, driver in (('rolling-restarts', 'Alex'), ('rolling-restarts-2', 'Blake')):
            shared = json.loads(self.git('show', f'main:presentations/{name}/run.json',
                                         repo=self.remote))
            self.assertEqual((shared['id'], shared['driver']['name']), (name, driver))
            self.assertEqual(set(self.git('log', '--format=%an', 'main', '--',
                                          f'presentations/{name}', repo=self.remote).split()),
                             {driver}, 'only one person ever wrote each folder')
        kept = self.blake.space.deck('rolling-restarts-2')
        view = self.seen(self.blake, kept)
        self.assertEqual((view['mine'], view['gate']['name']), (True, 'gate:outline'))
        self.assertIn('Alex started a deck in presentations/rolling-restarts while this '
                      'computer could not reach the shared repository', view['notice'])
        self.assertIn('moved to presentations/rolling-restarts-2', view['notice'])
        self.assertEqual(self.seen(self.blake, theirs)['driver']['name'], 'Alex')
        self.assertEqual(self.kept(self.blake), [], 'nothing was set aside: it was all moved')


class NoDriverTests(StudioCase):
    def test_nothing_changes_where_there_is_no_shared_repository(self):
        root = self.start()
        view = self.view(root)
        self.assertEqual((view['mine'], view['driver'], view['taken']), (True, None, None))
        self.assertIsNone(self.record(root)['driver'])
        for action in engines.DRIVING:
            with self.assertRaisesRegex(WorkspaceError, 'is a folder on this computer'):
                self.engine.drive(root, action)
        self.to_end(root)
        self.assertEqual(self.view(root)['mine'], True)
        self.assertEqual(self.engine.fetch(), {'reached': None, 'received': 0, 'notice': None})


class InStepTests(Team):
    def test_a_teammates_decks_are_adopted_with_their_driver(self):
        root = self.started()
        with self.be(self.alex):
            self.to_end(root)
        self.started(title='Health checks')
        self.assertEqual(self.as_(self.blake, self.blake.engine.decks)['elsewhere'], [])
        self.assertEqual(self.fetch(self.blake)['reached'], True)
        listed = self.as_(self.blake, self.blake.engine.decks)
        self.assertEqual([entry['title'] for entry in listed['finished']], ['Rolling restarts'])
        self.assertIsNone(listed['finished'][0]['driver'])
        theirs = listed['elsewhere'][0]
        self.assertEqual((theirs['title'], theirs['state'], theirs['driver']['name'],
                          theirs['mine'], theirs['needs']),
                         ('Health checks', 'elsewhere', 'Alex', False, False))
        self.assertIn(theirs['path'], [entry['path'] for entry in
                                       self.as_(self.blake, home.decks)])
        index = (self.blake.space.root / 'README.md').read_text()
        self.assertIn('Rolling restarts', index, 'the list of decks was shared on its own')

    def test_fetching_on_a_timer_never_touches_a_deck_this_computer_drives(self):
        mine = self.started()
        theirs = self.started(self.blake, title='Health checks')
        head = self.head(self.alex)
        with self.be(self.alex):
            self.engine.serving(every=0.05, tick=0.05)
            deadline = time.monotonic() + 30
            while not self.theirs(self.alex, theirs).exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.engine.close()
        self.assertTrue((self.theirs(self.alex, theirs) / 'intake.md').is_file())
        self.assertEqual(self.git('diff', '--name-only', head, 'HEAD', '--', str(mine),
                                  repo=self.alex.space.repo), '')
        self.assertEqual(self.seen(self.alex, mine)['mine'], True)

    def test_the_runner_fetches_when_it_starts(self):
        theirs = self.started(self.blake)
        with self.be(self.alex):
            self.engine.resume()
        self.assertEqual(self.seen(self.alex, theirs)['driver']['name'], 'Blake')


class TurnTests(StudioCase):
    BACKGROUND = True

    def until(self, check, seconds: float = 30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            found = check()
            if found:
                return found
            time.sleep(0.02)
        self.fail('It did not happen in time.')

    def test_turns_are_taken_in_the_order_they_were_asked_for(self):
        slots, order, waiting = engines._Slots(lambda: 1), [], []
        self.assertTrue(slots.take(lambda: False, 'first'))

        def wait(name: str) -> None:
            slots.take(lambda: False, name)
            order.append(name)
            slots.give_back()

        for name in ('second', 'third', 'fourth'):
            waiting.append(threading.Thread(target=wait, args=(name,), daemon=True))
            waiting[-1].start()
            self.until(lambda: slots.ahead(name) is not None)
        slots.give_back()
        for thread in waiting:
            thread.join(30)
        self.assertEqual(order, ['second', 'third', 'fourth'])

    def test_a_deck_that_waits_says_how_many_are_ahead_and_status_shows_every_run(self):
        settings.save(replace(settings.load(), parallel=1))
        entered, go = threading.Event(), threading.Event()
        self.addCleanup(go.set)

        def held(tools, job):
            self.workers.outline(tools, job)
            entered.set()
            go.wait(60)

        self.workers.then('outline', held)
        first = self.start()
        self.assertTrue(entered.wait(30))
        second = self.start(title='Health checks')
        self.until(lambda: self.view(second)['queue'])
        third = self.start(title='Blue green')
        self.until(lambda: self.view(third)['queue'])
        self.assertEqual((self.view(first)['queue'], self.view(second)['queue'],
                          self.view(third)['queue']), (None, {'ahead': 0}, {'ahead': 1}))
        self.assertEqual((self.view(second)['sentence'], self.view(third)['sentence']),
                         ('Waiting for its turn. It is next.',
                          'Waiting for its turn. 1 deck is ahead of it.'))
        found = self.engine.standing()
        self.assertEqual((found['limit'], found['elsewhere'], found['background']),
                         (1, [], None))
        runs = {run['id']: run for run in found['runs']}
        self.assertEqual({ident: run['queue'] for ident, run in runs.items()},
                         {'rolling-restarts': None, 'health-checks': {'ahead': 0},
                          'blue-green': {'ahead': 1}})
        self.assertIn('Drafting the outline', runs['rolling-restarts']['sentence'])
        go.set()
        self.until(lambda: all(self.state(root) == 'waiting' for root in (first, second, third)))
        order = [job.folder.name.split('--')[0] for _, job, _ in self.workers.jobs]
        self.assertEqual(order, ['rolling-restarts', 'health-checks', 'blue-green'])


class StatusTests(Team):
    def test_status_keeps_this_computers_runs_apart_from_those_driven_elsewhere(self):
        mine = self.started()
        theirs = self.started(self.blake, title='Health checks')
        self.fetch(self.alex)
        found = self.as_(self.alex, self.engine.standing)
        self.assertEqual([(run['id'], run['driver']['here'], run['needs'], run['state'])
                          for run in found['runs']],
                         [('rolling-restarts', True, True, 'waiting')])
        self.assertEqual(found['runs'][0]['path'], str(mine))
        self.assertEqual([(run['id'], run['state'], run['driver']['name'])
                          for run in found['elsewhere']],
                         [('health-checks', 'elsewhere', 'Blake')])
        self.assertEqual(found['elsewhere'][0]['path'], str(self.theirs(self.alex, theirs)))


class NotifyTests(StudioCase):
    def on(self) -> None:
        settings.save(replace(settings.load(), notify=True))

    def test_nothing_is_told_until_it_is_turned_on(self):
        self.start()
        self.assertEqual((settings.load().notify, self.engine.tell(), self.notifier.sent),
                         (False, [], []))

    def test_each_thing_that_needs_a_decision_is_told_once(self):
        self.on()
        root = self.start()
        self.assertEqual(self.engine.tell(), ['Rolling restarts'])
        self.assertEqual(self.engine.tell(), [])
        self.assertEqual(self.make().tell(), [], 'nor again after the runner is started again')
        self.decide(root, 'gate:outline')
        self.assertEqual(self.engine.tell(), ['Rolling restarts'], 'the next gate is new')
        self.engine.act(root, 'stop')
        self.assertEqual(self.engine.tell(), [], 'a deck its person stopped needs nothing')
        self.assertEqual(self.notifier.sent, ['Rolling restarts'] * 2)

    def test_nothing_is_told_while_a_page_is_open(self):
        self.on()
        self.start()
        self.engine.seen()
        self.assertEqual((self.engine.page_open(), self.engine.tell()), (True, []))
        with mock.patch.object(engines, 'PAGE_OPEN', 0):
            self.assertEqual((self.engine.page_open(), self.engine.tell()),
                             (False, ['Rolling restarts']))


class TeamNotifyTests(Team):
    def test_a_teammates_deck_is_never_told_here(self):
        with self.be(self.blake):
            settings.save(replace(settings.load(), notify=True))
        self.started()
        self.fetch(self.blake)
        self.assertEqual(self.as_(self.blake, self.blake.engine.tell), [])


class SlowRemoteTests(Team):
    @contextmanager
    def held_up(self, name: str):
        reached, go, real = threading.Event(), threading.Event(), hub.run

        def slow(repo, *args, **named):
            if hub.subcommand(args) == name and not go.is_set():
                reached.set()
                go.wait(30)
            return real(repo, *args, **named)

        with mock.patch.object(hub, 'run', slow):
            try:
                yield reached, go
            finally:
                go.set()

    def test_a_decision_is_not_held_up_by_a_slow_push_or_fetch(self):
        root = self.started()
        with self.be(self.alex):
            gitstate.share_when('asked')    # so the decision itself sends nothing
        for name, sharing, gate in (('push', self.engine.share, 'gate:outline'),
                                    ('fetch', self.engine.fetch, 'gate:look')):
            with self.subTest(name), self.be(self.alex), self.held_up(name) as (reached, go):
                behind = threading.Thread(target=sharing, daemon=True)
                behind.start()
                self.assertTrue(reached.wait(30), f'the {name} was never asked for')
                before, made = self.head(self.alex), []
                deciding = threading.Thread(target=lambda: made.append(
                    self.decide(root, gate)), daemon=True)
                deciding.start()
                deciding.join(30)
                self.assertFalse(deciding.is_alive(), f'the decision waited for the {name}')
                self.assertTrue(behind.is_alive(), f'the {name} is still held up')
                self.assertNotEqual(self.head(self.alex), before, 'and it was committed')
                go.set()
                behind.join(30)
        self.assertEqual(self.as_(self.alex, self.engine.share)['shared'], True)

    def test_nothing_is_changed_until_the_first_look_after_starting(self):
        root = self.started()
        with self.be(self.alex):
            self.engine.close()
            self.alex.engine = self.make(background=True)
        with self.be(self.alex), self.held_up('fetch') as (reached, go):
            self.alex.engine.resume(wait=False)
            self.assertTrue(reached.wait(30), 'the first look was never asked for')
            for change in (lambda: self.alex.engine.decide(root, 'gate:outline', 'approve'),
                           lambda: self.alex.engine.act(root, 'pause')):
                with self.assertRaises(WorkspaceError) as caught:
                    change()
                self.assertEqual(str(caught.exception), engines.CHECKING)
            go.set()
            for thread in threading.enumerate():
                if thread.name == 'resuming':
                    thread.join(30)


class PublishTests(Team):
    def test_revisions_are_numbered_pushed_and_say_whether_it_was_delivered(self):
        root = self.started()
        first = self.as_(self.alex, self.engine.publish, root)
        self.assertEqual((first['revision'], first['ready'], first['shared']), (1, False, True))
        self.assertIn('before this deck was delivered', first['notice'])
        with self.be(self.alex):
            self.to_end(root)
        second = self.as_(self.alex, self.engine.publish, root)
        self.assertEqual((second['revision'], second['ready']), (2, True))
        self.assertEqual(sorted(self.tags()), ['presentations/rolling-restarts/r1',
                                               'presentations/rolling-restarts/r2'])
        self.assertEqual([entry['revision'] for entry in
                          self.as_(self.alex, self.engine.published)], [2])

    def test_a_deck_someone_else_drives_is_not_published_from_here(self):
        root = self.started()
        self.fetch(self.blake)
        with self.assertRaises(engines.Elsewhere):
            self.as_(self.blake, self.blake.engine.publish, self.theirs(self.blake, root))
        self.assertEqual(self.tags(), [])


class DeleteTests(Team):
    def test_a_deck_is_deleted_and_the_deletion_shared(self):
        root = self.started()
        leaving = self.as_(self.alex, self.engine.leaving, root)
        self.assertEqual((leaving['may'], leaving['share'], leaving['revisions']),
                         (True, 'decision', 0))
        with self.assertRaisesRegex(WorkspaceError, 'not the title of this deck'):
            self.as_(self.alex, self.engine.delete, root, 'Something else')
        gone = self.as_(self.alex, self.engine.delete, root, 'Rolling restarts')
        self.assertEqual((gone['deleted'], gone['shared']), (True, True))
        self.assertFalse(root.exists())
        self.assertIn('Rolling restarts: Alex deletes this deck', self.shared()[0])
        self.fetch(self.blake)
        self.assertFalse(self.theirs(self.blake, root).exists())

    def test_a_teammate_cannot_delete_a_deck_they_do_not_drive(self):
        root = self.started()
        self.fetch(self.blake)
        leaving = self.as_(self.blake, self.blake.engine.leaving, self.theirs(self.blake, root))
        self.assertEqual(leaving['may'], False)
        self.assertIn('Alex runs this deck from another computer', leaving['why'])
        with self.assertRaises(engines.Elsewhere):
            self.as_(self.blake, self.blake.engine.delete, self.theirs(self.blake, root),
                     'Rolling restarts')


class BringTests(Team):
    def test_a_deck_brought_in_under_a_name_a_teammate_has_is_refused_then_numbered(self):
        root = self.started()
        outside = self.base / 'outside' / 'restarts'
        import shutil
        shutil.copytree(root, outside, ignore=shutil.ignore_patterns('work', 'sources'))
        with self.assertRaisesRegex(WorkspaceError, 'Alex already has a deck in '
                                    'presentations/rolling-restarts, which this computer had '
                                    'not seen yet, so this one was not brought in'):
            self.as_(self.blake, self.blake.engine.bring, outside)
        made = self.as_(self.blake, self.blake.engine.bring, outside)
        self.assertEqual(made['id'], 'rolling-restarts-2')

    def test_a_deck_is_copied_in_taken_and_carried_on_at_its_waiting_gate(self):
        root = self.started()
        outside = self.base / 'outside' / 'restarts'
        self.git('clone', '--quiet', str(self.alex.space.repo), str(self.base / 'copy'),
                 repo=self.base)
        (self.base / 'outside').mkdir()
        import shutil
        shutil.copytree(root, outside, ignore=shutil.ignore_patterns('work', 'sources'))
        self.fetch(self.blake)
        made = self.as_(self.blake, self.blake.engine.bring, outside)
        self.assertEqual(made['id'], 'rolling-restarts-2')
        brought = Path(made['path'])
        record = json.loads((brought / 'run.json').read_text())
        self.assertEqual((record['id'], record['driver']['name']), ('rolling-restarts-2',
                                                                    'Blake'))
        self.assertEqual(self.seen(self.blake, brought)['gate']['name'], 'gate:outline')
        self.assertTrue((outside / 'run.json').is_file(), 'the folder it came from is only read')
        with self.assertRaisesRegex(WorkspaceError, 'cannot be read'):
            (self.base / 'empty').mkdir()
            self.as_(self.blake, self.blake.engine.bring, self.base / 'empty')


if __name__ == '__main__':
    unittest.main()
