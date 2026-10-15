import os
import unittest
from pathlib import Path

import helpers  # noqa: F401  sets PRESENTATION_STUDIO_DATA
import home
import workspace


class HomeTests(unittest.TestCase):
    def test_data_root_is_the_test_folder(self):
        self.assertEqual(home.data_root(), Path(os.environ['PRESENTATION_STUDIO_DATA']))

    def test_json_round_trip(self):
        path = home.data_root() / 'x' / 'a.json'
        home.write_json(path, {'a': 1})
        self.assertEqual(home.read_json(path), {'a': 1})

    def test_write_atomic_replaces(self):
        path = home.data_root() / 'b.txt'
        workspace.write_atomic(path, 'one')
        workspace.write_atomic(path, 'two')
        self.assertEqual(path.read_text(encoding='utf-8'), 'two')
        self.assertEqual([p.name for p in path.parent.glob('.b.txt.*')], [])

    def test_error_is_a_sentence(self):
        self.assertEqual(str(workspace.WorkspaceError('No.')), 'No.')
