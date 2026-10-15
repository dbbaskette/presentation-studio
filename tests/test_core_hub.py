import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  quiet git, PRESENTATION_STUDIO_DATA
import hub
from workspace import WorkspaceError

IDENTITY = {'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.com',
            'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.com'}


class HubTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        patcher = mock.patch.dict(os.environ, {
            **IDENTITY, 'PRESENTATION_STUDIO_DATA': str(self.base / 'data')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '--quiet', '-b', 'main', str(self.remote)],
                       check=True)
        self.root = self.base / 'deck'
        self.root.mkdir()

    def test_join_sync_listing_and_use(self):
        joined = hub.join(str(self.remote), init=True)
        self.assertEqual((joined['hub'], joined['initialised'], joined['pushed'],
                          joined['decks']), ('remote', True, True, 0))
        repo = hub.clone_of('remote')
        self.assertIn('## Decks', (repo / 'README.md').read_text(encoding='utf-8'))

        record = repo / 'decks' / 'rolling' / '1' / 'record.json'
        hub.home.write_json(record, {'title': 'Rolling', 'published_by': 'T',
                                     'published_at': '2026-01-02T00:00:00Z'})
        report = hub.sync('remote')
        self.assertTrue(report['pushed'])
        self.assertIn('[Rolling](decks/rolling/1/)', (repo / 'README.md').read_text('utf-8'))

        entry = hub.listing(self.root)['hubs'][0]
        self.assertEqual((entry['name'], entry['pushed'], entry['chosen']),
                         ('remote', True, False))
        self.assertEqual(hub.use(self.root, 'remote'), {'hub': 'remote'})
        self.assertTrue(hub.listing(self.root)['hubs'][0]['chosen'])

        # a second computer gets the deck from the remote
        self.assertEqual([d['deck'] for d in hub.latest(repo)], ['rolling'])

    def test_a_second_join_of_the_same_hub_is_refused(self):
        hub.join(str(self.remote), init=True)
        with self.assertRaises(WorkspaceError):
            hub.join(str(self.remote), init=True)

    def test_an_address_with_a_token_is_refused(self):
        with self.assertRaisesRegex(WorkspaceError, 'password or token'):
            hub.join('https://user:secret@example.com/hub.git')

    def test_use_refuses_a_hub_that_is_not_joined(self):
        with self.assertRaises(WorkspaceError):
            hub.use(self.root, 'nowhere')


if __name__ == '__main__':
    unittest.main()
