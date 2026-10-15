"""The runner's settings: the values every studio shares, read from and saved to the studios
config, and the rest kept in Presentation Studio's own runner.json. Every test has a data
folder and a studios config of its own."""
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  sets PRESENTATION_STUDIO_DATA
import studios_config
from runner import settings
from workspace import WorkspaceError

THEIRS = """{
  "schema": 1,
  "person": {"name": "Dan Baskette"},
  "assistant": {"agent": "codex", "model": "gpt-6-sol", "effort": "high"},
  "brand": {"repository": "https://github.com/acme/brand.git", "release": "v1.4.0",
            "brand": "acme", "variant": "dark"},
  "output": "pptx",
  "blog": {"tone": "plain"}
}
"""


class SettingsCase(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        self.config = self.base / 'config' / 'studios-config.json'
        patch = mock.patch.dict(os.environ, {'PRESENTATION_STUDIO_DATA': str(self.base / 'data'),
                                             'STUDIOS_CONFIG': str(self.config)})
        patch.start()
        self.addCleanup(patch.stop)

    def write_config(self, text: str) -> None:
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(text, encoding='utf-8')

    def own(self) -> dict:
        return json.loads(settings.path().read_text())


class SettingsTests(SettingsCase):
    def test_save_then_load_keeps_agent_model_and_effort(self):
        settings.save(settings.Settings(agent='claude', model='opus', effort='high'))
        loaded = settings.load()
        self.assertEqual((loaded.agent, loaded.model, loaded.effort),
                         ('claude', 'opus', 'high'))

    def test_the_models_list_is_read(self):
        self.assertIn('opus', {m['name'] for m in settings.claude_models()['models']})

    def test_an_unknown_effort_is_refused(self):
        with self.assertRaises(WorkspaceError):
            settings.save(replace(settings.Settings(), effort='extreme'))

    def test_an_unknown_agent_is_refused(self):
        with self.assertRaises(WorkspaceError):
            settings.check_agent('gemini')

    def test_no_brand_is_named_until_the_person_chooses_one(self):
        chosen = settings.Settings()
        self.assertEqual((chosen.brand, chosen.variant), (None, None))
        self.assertEqual((chosen.brand_repository, chosen.brand_release), (None, None))
        kept = settings.save(replace(settings.Settings(), brand='', variant=''))
        self.assertEqual((kept.brand, kept.variant), (None, None))
        with self.assertRaises(WorkspaceError) as refused:
            settings.save(replace(settings.Settings(), brand='not a word!'))
        self.assertEqual(str(refused.exception),
                         'The brand is a short name, as your brand skill lists it.')

    def test_the_brand_skills_repository_is_kept_only_in_a_shape_git_takes(self):
        kept = settings.save(replace(settings.load(),
                                     brand_repository=' git@github.com:acme/brand.git ',
                                     brand_release='v1.4.0'))
        self.assertEqual((kept.brand_repository, kept.brand_release),
                         ('git@github.com:acme/brand.git', 'v1.4.0'))
        self.assertEqual(settings.load(), kept)
        self.assertEqual(settings.brand_source(), ('git@github.com:acme/brand.git', 'v1.4.0'))
        for repository, release, says in (
                ('-oProxyCommand=touch', None, 'as one address'),
                ('https://github.com/acme/my brand', None, 'as one address'),
                ('https://pat:secret@github.com/acme/brand.git', None, 'password or token'),
                ('https://github.com/acme/brand.git', '-v1', 'as its tag'),
                ('https://github.com/acme/brand.git', 'v1..2', 'as its tag'),
                (None, 'v1.4.0', 'give the repository too')):
            with self.subTest(repository=repository, release=release), \
                    self.assertRaises(WorkspaceError) as refused:
                settings.save(replace(settings.load(), brand_repository=repository,
                                      brand_release=release))
            self.assertIn(says, str(refused.exception))
        self.assertEqual(settings.load(), kept, 'nothing that was refused was kept')


class SharedTests(SettingsCase):
    """The values every studio shares live only in the studios config."""

    def test_shared_values_are_read_only_from_the_file(self):
        self.write_config(THEIRS)
        loaded = settings.load()
        self.assertEqual((loaded.agent, loaded.model, loaded.effort, loaded.name, loaded.brand,
                          loaded.variant, loaded.output, loaded.brand_repository,
                          loaded.brand_release),
                         ('codex', 'gpt-6-sol', 'high', 'Dan Baskette', 'acme', 'dark', 'pptx',
                          'https://github.com/acme/brand.git', 'v1.4.0'))
        self.assertEqual(settings.brand_source(),
                         ('https://github.com/acme/brand.git', 'v1.4.0'))
        # Another studio changes the file: the next read sees it, with nothing to restart.
        self.write_config(THEIRS.replace('"pptx"', '"google"').replace('"codex"', '"claude"')
                          .replace('"gpt-6-sol"', '"opus"'))
        self.assertEqual((settings.load().output, settings.load().agent),
                         ('google', 'claude'))

    def test_a_copy_kept_in_runner_json_is_never_read(self):
        settings.path().parent.mkdir(parents=True, exist_ok=True)
        settings.path().write_text(json.dumps({'schema': 1, 'agent': 'codex', 'name': 'Old',
                                               'output': 'pptx', 'parallel': 5}))
        loaded = settings.load()
        self.assertEqual((loaded.agent, loaded.name, loaded.output, loaded.parallel),
                         ('claude', None, 'google', 5))

    def test_saving_writes_the_file_and_a_fresh_read_sees_it(self):
        settings.save(replace(settings.load(), agent='codex', model='gpt-6-luna',
                              name='Alex Example', brand='acme', variant='light',
                              output='pptx', brand_repository='https://github.com/acme/b.git',
                              brand_release='v2.0.0', parallel=4, previews='local'))
        found, problem = studios_config.read()
        self.assertIsNone(problem)
        self.assertEqual(found, {
            'schema': 1, 'assistant': {'agent': 'codex', 'model': 'gpt-6-luna'},
            'person': {'name': 'Alex Example'},
            'brand': {'brand': 'acme', 'variant': 'light',
                      'repository': 'https://github.com/acme/b.git', 'release': 'v2.0.0'},
            'output': 'pptx'})
        self.assertEqual(settings.load().agent, 'codex')
        own = self.own()
        for name in ('agent', 'model', 'effort', 'name', 'brand', 'variant', 'output',
                     'brand_repository', 'brand_release'):
            self.assertNotIn(name, own, 'no copy of a shared value is kept here')
        self.assertEqual((own['parallel'], own['previews']), (4, 'local'))

    def test_only_what_changed_is_written_and_every_other_byte_stays(self):
        self.write_config(THEIRS)
        settings.save(replace(settings.load(), parallel=3, step_seconds=600))
        self.assertEqual(self.config.read_text(), THEIRS, 'a per-studio change writes nothing')
        settings.save(replace(settings.load(), variant='light'))
        self.assertEqual(self.config.read_text(),
                         THEIRS.replace('"variant": "dark"', '"variant": "light"'))

    def test_per_studio_settings_stay_in_runner_json(self):
        settings.save(replace(settings.load(), deck_dollars=7.5, notify=True,
                              look_for_updates=False, brand_skill='/some/skill'))
        self.assertFalse(self.config.exists(), 'nothing shared changed, so nothing is written')
        loaded = settings.load()
        self.assertEqual((loaded.deck_dollars, loaded.notify, loaded.look_for_updates,
                          loaded.brand_skill), (7.5, True, False, '/some/skill'))

    def test_a_value_in_the_file_that_cannot_be_used_is_the_default_and_never_written_over(self):
        text = THEIRS.replace('"codex"', '"gemini"').replace('"pptx"', '"keynote"')
        self.write_config(text)
        loaded = settings.load()
        self.assertEqual((loaded.agent, loaded.model, loaded.output), ('claude', None, 'google'))
        settings.save(replace(loaded, parallel=5))
        self.assertEqual(self.config.read_text(), text)

    def test_an_unreadable_file_means_defaults_and_a_refused_save(self):
        self.write_config('{"schema": 1, "assistant": ')
        loaded = settings.load()
        self.assertEqual((loaded.agent, loaded.name, loaded.output, loaded.brand_repository),
                         ('claude', None, 'google', None))
        with self.assertRaisesRegex(WorkspaceError, 'could not be read'):
            settings.save(replace(loaded, agent='codex', parallel=5))
        self.assertEqual(self.config.read_text(), '{"schema": 1, "assistant": ')
        self.assertEqual(settings.load().parallel, 2, 'a refused save keeps nothing')
        settings.save(replace(loaded, parallel=5))
        self.assertEqual(settings.load().parallel, 5, 'a per-studio change still goes through')

    def test_a_form_opened_before_another_studio_changed_a_value_never_writes_over_it(self):
        self.write_config('{"schema": 1, "assistant": {"agent": "claude", "model": "opus"}}')
        shown = settings.load()
        # Meanwhile, another studio changes the model.
        self.write_config('{"schema": 1, "assistant": {"agent": "claude", "model": "sonnet"}}')
        # A save that left the model alone keeps theirs, and writes only what it changed.
        settings.save(replace(shown, effort='high', parallel=4), shown)
        self.assertEqual(json.loads(self.config.read_text())['assistant'],
                         {'agent': 'claude', 'model': 'sonnet', 'effort': 'high'})
        # One that changed the model too is refused, and nothing at all is kept.
        kept = settings.path().read_text()
        before = self.config.read_text()
        with self.assertRaises(WorkspaceError) as refused:
            settings.save(replace(shown, model='haiku', parallel=5), shown)
        self.assertEqual(str(refused.exception), 'The model was changed in another studio '
                         'while this was open, so nothing was saved. Look again, then save.')
        self.assertEqual((self.config.read_text(), settings.path().read_text()), (before, kept))
        # Changed to what the other studio chose, there is nothing to refuse.
        settings.save(replace(shown, model='sonnet'), shown)
        self.assertEqual(settings.load().model, 'sonnet')

    def test_a_stale_form_keeps_the_output_another_studio_chose(self):
        # The output is a word at the top of the file, not a member of a group.
        self.write_config('{"schema": 1, "output": "google"}')
        shown = settings.load()
        self.write_config('{"schema": 1, "output": "pptx"}')
        settings.save(replace(shown, name='Alex'), shown)
        self.assertEqual(json.loads(self.config.read_text()),
                         {'schema': 1, 'output': 'pptx', 'person': {'name': 'Alex'}})
        self.write_config('{"schema": 1, "person": {"name": "Blake"}}')
        with self.assertRaisesRegex(WorkspaceError, 'Your name was changed in another studio'):
            settings.save(replace(shown, name='Casey', output='pptx'), shown)
        self.assertEqual(json.loads(self.config.read_text()),
                         {'schema': 1, 'person': {'name': 'Blake'}})

    def test_own_and_forget_own_are_what_migration_moves(self):
        settings.path().parent.mkdir(parents=True, exist_ok=True)
        settings.path().write_text(json.dumps({
            'schema': 1, 'agent': 'codex', 'model': None, 'name': 'Old Name', 'brand': None,
            'output': 'pptx', 'brand_repository': 'https://github.com/acme/b.git',
            'brand_release': 'v1', 'parallel': 5}))
        self.assertEqual(settings.own(), {'agent': 'codex', 'name': 'Old Name',
                                          'output': 'pptx',
                                          'brand_repository': 'https://github.com/acme/b.git',
                                          'brand_release': 'v1'})
        settings.forget_own()
        self.assertEqual(self.own(), {'schema': 1, 'parallel': 5})
        self.assertEqual(settings.own(), {})


if __name__ == '__main__':
    unittest.main()
