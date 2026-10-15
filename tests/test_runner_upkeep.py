"""What the runner looks after: Presentation Studio and its two companions (harness-slides and
harness-research) against the pins in installer/companions.json, which releases exist, the
update of the companions and which guidance a new deck gets. The brand skill is not a
companion: its row and its install are in test_runner_brand_source.py.

Each test has a home of its own with the companions it needs laid out as their installers
leave them, and an installer folder of its own: with no installer, or with a small stand-in
that answers as the real one does. Training Studio's link and upgrade tests drive its real
installer and come with Task 14's. Every repository is a bare one made here. Nothing real is
read, and nothing is fetched from anywhere but there.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
import runner_support  # noqa: F401  puts the runner on the import path

from workspace import WorkspaceError

from runner import settings, upkeep

VERSION = (helpers.REPO / 'VERSION').read_text().strip()
PINS = {'harness-slides': '0.14.1', 'harness-research': '0.8.0'}
STAND_IN = '''"""A stand-in for the installer: what upkeep asks of it, answered as it does."""
import json
import sys
from pathlib import Path

HARNESS = {'claude': 'Claude Code', 'codex': 'Codex'}


class InstallError(Exception):
    pass


def read_state(root):
    return None


def found_harnesses(home):
    return []


if __name__ == '__main__':
    Path(__file__).with_name('asked.json').write_text(json.dumps(sys.argv[1:]))
    print(json.dumps({'companions': {'harness-slides': {'state': 'installed',
                                                        'wanted': '0.14.1'}}}))
'''


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(['git', '-c', 'user.name=A Test', '-c', 'user.email=t@example.com',
                           *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


class UpkeepCase(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        self.home = self.base / 'home'
        self.skills = self.home / '.claude' / 'skills'
        self.skills.mkdir(parents=True)
        self.installer = self.base / 'version' / 'installer'
        self.installer.mkdir(parents=True)
        self.source = self.base / 'presentation-studio.git'
        git(self.base, 'init', '-q', '--bare', str(self.source))
        patch = mock.patch.dict(os.environ, {
            'PRESENTATION_STUDIO_DATA': str(self.base / 'data'),
            'PRESENTATION_STUDIO_SOURCE': str(self.source)})
        patch.start()
        self.addCleanup(patch.stop)
        for name in ('BRAND_SKILL_RUNTIME', 'HARNESS_SLIDES_RUNTIME',
                     'HARNESS_RESEARCH_RUNTIME'):
            os.environ.pop(name, None)

    def keeper(self, after=None) -> upkeep.Upkeep:
        return upkeep.Upkeep(home_dir=self.home, root=self.base / 'root',
                             installer=self.installer / 'install.py', after=after)

    def companion(self, name: str, version: str | None, where: Path | None = None) -> Path:
        """A companion as its own installer leaves it, or one whose version cannot be read."""
        folder = (where or self.skills) / name
        (folder / 'scripts').mkdir(parents=True)
        (folder / 'SKILL.md').write_text('its entry\n')
        (folder / 'scripts' / f'{name}.mjs').write_text('// lists its brands\n')
        package = {'name': name}
        if version:
            package['version'] = version
        (folder / 'package.json').write_text(json.dumps(package))
        return folder

    def pin(self, **versions) -> None:
        pins = {name: {'repository': str(self.base / f'{name}.git'), 'version': version,
                       'commit': 'a' * 40, 'sha256': 'b' * 64, 'stub': 'bootstrap/SKILL.md',
                       'installer': 'scripts/install.mjs'}
                for name, version in {**PINS, **versions}.items()}
        (self.installer / 'companions.json').write_text(json.dumps(
            {'schema': 1, 'companions': pins}))

    def stand_in(self) -> None:
        (self.installer / 'install.py').write_text(STAND_IN)

    def states(self, found: dict) -> dict:
        return {entry['name']: entry['state'] for entry in found['companions']}


class CompanionTests(UpkeepCase):
    def test_with_no_pins_yet_each_companion_is_only_looked_for(self):
        self.companion('harness-slides', '0.14.1')
        found = self.keeper().check(repair=False)
        self.assertEqual(self.states(found), {'harness-slides': 'ok',
                                              'harness-research': 'missing'})
        slides = found['companions'][0]
        self.assertEqual((slides['wanted'], slides['repository'], slides['says']),
                         (None, None, 'harness-slides 0.14.1, for Claude Code. No version is '
                                      'pinned for it yet.'))
        self.assertEqual(slides['found'], {'Claude Code': '0.14.1'})
        self.assertEqual(found['companions'][1]['says'], 'harness-research is not installed '
                         'for Claude Code, and research cannot run without it.')
        self.assertEqual((found['installer'], found['problem']), (False, upkeep.NO_INSTALLER))

    def test_each_companion_is_compared_with_its_pin(self):
        self.pin()
        self.companion('harness-slides', '0.13.1')
        self.companion('harness-research', '0.9.0')
        found = self.keeper().check(repair=False)
        self.assertEqual(self.states(found), {'harness-slides': 'older',
                                              'harness-research': 'ok'})
        self.assertEqual(found['companions'][0]['says'], 'harness-slides for Claude Code is '
                         'older than the 0.14.1 this Presentation Studio was made with.')
        self.assertEqual(found['companions'][0]['commit'], 'a' * 12)
        rows = {row['name']: row for row in self.keeper().versions(found, None, False)['rows']}
        self.assertEqual((rows['harness-slides']['state'], rows['harness-slides']['target']),
                         ('update', '0.14.1'))
        self.assertEqual(rows['harness-research']['state'], 'current')
        self.assertEqual(rows['brand skill']['state'], 'unknown')

    def test_no_brand_skill_is_pinned_or_named(self):
        self.pin()
        found = self.keeper().check(repair=False)
        self.assertEqual(sorted(self.states(found)), ['harness-research', 'harness-slides'])
        rows = self.keeper().versions(found, None, False)['rows']
        self.assertEqual([row['name'] for row in rows],
                         ['presentation-studio', 'harness-slides', 'harness-research',
                          'brand skill'])
        self.assertEqual(rows[-1]['says'], 'No brand skill is installed, so a deck stops where '
                         'it first needs your brand. Name its repository in Settings to install '
                         'and upgrade it from here.')

    def test_each_assistant_is_looked_at_for_itself(self):
        self.pin()
        codex = self.home / '.agents' / 'skills'
        self.companion('harness-slides', '0.14.1')
        self.companion('harness-slides', '0.13.1', codex)
        self.companion('harness-research', '0.8.0')
        found = self.keeper().check(repair=False)
        self.assertEqual(self.states(found), {'harness-slides': 'older',
                                              'harness-research': 'missing'})
        self.assertEqual(found['companions'][0]['says'], 'harness-slides for Codex is older '
                         'than the 0.14.1 this Presentation Studio was made with.')
        self.assertEqual(found['companions'][1]['says'], 'harness-research is not installed '
                         'for Codex, and research cannot run without it. This Presentation '
                         'Studio was made with 0.8.0.')
        self.companion('harness-research', None, codex)
        self.assertEqual(self.states(self.keeper().check(repair=False))['harness-research'],
                         'unread')

    def test_only_the_copy_in_each_assistants_skills_folder_counts(self):
        self.pin()
        shared = self.home / '.local' / 'share' / 'harness-slides'
        self.companion('harness-slides', '0.1.0', shared)
        (shared / 'current').symlink_to(shared / 'harness-slides')
        self.companion('harness-slides', '0.14.1')
        elsewhere = self.companion('harness-slides', '0.2.0', self.base / 'mine')
        with mock.patch.dict(os.environ, {'HARNESS_SLIDES_RUNTIME': str(elsewhere)}):
            found = self.keeper().check(repair=False)
        self.assertEqual(found['companions'][0]['state'], 'ok')
        self.assertEqual(found['companions'][0]['found'], {'Claude Code': '0.14.1'})

    def test_a_companion_whose_version_cannot_be_read_is_said_and_left_alone(self):
        self.pin()
        self.companion('harness-research', None)
        found = self.keeper().check(repair=False)
        self.assertEqual(found['companions'][1]['state'], 'unread')
        self.assertIn('its version could not be read', found['companions'][1]['says'])

    def test_pins_that_cannot_be_read_are_said_and_the_rest_is_still_looked_at(self):
        (self.installer / 'companions.json').write_text('{"schema": 1, "companions": ')
        self.companion('harness-slides', '0.14.1')
        found = self.keeper().check(repair=False)
        self.assertIn('does not say which companion skills to install', found['problem'])
        self.assertEqual(found['companions'][0]['state'], 'ok')
        self.assertEqual(upkeep.read_pins(self.base / 'nothing.json'), ({}, None))

    def test_looking_runs_nothing(self):
        self.pin()
        self.companion('harness-slides', '0.14.1')
        with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('ran')):
            keep = self.keeper()
            with mock.patch.object(keep, '_tools', return_value={}), \
                    mock.patch.object(keep, '_brands', return_value=[]):
                self.assertEqual(self.states(keep.check(repair=False))['harness-slides'], 'ok')


class UpdateTests(UpkeepCase):
    def test_with_no_installer_nothing_is_brought(self):
        self.pin()
        with self.assertRaises(WorkspaceError) as caught:
            self.keeper().update(False)
        self.assertEqual(str(caught.exception), upkeep.NO_INSTALLER)

    def test_nothing_to_bring_and_a_working_deck_are_refused_in_a_sentence(self):
        self.stand_in()
        self.pin()
        for name, version in PINS.items():
            self.companion(name, version)
        with self.assertRaises(WorkspaceError) as caught:
            self.keeper().update(False)
        self.assertEqual(str(caught.exception), upkeep.NOTHING)
        (self.skills / 'harness-slides').rename(self.base / 'gone')
        with self.assertRaises(WorkspaceError) as caught:
            self.keeper().update(True)
        self.assertEqual(str(caught.exception), upkeep.WORKING)

    def test_a_companion_with_no_pin_is_never_offered(self):
        self.stand_in()
        keep = self.keeper()
        keep.check(repair=False)
        self.assertFalse(keep.report()['update']['offered'])
        with self.assertRaises(WorkspaceError) as caught:
            keep.update(False)
        self.assertEqual(str(caught.exception), upkeep.NOTHING)

    def test_an_update_runs_the_installer_beside_the_runner_in_the_background(self):
        self.stand_in()
        self.pin()
        looked = []
        keep = self.keeper(after=lambda: looked.append('again'))
        shown = keep.update(False)
        self.assertEqual(shown['update']['state'], 'running')
        for thread in list(keep._threads):
            thread.join(60)
        update = keep.report()['update']
        self.assertEqual((update['state'], update['says']),
                         ('done', 'harness-slides 0.14.1 was installed by its own installer.'))
        asked = json.loads((self.installer / 'asked.json').read_text())
        self.assertEqual(asked[:4], ['companions', '--companions', 'install', '--while-open'])
        self.assertIn(str(self.home), asked)
        self.assertEqual(looked, ['again'])


class ReleaseTests(UpkeepCase):
    def release(self, version: str) -> None:
        work = self.base / 'work'
        if not work.exists():
            git(self.base, 'init', '-q', '-b', 'main', str(work))
        (work / 'VERSION').write_text(f'{version}\n')
        git(work, 'add', '-A')
        git(work, 'commit', '-q', '-m', f'Release {version}')
        git(work, 'tag', f'v{version}')
        git(work, 'push', '-q', '--tags', str(self.source), 'main')

    def test_a_newer_presentation_studio_is_said_and_offered_only_where_it_can_be(self):
        self.release('99.0.0')
        keep = self.keeper()
        keep.check(repair=False)
        self.assertTrue(keep.look())
        report = keep.report()
        own = report['versions']['rows'][0]
        self.assertEqual((own['name'], own['installed'], own['newest'], own['state']),
                         ('presentation-studio', keep.version(), '99.0.0', 'update'))
        self.assertFalse(report['versions']['upgrade']['offered'],
                         'never from a copy of the repository')
        with self.assertRaises(WorkspaceError) as caught:
            keep.upgrade(False, '99.0.0')
        self.assertEqual(str(caught.exception), upkeep.NO_INSTALLER)
        self.stand_in()
        with self.assertRaises(WorkspaceError) as caught:
            self.keeper().upgrade(False, '99.0.0')
        self.assertEqual(str(caught.exception), upkeep.FROM_CHECKOUT)

    def test_it_looks_at_most_once_a_day_and_never_when_turned_off(self):
        self.release('0.2.0')
        keep = self.keeper()
        self.assertTrue(keep.look())
        self.assertFalse(keep.look(), 'once a day')
        kept = json.loads(keep.saved_path().read_text())
        self.assertEqual(kept['found']['presentation-studio']['latest'], '0.2.0')
        keep.saved_path().unlink()
        settings.save(settings.Settings(look_for_updates=False))
        self.assertFalse(keep.look())
        self.assertFalse(keep.saved_path().exists())

    def test_each_pinned_companion_is_looked_for_in_its_own_repository(self):
        self.pin()
        self.assertEqual(sorted(self.keeper().repositories()),
                         ['harness-research', 'harness-slides', 'presentation-studio'])
        (self.installer / 'companions.json').unlink()
        self.assertEqual(sorted(self.keeper().repositories()), ['presentation-studio'])

    def test_before_anything_is_known_the_newest_is_unknown(self):
        keep = self.keeper()
        self.assertTrue(keep.report()['checking'], 'the report never waits for a look')
        keep.check(repair=False)
        self.assertEqual(keep.report()['versions']['rows'][0]['state'], 'unknown')

    def test_versions_can_be_dismissed_until_something_else_is_wanted(self):
        keep = self.keeper()
        keep.check(repair=False)
        key = keep.report()['versions']['key']
        self.assertEqual(key, 'harness-slides missing, harness-research missing')
        self.assertTrue(keep.dismiss(key)['versions']['dismissed'])
        self.companion('harness-slides', '0.14.1')
        keep.check(repair=False)
        self.assertFalse(keep.report()['versions']['dismissed'])


class GuidanceTests(UpkeepCase):
    def test_which_guidance_a_new_deck_gets_is_said(self):
        said = upkeep.Upkeep.guidance()
        self.assertEqual(said['commit'], None)
        self.assertEqual(said['says'], f'New decks follow the guidance installed with '
                         f'Presentation Studio {VERSION}. None has been fetched on this '
                         'computer yet.')


if __name__ == '__main__':
    unittest.main()
