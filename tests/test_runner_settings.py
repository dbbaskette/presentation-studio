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


if __name__ == '__main__':
    unittest.main()
