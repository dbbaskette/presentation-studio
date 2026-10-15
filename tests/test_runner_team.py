"""The team: one driver for each deck, the computer's own notifications, publishing inside
the workspace as numbered revision tags, and bringing a deck's folder in.

Two people are two data folders and two git identities on one computer, joined to one bare
repository. Nothing here needs the engine.

The engine-driven team tests (starting a deck takes it and shares the claim first; a teammate
reads a deck and cannot change it; a second claim the repository refuses is dropped; taking
over and handing over; a deck started while the repository is away; the status list and its
turns; adopting a teammate's decks on a timer and when the runner starts; a slow remote never
holding up a decision; publishing, deleting and bringing a deck in) are in test_engine_team.py.
Deferred to Task 12 (they drive the page): notifications on the page, the page's publish and
published routes, and bringing a deck in through the page.
"""
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import helpers
import runner_support  # noqa: F401

import home
import hub
from runner import gitstate, team
from test_runner_gitstate import WorkspaceCase, asked, git

STAMP = r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$'
DECK = 'quarterly-review'


class TeamCase(WorkspaceCase):
    def started(self, ws, ident: str = DECK, text: str = '{}\n') -> Path:
        """A deck folder in the workspace, kept in a commit."""
        self.write(ws, f'{ident}/run.json', text)
        gitstate.commit(ws, f'Start {ident}')
        return ws.deck(ident)

    def tags(self) -> list[str]:
        return git(self.remote, 'tag', '--list').splitlines()


class DriverTests(TeamCase):
    def test_this_computers_identifier_is_made_once_and_says_nothing_of_anyone(self):
        first = team.computer()
        self.assertRegex(first, r'^[0-9a-f]{16}$')
        self.assertEqual(team.computer(), first)
        kept = json.loads((home.data_root() / 'computer.json').read_text())
        self.assertEqual(kept, {'schema': 1, 'id': first})
        self.be('blake')
        self.assertNotEqual(team.computer(), first)

    def test_a_workspace_on_one_computer_has_no_drivers(self):
        space = gitstate.local(self.base / 'mine')
        self.assertIsNone(team.claim(space))
        record = {'driver': {'name': 'Someone', 'computer': 'f' * 16, 'since': home.now()}}
        self.assertIsNone(team.driver(space, record))
        self.assertTrue(team.ours(space, record))
        self.assertTrue(team.ours(space, {}))
        self.assertTrue(team.ours(None, None))
        self.assertIsNone(team.elsewhere(space, record))

    def test_in_a_shared_workspace_a_deck_is_ours_only_while_its_record_names_this_computer(self):
        alex = self.join()
        claim = team.claim(alex)
        self.assertEqual((claim['name'], claim['computer']), ('Alex', team.computer()))
        self.assertRegex(claim['since'], STAMP)
        record = {'driver': claim}
        self.assertTrue(team.ours(alex, record))
        self.assertIsNone(team.elsewhere(alex, record))
        self.assertEqual(team.driver(alex, record),
                         {'name': 'Alex', 'here': True, 'since': claim['since']})

        self.be('blake')
        blake = self.join()
        self.assertFalse(team.ours(blake, record))
        self.assertEqual(team.driver(blake, record)['here'], False)
        said = team.elsewhere(blake, record)
        self.assertIn('Alex has been running this deck from another computer since', said)
        self.assertIn(claim['since'][:10], said)

    def test_a_deck_that_names_nobody_is_nobodys_until_it_is_taken(self):
        self.be('blake')
        blake = self.join()
        for record in ({}, None, {'driver': 'Alex'}, {'driver': {'name': 'Alex'}}):
            self.assertFalse(team.ours(blake, record), record)
            self.assertIsNone(team.driver(blake, record))
            self.assertEqual(team.elsewhere(blake, record), team.NOBODY)
        self.assertNotRegex(team.NOBODY, 'artifact|stale|lineage')

    def test_who_took_a_deck_from_this_computer_is_read_back(self):
        root = self.base / 'somewhere' / DECK
        self.assertIsNone(team.taken(root))
        team.keep('taken', {str(root): {'name': 'Blake', 'at': '2026-10-14T10:00:00Z',
                                        'kept': 'refs/presentation-studio/kept/x'}})
        self.assertEqual(team.taken(root), {'by': 'Blake', 'at': '2026-10-14T10:00:00Z',
                                            'kept': 'refs/presentation-studio/kept/x'})
        team.keep('taken', {str(root): {'at': 'x'}})
        self.assertIsNone(team.taken(root))


class NotifierTests(unittest.TestCase):
    def notifier(self, system: str = 'Linux', have=(), environ=None, code: int = 0):
        ran = []

        def run(command, **named):
            ran.append(command)
            return subprocess.CompletedProcess(command, code)

        return team.Notifier(which=lambda name: f'/usr/bin/{name}' if name in have else None,
                             run=run, system=lambda: system, environ=environ or {}), ran

    def test_macos_uses_the_systems_own_command_and_hands_the_words_over_as_arguments(self):
        notifier, ran = self.notifier('Darwin', have=('osascript',))
        self.assertEqual(notifier.can(), (True, None))
        title = 'Review" & do shell script "true'
        self.assertTrue(notifier.send(title))
        self.assertEqual(ran[0][0], 'osascript')
        self.assertEqual(ran[0][-3:], ['--', 'Presentation Studio',
                                       f'"{title}" needs a decision.'])
        self.assertNotIn(title, ' '.join(ran[0][:-1]), 'never written into the script')

    def test_elsewhere_it_uses_what_is_present(self):
        notifier, ran = self.notifier(have=('notify-send',))
        self.assertTrue(notifier.send('Quarterly review'))
        self.assertEqual(ran, [['notify-send', '--', 'Presentation Studio',
                                '"Quarterly review" needs a decision.']])

    def test_the_command_can_be_replaced(self):
        notifier, ran = self.notifier('Darwin', have=('osascript',),
                                      environ={team.REPLACED: 'my-notify --quiet'})
        self.assertTrue(notifier.send('Quarterly review'))
        self.assertEqual(ran, [['my-notify', '--quiet', 'Presentation Studio',
                                '"Quarterly review" needs a decision.']])
        self.assertEqual(team.REPLACED, 'PRESENTATION_STUDIO_NOTIFY')

    def test_a_computer_with_no_way_to_notify_says_so(self):
        notifier, ran = self.notifier()
        self.assertEqual(notifier.can(), (False, team.NO_WAY))
        self.assertFalse(notifier.send('Quarterly review'))
        self.assertEqual(ran, [])
        self.assertNotRegex(team.NO_WAY, 'artifact|stale|lineage')

    def test_a_command_that_fails_is_not_counted_as_told(self):
        self.assertFalse(self.notifier(have=('notify-send',), code=1)[0].send('A title'))


class PublishTests(TeamCase):
    def tag(self, name: str) -> str:
        return git(self.remote, 'rev-parse', f'refs/tags/{name}')

    def test_the_published_list_asks_git_twice_however_many_there_are(self):
        ws = self.join()
        for ident in (DECK, 'health-review', 'launch-plan'):
            self.started(ws, ident)
            team.publish(ws, ident, ident.title(), True, 'Alex')
        self.write(ws, 'health-review/slides.md', 'Changed.\n')
        gitstate.commit(ws, 'Change one')
        with asked() as ran:
            listed = team.published(ws)
        self.assertEqual([name for name, _ in ran], ['for-each-ref', 'cat-file'])
        self.assertEqual({entry['id']: entry['current'] for entry in listed},
                         {DECK: True, 'health-review': False, 'launch-plan': True})

    def test_revisions_are_numbered_pushed_and_never_moved(self):
        alex = self.join()
        root = self.started(alex)
        gitstate.sync(alex)
        first = team.publish(alex, DECK, 'Quarterly review', True, 'Alex')
        self.assertEqual(first, {'revision': 1, 'tag': 'presentations/quarterly-review/r1',
                                 'shared': True, 'why': None})
        name = first['tag']
        self.assertEqual(self.tags(), [name])
        kept, stood = self.tag(name), git(self.remote, 'rev-parse', 'refs/heads/main')
        self.assertNotEqual(kept, stood, 'an annotated tag, not a bare pointer')
        self.assertEqual(git(self.remote, 'rev-parse', f'{name}^{{commit}}'), stood)

        self.be('blake')
        blake = self.join()
        self.assertTrue(team.fetch_tags(blake))
        listed = team.published(blake)
        self.assertEqual(listed, [{'path': str(blake.deck(DECK)), 'id': DECK,
                                   'title': 'Quarterly review', 'revision': 1,
                                   'at': listed[0]['at'], 'by': 'Alex', 'ready': True,
                                   'current': True}])
        self.assertRegex(listed[0]['at'], STAMP)
        self.assertEqual(team.publish(blake, DECK, 'Quarterly review', True, 'Blake')['revision'],
                         2)
        self.assertEqual(self.tags(), [name, 'presentations/quarterly-review/r2'])
        self.assertEqual(self.tag(name), kept, 'the first revision is where it was')

        self.be('alex')
        team.fetch_tags(alex)
        listed = team.published(alex)
        self.assertEqual([(entry['revision'], entry['by']) for entry in listed], [(2, 'Blake')])
        self.assertEqual(team.revisions(alex, DECK), 2)
        self.assertEqual(team.revisions(alex, 'other-deck'), 0)
        self.assertTrue(root.is_dir())

    def test_two_people_publishing_one_number_at_once_get_consecutive_revisions(self):
        alex = self.join()
        self.started(alex)
        team.send_tags(alex)
        gitstate.sync(alex)
        self.be('blake')
        blake = self.join()
        self.be('alex')
        real, raced = team.send_tags, []

        def blake_first(space, only=None):
            if only and not raced:
                raced.append(True)
                self.be('blake')
                made = team.publish(blake, DECK, 'Quarterly review', True, 'Blake')
                self.be('alex')
                self.assertEqual(made['revision'], 1)
            return real(space, only)

        with mock.patch.object(team, 'send_tags', blake_first):
            mine = team.publish(alex, DECK, 'Quarterly review', True, 'Alex')
        self.assertEqual((mine['revision'], mine['shared']), (2, True))
        self.assertEqual(len(self.tags()), 2)
        by = {entry['revision']: entry['by'] for entry in team._tags(alex)}
        self.assertEqual(by, {1: 'Blake', 2: 'Alex'})

    def test_a_deck_that_is_not_ready_is_published_and_says_so(self):
        ws = self.join()
        self.started(ws)
        made = team.publish(ws, DECK, 'Quarterly review', False, 'Alex')
        self.assertEqual((made['revision'], made['shared']), (1, True))
        listed = team.published(ws)
        self.assertEqual((listed[0]['ready'], listed[0]['current']), (False, True))
        self.write(ws, f'{DECK}/slides.md', 'More.\n')
        gitstate.commit(ws, 'More')
        self.assertFalse(team.published(ws)[0]['current'], 'the deck changed since')

    def test_a_revision_made_while_the_repository_is_away_goes_with_the_next_send(self):
        ws = self.join()
        self.started(ws)
        gitstate.sync(ws)
        self.remote.rename(self.base / 'moved-away.git')
        made = team.publish(ws, DECK, 'Quarterly review', True, 'Alex')
        self.assertEqual((made['revision'], made['shared']), (1, False))
        self.assertTrue(made['why'])
        (self.base / 'moved-away.git').rename(self.remote)
        self.assertEqual(self.tags(), [])
        self.assertIsNone(team.send_tags(ws))
        self.assertEqual(self.tags(), ['presentations/quarterly-review/r1'])

    def test_a_workspace_on_one_computer_keeps_its_revisions_here(self):
        ws = gitstate.local(self.base / 'mine')
        self.started(ws)
        made = team.publish(ws, DECK, 'Quarterly review', True, 'Alex')
        self.assertEqual((made['revision'], made['shared']), (1, False))
        self.assertEqual(git(ws.repo, 'tag', '--list'), 'presentations/quarterly-review/r1')
        self.assertEqual(team.send_tags(ws), 'this workspace has no shared repository')
        self.assertFalse(team.fetch_tags(ws))
        self.assertEqual(team.publish(ws, DECK, 'Quarterly review', True, 'Alex')['revision'], 2)
        self.assertEqual([entry['revision'] for entry in team.published(ws)], [2])

    def test_tags_that_are_not_ours_are_not_listed(self):
        ws = self.join()
        self.started(ws)
        git(ws.repo, 'tag', 'presentations/quarterly-review/v9')
        git(ws.repo, 'tag', '-m', 'x', 'presentations/quarterly-review/r0', 'HEAD')
        git(ws.repo, 'tag', '-m', 'not json', 'presentations/quarterly-review/r5', 'HEAD')
        self.assertEqual(team.published(ws), [])

    def test_no_command_here_ever_forces_a_push_or_moves_a_tag(self):
        source = Path(team.__file__).read_text().split('"""', 2)[2]
        for never in ('--force', "'-f'", '+refs', '--mirror', "'reset'"):
            self.assertNotIn(never, source, never)


class BringTests(TeamCase):
    def folder(self) -> Path:
        top = self.base / 'elsewhere' / DECK
        (top / 'slides').mkdir(parents=True)
        (top / 'run.json').write_text('{}\n')
        (top / 'slides' / 'one.md').write_text('One.\n')
        (top / 'sources').mkdir()
        (top / 'sources' / 'notes.txt').write_text('Kept beside the deck.\n')
        return top

    def tree(self, folder: Path) -> dict:
        return {path.relative_to(folder).as_posix(): path.read_bytes()
                for path in sorted(folder.rglob('*')) if path.is_file()}

    def test_a_plain_folder_is_copied_whole_and_the_original_is_not_touched(self):
        top = self.folder()
        before = self.tree(top)
        self.assertIsNone(team.unacceptable(top))
        target = self.base / 'copy'
        team.copy_in(top, target)
        self.assertEqual(self.tree(target), before)
        self.assertEqual(self.tree(top), before)
        self.assertEqual([path.name for path in self.base.glob('.bringing-*')], [])

    def test_what_is_never_copied_is_left_out(self):
        top = self.folder()
        (top / '.git').mkdir()
        (top / '.git' / 'HEAD').write_text('ref: refs/heads/main\n')
        (top / 'run.lock').write_text('1\n')
        (top / '.presentation-studio').mkdir()
        (top / '.presentation-studio' / 'lock').write_text('1\n')
        (top / '.presentation-studio' / 'state.json').write_text('{}\n')
        (top / '.harness-slides' / 'guidance').mkdir(parents=True)
        (top / '.harness-slides' / 'guidance' / 'a.md').write_text('x\n')
        self.assertIsNone(team.unacceptable(top))
        target = self.base / 'copy'
        team.copy_in(top, target)
        self.assertEqual(sorted(self.tree(target)), [
            '.presentation-studio/state.json', 'run.json', 'slides/one.md', 'sources/notes.txt'])

    def test_what_cannot_be_brought_in_is_refused_in_a_sentence(self):
        top = self.folder()
        (top / 'linked.md').symlink_to(top / 'run.json')
        self.assertIn('linked.md is a symbolic link, which a workspace does not take',
                      team.unacceptable(top))
        (top / 'linked.md').unlink()
        (top / 'nested' / '.git').mkdir(parents=True)
        self.assertIn('nested holds a repository of its own', team.unacceptable(top))
        (top / 'nested' / '.git').rmdir()
        with mock.patch.object(team, 'LARGEST', 10):
            self.assertIn('is larger than', team.unacceptable(top))
        self.assertIsNone(team.unacceptable(top / 'nested'))


if __name__ == '__main__':
    unittest.main()
