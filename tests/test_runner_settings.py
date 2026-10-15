import unittest
from dataclasses import replace

import helpers  # noqa: F401  sets PRESENTATION_STUDIO_DATA
from runner import settings
from workspace import WorkspaceError


class SettingsTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
