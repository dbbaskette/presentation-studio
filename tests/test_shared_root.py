import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401
from runner import gitstate


def git(cwd, *args):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


class SharedRootTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        patcher = mock.patch.dict(os.environ, {'PRESENTATION_STUDIO_DATA': str(self.tmp / 'data')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.remote = self.tmp / 'team.git'
        git(self.tmp, 'init', '--bare', '-b', 'main', str(self.remote))
        seed = self.tmp / 'seed'
        git(self.tmp, 'clone', str(self.remote), str(seed))
        (seed / 'trainings').mkdir()
        (seed / 'trainings' / 'hub.json').write_text('{"schema": 1, "tool": "training-studio"}\n')
        (seed / 'blogs').mkdir()
        (seed / 'blogs' / 'README.md').write_text('# Blogs\n')
        git(seed, 'add', '-A')
        git(seed, '-c', 'user.name=t', '-c', 'user.email=t@e', 'commit', '-m', 'seed')
        git(seed, 'push', 'origin', 'main')

    def test_presentations_folder_sits_beside_the_others(self):
        ws = gitstate.join(str(self.remote))
        self.assertEqual(ws.folder, 'presentations')
        self.assertTrue((ws.root / 'hub.json').is_file())
        gitstate.sync(ws)
        check = self.tmp / 'check'
        git(self.tmp, 'clone', str(self.remote), str(check))
        self.assertEqual((check / 'trainings' / 'hub.json').read_text(),
                         '{"schema": 1, "tool": "training-studio"}\n')
        self.assertEqual((check / 'blogs' / 'README.md').read_text(), '# Blogs\n')
        self.assertIn('presentation-studio', (check / 'presentations' / 'hub.json').read_text())

    def test_a_deck_commit_touches_only_presentations_and_a_push_leaves_the_rest_alone(self):
        ws = gitstate.join(str(self.remote))
        (ws.root / 'quarterly-review').mkdir()
        (ws.root / 'quarterly-review' / 'run.json').write_text('{}\n')
        self.assertTrue(gitstate.commit(ws, 'Start the review'))
        changed = git(ws.repo, 'show', '--name-only', '--format=', 'HEAD').split()
        self.assertEqual(changed, ['presentations/quarterly-review/run.json'])
        before = git(self.remote, 'rev-parse', 'main:trainings', 'main:blogs')
        gitstate.sync(ws)
        self.assertEqual(git(self.remote, 'rev-parse', 'main:trainings', 'main:blogs'), before)
        self.assertIn('quarterly-review/run.json',
                      git(self.remote, 'ls-tree', '-r', '--name-only', 'main', 'presentations'))
        self.assertEqual(git(self.remote, 'ls-tree', '--name-only', 'main').split(),
                         ['blogs', 'presentations', 'trainings'])


if __name__ == '__main__':
    unittest.main()
