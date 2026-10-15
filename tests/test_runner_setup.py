"""Setting this computer up through the page: the workspace, the defaults a new deck starts
with, the check that changes nothing, and the studios config every *-studio on this computer
shares. STUDIOS_CONFIG names a file in the test's own folder (helpers.py sees to it for every
test), so the real one is never read or written."""
import json
import os
from pathlib import Path
from unittest import mock

import helpers
from runner_support import FORM, StudioCase

import studios_config
from runner import gitstate, settings, setup
from test_runner_page import Asking

THEIRS = """{
    "schema": 1,
    "team": {"repository": "REMOTE", "branch": "main", "reviewers": ["sam", "kim"]},
    "person": { "name": "Dan Baskette" },
    "assistant": { "agent": "codex", "model": "gpt-6-sol", "effort": "high" },
    "brand": { "brand": "example", "variant": "dark" },
    "output": "pptx",
    "share": "asked",
    "blog": {"tone": "plain", "drafts": 3, "nested": {"a": [1, 2, {"b": null}]}}
}
"""
DEFAULTS = {'agent': {'default': 'claude', 'model': None, 'effort': None},
            'person': {'name': None}, 'output': 'google',
            'limits': {'step_seconds': 900, 'deck_dollars': 20.0, 'parallel': 2}}


class FirstTimeCase(Asking, StudioCase):
    """A computer where nothing is set up yet."""

    def set_up(self):
        return None

    def setUp(self):
        super().setUp()
        self.ready_page()
        settings.path().unlink()
        patch = mock.patch.dict(os.environ, {'STUDIOS_CONFIG': str(self.base / 'config' /
                                                                   'studios-config.json')})
        patch.start()
        self.addCleanup(patch.stop)
        self.config = Path(os.environ['STUDIOS_CONFIG'])

    def bare(self, name: str = 'team-repo.git') -> Path:
        remote = self.base / name
        remote.mkdir()
        self.git('init', '--quiet', '--bare', repo=remote)
        self.git('symbolic-ref', 'HEAD', 'refs/heads/main', repo=remote)
        return remote

    def someone_else(self, remote: Path, **named) -> None:
        """A teammate sets the workspace up in the shared repository and shares it."""
        with mock.patch.dict(os.environ, {'PRESENTATION_STUDIO_DATA': str(self.base /
                                                                          'theirs')}):
            self.assertTrue(gitstate.sync(gitstate.join(str(remote), **named))['shared'])

    def defaults(self, said: dict) -> dict:
        return {key: said[key] for key in DEFAULTS}

    def write_config(self, text: str) -> None:
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(text, encoding='utf-8')


class SetUpTests(FirstTimeCase):
    def test_nothing_is_set_up_at_first(self):
        said = self.get('setup')
        self.assertEqual((said['configured'], said['workspace'], said['suggested']),
                         (False, None, None))
        self.assertEqual(self.defaults(said), DEFAULTS)
        self.assertEqual(said['brand']['default'], {'brand': 'tanzu', 'variant': 'light'})
        self.assertEqual((said['shared'], said['shared_problem']), ({}, None))
        self.assertEqual((said['notify'], said['updates'], said['upkeep']),
                         ({'on': False, 'can': True, 'problem': None}, {'look': True}, None))
        self.assertEqual(said['previews'], {'how': None, 'drive': True, 'local': True})
        self.assertIn('No workspace is set up on this computer yet',
                      self.post('decks', {'form': FORM}, 409)['error'])
        self.assertIn('No workspace is set up', self.post('share', {}, 409)['error'])
        self.assertEqual(self.get('decks'), {'needs': [], 'working': [], 'finished': [],
                                             'elsewhere': []})

    def test_a_folder_on_this_computer_becomes_the_workspace(self):
        folder = self.base / 'my-decks'
        made = self.post('setup', {
            'path': str(folder), 'branch': 'main', 'name': 'my-work',
            'share_when': 'when-asked', 'agent': 'codex', 'model': 'a-model',
            'effort': 'ultra', 'person': 'Alex Example', 'brand': 'example',
            'variant': 'dark', 'output': 'pptx', 'previews': 'local',
            'limits': {'step_seconds': 600, 'deck_dollars': 7.5, 'parallel': 3}})
        self.assertEqual(made['workspace'], {
            'name': 'my-work', 'repository': None, 'path': str(folder),
            'folder': 'presentations', 'branch': 'main', 'share_when': 'when-asked',
            'shared': False, 'notice': None})
        self.assertEqual(self.defaults(made), {
            'agent': {'default': 'codex', 'model': 'a-model', 'effort': 'ultra'},
            'person': {'name': 'Alex Example'}, 'output': 'pptx',
            'limits': {'step_seconds': 600, 'deck_dollars': 7.5, 'parallel': 3}})
        self.assertEqual((made['brand']['default'], made['previews']['how']),
                         ({'brand': 'example', 'variant': 'dark'}, 'local'))
        self.assertEqual(self.get('setup'), made)
        marker = json.loads((folder / 'presentations' / 'hub.json').read_text())
        self.assertEqual((marker['tool'], marker['name']), ('presentation-studio', 'my-work'))
        path = self.post('decks', {'form': {**FORM, 'agent': 'codex'}})['path']
        self.assertEqual(Path(path), folder / 'presentations' / 'rolling-restarts')
        self.assertEqual(self.get('run', path=path)['agent'], 'codex')

    def test_a_repository_becomes_the_workspace_in_a_copy_of_the_runners_own(self):
        remote = self.bare()
        made = self.post('setup', {'repository': str(remote), 'share_when': 'each-decision'})
        space = made['workspace']
        self.assertEqual((space['name'], space['repository'], space['folder'],
                          space['branch'], space['share_when'], space['shared']),
                         ('team-repo', str(remote), 'presentations', 'main', 'each-decision',
                          False))
        self.assertEqual(Path(space['path']), gitstate.clones() / 'team-repo')
        self.assertEqual(self.post('share', {}), {'shared': True, 'notice': None})
        self.assertEqual(self.get('setup')['workspace']['shared'], True)

    def test_a_second_person_is_asked_for_nothing_the_repository_already_says(self):
        remote = self.bare()
        self.someone_else(remote, folder='decks', name='field-team')
        space = self.post('setup', {'repository': str(remote)})['workspace']
        self.assertEqual((space['name'], space['folder'], space['branch']),
                         ('field-team', 'decks', 'main'))

    def test_the_settings_can_change_without_moving_the_workspace(self):
        folder = self.base / 'my-decks'
        self.post('setup', {'path': str(folder)})
        changed = self.post('setup', {'share_when': 'when-asked', 'model': 'a-model',
                                      'effort': 'max', 'limits': {'parallel': 4}})
        self.assertEqual((changed['workspace']['path'], changed['workspace']['share_when'],
                          changed['agent'], changed['limits']['parallel']),
                         (str(folder), 'when-asked',
                          {'default': 'claude', 'model': 'a-model', 'effort': 'max'}, 4))
        self.assertEqual(self.post('setup', {'limits': {'parallel': 3}})['agent'],
                         {'default': 'claude', 'model': 'a-model', 'effort': 'max'})
        self.assertEqual(self.post('setup', {'agent': 'codex'})['agent'],
                         {'default': 'codex', 'model': None, 'effort': None})

    def test_set_up_that_makes_no_sense_changes_nothing(self):
        folder = str(self.base / 'my-decks')
        for sent, said in (
                ({}, "Give the repository's address, or a folder on this computer."),
                ({'path': folder, 'repository': 'https://example.com/team/team-repo.git'},
                 "Give the repository's address or a folder on this computer, not both."),
                ({'path': 'my-decks'}, "Give the folder's whole path"),
                ({'path': folder, 'folder': '../outside'}, 'A workspace folder is letters'),
                ({'path': folder, 'branch': 'not a branch'}, 'cannot be the name of a branch'),
                ({'path': folder, 'name': 'two words'}, 'A workspace name is letters'),
                ({'path': folder, 'share_when': 'never'}, 'Sharing is one of: each-decision, '
                 'when-asked.'),
                ({'path': folder, 'agent': 'another'}, 'The agent is one of: claude, codex.'),
                ({'path': folder, 'model': 'two words'}, 'The model is the short name'),
                ({'path': folder, 'effort': 'warp'}, 'The reasoning level is one of'),
                ({'path': folder, 'person': 7}, 'Give your name as text'),
                ({'path': folder, 'brand': '../x'}, 'The brand is a short name'),
                ({'path': folder, 'variant': ''}, 'The variant is a short name'),
                ({'path': folder, 'output': 'keynote'}, 'A deck is made as one of: google, '
                 'pptx.'),
                ({'path': folder, 'previews': 'paper'}, 'Previews are rendered one of'),
                ({'path': folder, 'limits': [900]}, 'Give the limits as'),
                ({'path': folder, 'limits': {'step_seconds': 5}},
                 'The time for one step, in seconds, is a whole number from 60 to 7200.'),
                ({'path': folder, 'limits': {'deck_dollars': 0}},
                 'What a deck may spend, in dollars, is a number from 0.01 to 1000.'),
                ({'path': folder, 'limits': {'parallel': 2.5}},
                 'How many decks run at once is a whole number from 1 to 8.'),
                ({'path': folder, 'for_all_studios': 'yes'}, 'Say whether this is for all '
                 'your studios'),
                ({'path': 7}, 'Give the path as text.')):
            with self.subTest(sent=sent):
                self.assertIn(said, self.post('setup', sent, 400)['error'])
        self.assertFalse(Path(folder).exists())
        self.assertEqual((self.get('setup')['configured'], settings.path().exists()),
                         (False, False))

    def test_set_up_needs_a_git_identity_and_says_how_to_give_one(self):
        helpers.gitconfig(self.base / 'nobody.gitconfig', '[user]\n\tuseConfigOnly = true\n')
        with mock.patch.dict(os.environ, {'GIT_CONFIG_GLOBAL':
                                          str(self.base / 'nobody.gitconfig')}):
            said = self.post('setup', {'path': str(self.base / 'my-decks')}, 409)
            self.assertIn('git does not know who you are', said['error'])
            checked = self.post('setup/check', {'path': str(self.base / 'my-decks')})
        self.assertEqual(self.get('setup')['configured'], False)
        who = checked['checks'][2]
        self.assertEqual((checked['ok'], who['what'], who['ok']),
                         (False, 'git knows who you are', False))

    def test_setting_up_picks_up_the_decks_already_in_the_workspace(self):
        remote = self.bare()
        with mock.patch.dict(os.environ, {'PRESENTATION_STUDIO_DATA': str(self.base /
                                                                          'theirs')}):
            settings.save(settings.Settings(previews='local'))
            theirs = self.make()
            gitstate.join(str(remote))
            theirs.start(FORM)
            self.assertTrue(theirs.share()['shared'])
        self.post('setup', {'repository': str(remote)})
        listed = self.get('decks')
        self.assertEqual([(item['title'], item['mine'], item['driver']['name'])
                          for item in listed['elsewhere']],
                         [('Rolling restarts', False, 'Alex')])


class CheckTests(FirstTimeCase):
    """`POST /api/setup/check` looks, and changes nothing."""

    def check(self, expect: int = 200, **sent) -> dict:
        before = self.on_disk()
        found = self.post('setup/check', sent, expect)
        self.assertEqual(self.on_disk(), before, 'a check changes nothing')
        self.assertEqual(self.get('setup')['configured'], False)
        return found

    def test_a_new_folder_on_this_computer_can_be_used(self):
        found = self.check(path=str(self.base / 'my-decks'))
        self.assertEqual((found['ok'], found['found']), (True, {
            'name': 'my-decks', 'folder': 'presentations', 'branch': 'main',
            'existing': False}))
        self.assertEqual([item['what'] for item in found['checks']], [
            'The folder can be reached', 'The folder can be written to',
            'git knows who you are', 'The folder for decks can be used'])

    def test_a_repository_a_teammate_set_up_says_what_it_holds(self):
        remote = self.bare()
        self.someone_else(remote, folder='decks', name='field-team')
        found = self.check(repository=str(remote))
        self.assertEqual((found['ok'], found['found']), (True, {
            'name': 'field-team', 'folder': 'decks', 'branch': 'main', 'existing': True}))

    def test_a_folder_that_belongs_to_another_tool_is_not_taken(self):
        folder = self.base / 'theirs'
        (folder / 'presentations').mkdir(parents=True)
        (folder / 'presentations' / 'hub.json').write_text(json.dumps(
            {'schema': 1, 'tool': 'training-studio', 'name': 'x', 'folder': 'presentations',
             'branch': 'main'}))
        found = self.check(path=str(folder))
        self.assertFalse(found['ok'])
        self.assertFalse(found['checks'][3]['ok'])

    def test_an_address_that_carries_a_secret_is_never_used(self):
        found = self.check(repository='https://dan:hunter2@example.com/team/repo.git')
        self.assertFalse(found['ok'])
        self.assertIn('carries a password or token', found['checks'][0]['fix'])

    def test_a_repository_that_cannot_be_reached_says_how_to_put_it_right(self):
        found = self.check(repository=str(self.base / 'nowhere.git'))
        self.assertFalse(found['checks'][0]['ok'])
        self.assertIn('could not be reached', found['checks'][0]['fix'])

    def test_a_check_that_makes_no_sense_is_refused(self):
        self.assertIn('not both', self.check(400, path=str(self.base / 'a'),
                                             repository=str(self.base / 'b.git'))['error'])
        self.assertIn('Give the repository as text.',
                      self.check(400, repository=['a', 'list'])['error'])


class SharedConfigTests(FirstTimeCase):
    """The studios config: read to pre-fill set-up, written only for all studios."""

    def test_with_no_file_the_defaults_are_as_they_were(self):
        self.assertFalse(self.config.exists())
        said = self.get('setup')
        self.assertEqual((said['shared'], said['shared_problem'], said['suggested']),
                         ({}, None, None))
        self.assertEqual(self.defaults(said), DEFAULTS)
        self.post('setup', {'path': str(self.base / 'my-decks')})
        self.assertFalse(self.config.exists(), 'nothing is written unless asked')

    def test_set_up_is_pre_filled_from_the_file_until_this_computer_saves_its_own(self):
        remote = self.bare()
        self.write_config(THEIRS.replace('REMOTE', str(remote)))
        said = self.get('setup')
        self.assertEqual(said['shared'], {
            'team': {'repository': str(remote), 'branch': 'main'},
            'person': {'name': 'Dan Baskette'},
            'assistant': {'agent': 'codex', 'model': 'gpt-6-sol', 'effort': 'high'},
            'brand': {'brand': 'example', 'variant': 'dark'}, 'output': 'pptx',
            'share': 'asked'})
        self.assertEqual(said['suggested'], {'repository': str(remote), 'branch': 'main',
                                             'share_when': 'when-asked'})
        self.assertEqual(self.defaults(said), {
            'agent': {'default': 'codex', 'model': 'gpt-6-sol', 'effort': 'high'},
            'person': {'name': 'Dan Baskette'}, 'output': 'pptx',
            'limits': DEFAULTS['limits']})
        self.assertEqual(said['brand']['default'], {'brand': 'example', 'variant': 'dark'})
        made = self.post('setup', {'repository': str(remote)})
        self.assertEqual((made['agent']['default'], made['output'], made['suggested']),
                         ('codex', 'pptx', None), 'what was pre-filled is what is saved')
        self.assertEqual(settings.load().name, 'Dan Baskette')
        self.write_config(THEIRS.replace('REMOTE', str(remote)).replace('"pptx"', '"google"'))
        self.assertEqual(self.get('setup')['output'], 'pptx', "this computer's own wins")

    def test_a_value_that_could_not_be_used_here_is_left_out(self):
        self.write_config(json.dumps({
            'schema': 1,
            'team': {'repository': 'https://dan:hunter2@example.com/team.git',
                     'branch': '../x'},
            'assistant': {'agent': 'gemini', 'model': 'opus'},
            'brand': {'brand': '../../etc', 'variant': 'light'},
            'output': 'keynote', 'share': 'sometimes', 'person': {'name': 7}}))
        said = self.get('setup')
        self.assertEqual(said['shared'], {'brand': {'variant': 'light'}})
        self.assertEqual(said['agent']['default'], 'claude')

    def test_an_unreadable_file_never_blocks_set_up_and_says_why(self):
        self.write_config('{"schema": 1, "team": ')
        said = self.get('setup')
        self.assertEqual(said['shared'], {})
        self.assertIn('could not be read (it is not valid JSON), so Presentation Studio is '
                      'using its own settings.', said['shared_problem'])
        self.assertEqual(self.defaults(said), DEFAULTS)
        made = self.post('setup', {'path': str(self.base / 'my-decks'), 'agent': 'codex',
                                   'for_all_studios': True})
        self.assertTrue(made['configured'])
        self.assertEqual(made['for_all_studios']['written'], [])
        self.assertIn('could not be read', made['for_all_studios']['problem'])
        self.assertEqual(self.config.read_text(), '{"schema": 1, "team": ',
                         'an unreadable file is never written over')
        self.assertEqual(settings.load().agent, 'codex', 'the set-up is saved all the same')

    def test_for_all_studios_writes_only_what_changed_and_keeps_every_other_byte(self):
        remote = self.bare()
        text = THEIRS.replace('REMOTE', str(remote))
        self.write_config(text)
        self.post('setup', {'repository': str(remote)})
        self.assertEqual(self.config.read_text(), text, 'saving without asking writes nothing')
        made = self.post('setup', {'model': 'gpt-6-luna', 'variant': 'light',
                                   'for_all_studios': True})
        self.assertEqual(made['for_all_studios'], {
            'written': ['assistant.model', 'brand.variant'], 'problem': None})
        self.assertEqual(self.config.read_text(), text
                         .replace('"model": "gpt-6-sol"', '"model": "gpt-6-luna"')
                         .replace('"variant": "dark"', '"variant": "light"'))
        again = self.post('setup', {'limits': {'parallel': 3}, 'for_all_studios': True})
        self.assertEqual(again['for_all_studios'], {'written': [], 'problem': None})

    def test_a_first_save_for_all_studios_makes_the_file(self):
        remote = self.bare()
        made = self.post('setup', {'repository': str(remote), 'person': 'Alex Example',
                                   'for_all_studios': True})
        self.assertIsNone(made['for_all_studios']['problem'])
        kept = json.loads(self.config.read_text())
        self.assertEqual(kept, {
            'schema': 1, 'team': {'repository': str(remote), 'branch': 'main'},
            'share': 'decision',
            'assistant': {'agent': 'claude'},   # null is as good as leaving it out
            'person': {'name': 'Alex Example'},
            'brand': {'brand': 'tanzu', 'variant': 'light'}, 'output': 'google'})
        self.assertEqual(studios_config.read(), (kept, None))


class SharedValuesTests(StudioCase):
    """What `setup.shared` and `setup.base` make of the file, without the page."""

    def test_the_tests_never_read_the_real_file(self):
        self.assertIn('STUDIOS_CONFIG', os.environ)
        self.assertNotEqual(studios_config.path(), studios_config.PATH)
        self.assertNotIn(Path.home() / '.config', studios_config.path().parents)

    def test_saved_settings_are_used_as_they_are(self):
        self.assertTrue(settings.path().is_file())
        self.assertEqual(setup.base(), settings.load())

