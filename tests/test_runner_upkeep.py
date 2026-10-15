"""What the runner looks after: Presentation Studio and its two companions (harness-slides and
harness-research) against the pins in installer/companions.json, which releases exist, the
update of the companions and which guidance a new deck gets. The brand skill is not a
companion: its row and its install are in test_runner_brand_source.py.

Each test has a home of its own with the companions it needs laid out as their installers
leave them, and an installer folder of its own: with no installer, or with a small stand-in
that answers as the real one does. The link, update and upgrade tests at the end install
Presentation Studio with its real installer into a temporary home, with the installer tests'
stand-in companions. Every repository is a bare one made here. Nothing real is read, and
nothing is fetched from anywhere but there.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import helpers
import runner_support  # noqa: F401  puts the runner on the import path

import home
from workspace import WorkspaceError

from runner import settings, upkeep
from test_installer import NODE, StandIn, install, write_pins

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
            'STUDIOS_CONFIG': str(self.base / 'studios-config.json'),
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


# --- with the real installer --------------------------------------------------------------

_made = {}


def settle(keep: upkeep.Upkeep) -> None:
    """Wait for what it does in the background, without ending anything."""
    for thread in list(keep._threads):
        thread.join(60)


def setUpModule():
    """Each companion's stand-in, pinned at its first release, as a maintainer pins it."""
    holder = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(holder.cleanup)
    base = Path(holder.name).resolve()
    pins = {}
    for name, version in (('harness-research', '0.8.0'), ('harness-slides', '0.14.1')):
        _made[name] = StandIn(base, name)
        commit = _made[name].release(version)
        pins[name] = {'repository': str(_made[name].bare), 'version': '0.0.0',
                      'commit': '0' * 40, 'sha256': '0' * 64, 'stub': 'bootstrap/SKILL.md',
                      'installer': 'scripts/install.mjs'}
        write_pins(base / 'companions.json', pins)
        install.pin(base / 'companions.json', name, commit)
        pins = install.read_pins(base / 'companions.json')
    _made['pins'] = pins


class InstalledCase(unittest.TestCase):
    """Presentation Studio installed by its own installer into a temporary home, with its
    data folder where the installer keeps its record."""

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        self.home = self.base / 'home'
        self.root = self.home / '.local' / 'share' / 'presentation-studio'
        self.claude = self.home / '.claude' / 'skills'
        self.codex = self.home / '.agents' / 'skills'
        self.claude.mkdir(parents=True)
        self.codex.mkdir(parents=True)
        self.pins_file = self.base / 'companions.json'
        write_pins(self.pins_file, _made['pins'])
        self.source = self.base / 'presentation-studio.git'
        git(self.base, 'init', '-q', '--bare', str(self.source))
        for patch in (mock.patch.dict(os.environ, {
                          'PRESENTATION_STUDIO_DATA': str(self.root),
                          'STUDIOS_CONFIG': str(self.base / 'studios-config.json'),
                          'PRESENTATION_STUDIO_SOURCE': str(self.source)}),
                      mock.patch.object(install, 'PINS', self.pins_file),
                      mock.patch.object(install, 'PLATFORM', 'linux'),
                      # What else this computer has is the installer tests' business.
                      mock.patch.object(install, 'prerequisites',
                                        lambda *asked, **named: {'notes': []})):
            patch.start()
            self.addCleanup(patch.stop)
        for name in ('BRAND_SKILL_RUNTIME', 'HARNESS_SLIDES_RUNTIME',
                     'HARNESS_RESEARCH_RUNTIME'):
            os.environ.pop(name, None)

    def installed(self, *args: str) -> Path:
        """Install Presentation Studio into the temporary home; the installed version."""
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = install.main(['install', '--yes', '--companions', 'skip', '--json',
                                 '--home', str(self.home), *args])
        self.assertEqual(code, 0, printed.getvalue())
        result = json.loads(printed.getvalue())
        return self.root / 'versions' / result['version'] if result['mode'] == 'managed' \
            else helpers.REPO

    def keeper(self, staged: Path | None = None, after=None) -> upkeep.Upkeep:
        """What looks after the skills, as the runner of that version makes it."""
        staged = staged or self.installed()
        return upkeep.Upkeep(home_dir=self.home, root=self.root,
                             installer=staged / 'installer' / 'install.py', after=after)


class LinkTests(InstalledCase):
    def test_a_missing_link_to_a_whole_copy_is_put_back_and_said(self):
        keep = self.keeper()
        link = self.claude / 'presentation-studio'
        link.unlink()
        found = keep.check(repair=True)
        self.assertEqual(os.readlink(link), str(self.root / 'current'))
        self.assertTrue((link / 'SKILL.md').is_file())
        self.assertEqual(found['repaired'], [f'The link for Claude Code was missing, and was '
                                             f'put back: {link}.'])
        self.assertEqual([(entry['assistant'], entry['state']) for entry in found['links']],
                         [('Claude Code', 'repaired'), ('Codex', 'ok')])
        self.assertEqual(keep.check(repair=True)['repaired'], [], 'once put back, it is ok')

    def test_looking_without_repairing_changes_nothing(self):
        keep = self.keeper()
        (self.codex / 'presentation-studio').unlink()
        found = keep.check(repair=False)
        self.assertFalse(os.path.lexists(self.codex / 'presentation-studio'))
        self.assertEqual(found['repaired'], [])
        self.assertEqual(found['links'][1]['state'], 'missing')
        self.assertIn('It is put back when Presentation Studio starts.',
                      found['links'][1]['says'])

    def test_only_what_the_installer_placed_is_ever_put_back(self):
        keep = self.keeper()
        claude, codex = self.claude / 'presentation-studio', self.codex / 'presentation-studio'
        claude.unlink()
        claude.mkdir()                               # a folder of someone's own
        (claude / 'SKILL.md').write_text('mine\n')
        codex.unlink()
        codex.symlink_to(self.base)                  # a link someone pointed elsewhere
        found = keep.check(repair=True)
        self.assertEqual(found['repaired'], [])
        self.assertEqual((claude / 'SKILL.md').read_text(), 'mine\n')
        self.assertEqual(os.readlink(codex), str(self.base))
        self.assertEqual([entry['state'] for entry in found['links']],
                         ['left alone', 'left alone'])
        self.assertIn('is not the link the installer placed, so it was left alone',
                      found['links'][0]['says'])

    def test_an_assistant_whose_skill_folder_is_gone_is_not_given_one_again(self):
        keep = self.keeper()
        shutil.rmtree(self.home / '.agents')
        found = keep.check(repair=True)
        self.assertFalse((self.home / '.agents').exists())
        self.assertEqual(found['links'][1]['state'], 'left alone')
        self.assertIn('is gone, so Presentation Studio was not linked into it again',
                      found['links'][1]['says'])

    def test_the_link_to_the_version_and_the_commands_are_put_back_when_missing(self):
        staged = self.installed()
        keep = self.keeper(staged)
        (self.root / 'current').unlink()
        (self.root / 'presentation').unlink()
        (self.root / 'studio').write_text('my own studio\n')   # not missing: left alone
        found = keep.check(repair=True)
        self.assertEqual(os.readlink(self.root / 'current'), str(staged))
        self.assertTrue(install.ours(self.root / 'presentation'))
        self.assertIn(str(self.root / 'current' / 'runner' / 'studio.py'),
                      (self.root / 'presentation').read_text())
        self.assertEqual((self.root / 'studio').read_text(), 'my own studio\n')
        self.assertEqual(found['repaired'], [
            f"The link to the installed version was missing, and was put back: "
            f"{self.root / 'current'}.",
            f"The command the skill runs its helper with was missing, and was written again: "
            f"{self.root / 'presentation'}."])
        self.assertEqual([entry['state'] for entry in found['links']], ['ok', 'ok'],
                         'the links work again once the version they point through is back')

    def test_a_link_whose_copy_is_gone_is_said_and_left(self):
        keep = self.keeper()
        (self.root / 'current').unlink()
        (self.root / 'current').symlink_to(self.base / 'gone')
        state = install.read_state(self.root)
        state['current'] = 'not-there'
        install.write_state(self.root, state)
        found = keep.check(repair=True)
        self.assertEqual(found['repaired'], [])
        self.assertEqual(found['links'][0]['state'], 'missing')
        self.assertIn('which is not there any more. Run the installer again.',
                      found['links'][0]['says'])

    def test_where_the_record_is_follows_where_the_runner_was_installed(self):
        version = self.root / 'versions' / '1.0.0-abc'
        self.assertEqual(upkeep.install_root(version / 'runner'), self.root)
        self.assertEqual(upkeep.install_root(helpers.REPO / 'runner'), home.data_root())


class InstalledUpdateTests(InstalledCase):
    def test_an_update_runs_the_installer_of_this_version_in_the_background(self):
        staged = self.installed()
        going, told, asked = threading.Event(), [], []

        def supervise(command, cwd, env, stdin, seconds, errors, each, stop):
            asked.append((command, seconds))
            going.wait(30)
            each(json.dumps({'action': 'companions', 'companions': {
                'harness-research': {'state': 'installed', 'wanted': '0.8.0'},
                'harness-slides': {'state': 'failed', 'wanted': '0.14.1',
                                   'detail': 'its installer needs Node 20 or newer.'}}})
                 .encode())
            return 0, False

        keep = self.keeper(staged, after=lambda: told.append('looked again'))
        keep.check()
        with mock.patch.object(upkeep.companion, 'supervise', supervise):
            shown = keep.update(working=False)
            self.assertEqual(shown['update']['state'], 'running')
            with self.assertRaises(WorkspaceError) as refused:
                keep.update(working=False)
            self.assertEqual(str(refused.exception), upkeep.UPDATING)
            going.set()
            settle(keep)
        (command, seconds), = asked
        self.assertEqual(command[2:], [
            str(staged / 'installer' / 'install.py'), 'companions', '--companions', 'install',
            '--while-open', '--json', '--home', str(self.home), '--root', str(self.root)])
        self.assertEqual(seconds, upkeep.UPDATE_SECONDS)
        done = keep.report()['update']
        self.assertEqual(done['state'], 'failed')
        self.assertEqual(done['says'], 'harness-research 0.8.0 was installed by its own '
                         'installer. harness-slides 0.14.1 was not installed: its installer '
                         'needs Node 20 or newer.')
        self.assertEqual(told, ['looked again'])

    @unittest.skipUnless(NODE, 'a companion installs itself with Node')
    def test_an_update_brings_each_companion_through_its_own_checked_install(self):
        staged = self.installed('--target', 'claude')
        keep = self.keeper(staged)
        self.assertEqual([entry['state'] for entry in keep.check()['companions']],
                         ['missing', 'missing'])
        keep.update(working=False)
        settle(keep)
        done = keep.report()
        self.assertEqual(done['update']['state'], 'done', done['update']['says'])
        self.assertEqual(sorted(entry['state'] for entry in done['companions']), ['ok', 'ok'])
        state = install.read_state(self.root)
        self.assertEqual(sorted(state['companions']), ['harness-research', 'harness-slides'])


class UpgradeTests(InstalledCase):
    """Upgrading Presentation Studio itself, through the installer of the version fetched."""

    def setUp(self):
        super().setUp()
        self.keep = self.keeper()
        self.keep.check()
        self.work = self.base / 'presentation-studio-work'
        git(self.base, 'init', '-q', str(self.work))
        (self.work / 'VERSION').write_text('1\n')
        git(self.work, 'add', '-A')
        git(self.work, 'commit', '-q', '-m', 'one')

    def release(self, *versions: str) -> None:
        for version in versions:
            git(self.work, 'tag', version)
        git(self.work, 'push', '-q', '--tags', str(self.source))

    def test_a_checkout_shows_the_versions_and_says_it_is_upgraded_with_git_pull(self):
        keep = upkeep.Upkeep(home_dir=self.home, root=self.base / 'nothing-installed',
                             installer=helpers.REPO / 'installer' / 'install.py')
        keep.check()
        self.release('v99.0.0')
        keep.look()
        versions = keep.report()['versions']
        self.assertEqual((versions['checkout'], versions['command']),
                         (True, f'cd {helpers.REPO} && git pull'))
        self.assertFalse(versions['upgrade']['offered'])
        with self.assertRaises(WorkspaceError) as refused:
            keep.upgrade(False, '99.0.0')
        self.assertEqual(str(refused.exception), upkeep.FROM_CHECKOUT)

    def test_an_installed_version_is_offered_the_newer_one(self):
        self.release('v99.0.0')
        self.assertTrue(self.keep.look())
        versions = self.keep.report()['versions']
        self.assertEqual((versions['checkout'], versions['command']), (False, None))
        self.assertEqual((versions['upgrade']['offered'], versions['upgrade']['version']),
                         (True, '99.0.0'))

    def test_the_upgrade_runs_the_fetched_versions_own_installer_beside_this_one(self):
        self.release('v99.0.0')
        self.keep.look()
        asked, fetched, going = [], [], threading.Event()

        def fetch(repository, ref, into):
            going.wait(30)   # held until the test has seen it running
            fetched.append((repository, ref))
            tree = into / 'tree'
            tree.mkdir()
            (tree / 'VERSION').write_text('99.0.0\n')   # the repository's own, at its top
            return tree, 'c' * 40

        def supervise(command, cwd, env, stdin, seconds, errors, each, stop):
            asked.append((command, seconds))
            staged = self.root / 'versions' / '99.0.0-abcdef012345'
            staged.mkdir(parents=True)
            install.replace_link(self.root / 'current', staged)
            each(json.dumps({'action': 'install', 'mode': 'managed',
                             'version': '99.0.0-abcdef012345'}).encode())
            return 0, False

        with mock.patch.object(upkeep, 'fetch_tree', fetch), \
                mock.patch.object(upkeep.companion, 'supervise', supervise):
            shown = self.keep.upgrade(False, '99.0.0')
            self.assertEqual(shown['versions']['upgrade']['state'], 'running')
            going.set()
            settle(self.keep)
        self.assertEqual(fetched, [(str(self.source), 'refs/tags/v99.0.0')])
        (command, seconds), = asked
        self.assertEqual(command[3:], [
            'install', '--yes', '--json', '--companions', 'skip', '--while-open',
            '--home', str(self.home), '--root', str(self.root), '--target', 'both'])
        self.assertTrue(command[2].endswith('/tree/installer/install.py'))
        self.assertEqual(seconds, upkeep.UPGRADE_SECONDS)
        versions = self.keep.report()['versions']
        self.assertEqual((versions['upgrade']['state'], versions['upgrade']['restart']),
                         ('restart', True))
        left = []
        self.keep.leave = lambda: left.append('left')
        with self.assertRaises(WorkspaceError) as refused:
            self.keep.restart(True)
        self.assertEqual(str(refused.exception), upkeep.RESTART_WORKING)
        self.assertEqual(self.keep.restart(False)['versions']['upgrade']['state'],
                         'restarting')
        self.assertEqual((self.keep.restarting, left),
                         (['/bin/sh', str(self.root / 'studio'), 'serve'], ['left']))

    def test_a_version_that_is_not_the_one_shown_is_not_installed(self):
        self.release('v99.0.0')
        self.keep.look()

        def fetch(repository, ref, into):
            (into / 'tree').mkdir()
            (into / 'tree' / 'VERSION').write_text('1.0.0\n')
            return into / 'tree', 'c' * 40

        with mock.patch.object(upkeep, 'fetch_tree', fetch), \
                mock.patch.object(upkeep.companion, 'supervise') as ran:
            self.keep.upgrade(False, '99.0.0')
            settle(self.keep)
        ran.assert_not_called()
        upgrade = self.keep.report()['versions']['upgrade']
        self.assertEqual(upgrade['state'], 'failed')
        self.assertEqual(upgrade['says'], f'Presentation Studio 99.0.0 was not installed: '
                         f'{self.source} has version 1.0.0 at refs/tags/v99.0.0.')
        with self.assertRaises(WorkspaceError) as refused:
            self.keep.restart(False)
        self.assertEqual(str(refused.exception), upkeep.NO_RESTART)


if __name__ == '__main__':
    unittest.main()
