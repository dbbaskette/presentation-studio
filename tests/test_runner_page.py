"""The runner's server: every address the page may ask, each thing it refuses, and the engine
behind it.

Most classes ask the page without a socket, so they run where a port cannot be opened.
WireTests talks to a real server on a local port and is skipped where that is not allowed.
Nothing starts an agent, looks at the real computer or touches the network: the engine runs
over the stand-ins and scripted workers of runner_support. The team tests that drive the
page (a deck someone else drives, taking and handing over, publishing, deleting, bringing a
deck in and notifications while a page is open) are in TeamPageTests, deferred to here from
test_runner_team.py.
"""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.error
from dataclasses import replace
import urllib.request
from email.message import Message
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode

import helpers
from runner_support import FORM, StudioCase, TeamCase, asks

import computer
import home
import server
from runner import agents, engine as engines, page, settings
from runner.steps import deliver
from workspace import WorkspaceError

VERSION = (helpers.SKILL / 'VERSION').read_text().strip()
GETS = ('/api/capabilities', '/api/setup', '/api/agents', '/api/models', '/api/decks',
        '/api/run', '/api/slide', '/api/download', '/api/status', '/api/published',
        '/api/delete', '/api/file', '/api/computer')
POSTS = ('/api/setup/check', '/api/setup', '/api/decks', '/api/run', '/api/decide',
         '/api/answer', '/api/share', '/api/fetch', '/api/drive', '/api/publish',
         '/api/delete', '/api/bring', '/api/companions', '/api/upgrade', '/api/restart',
         '/api/versions', '/api/computer', '/api/brand', '/api/brand/install',
         '/api/shared', '/api/deliver')
BOTH = ('/api/setup', '/api/decks', '/api/run', '/api/delete', '/api/computer')
LISTED = [{'name': 'gpt-6-sol', 'label': 'GPT-6-Sol (gpt-6-sol)', 'family': None,
           'about': 'Previous generation workhorse model.', 'default_level': 'medium',
           'levels': ['low', 'medium', 'high', 'xhigh']}]
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
NOTES = b'# Notes\n\nCapacity holds with two.\n'


def never(*args, **kwargs):
    raise AssertionError('A test must never look at the real computer.')


def encoded(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


class Asking:
    """Asking a RunnerPage as the server would, with no socket."""

    PORT = 8765

    def ready_page(self):
        for patcher in (mock.patch.object(computer, 'run', never),
                        mock.patch.object(computer, 'reach', never)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.page = page.RunnerPage(self.PORT, self.engine)
        self.origin = f'http://127.0.0.1:{self.PORT}'

    def headers(self, token=True, host=None, origin=None, kind=None) -> Message:
        made = Message()
        made['Host'] = host or f'127.0.0.1:{self.PORT}'
        if token:
            made[server.TOKEN_HEADER] = self.page.token if token is True else token
        for name, value in (('Origin', origin), ('Content-Type', kind)):
            if value:
                made[name] = value
        return made

    def raw(self, method: str, target: str, body: bytes | None = None, **options):
        """One request: (status, kind, bytes, headers) or the refusal as JSON."""
        try:
            reply = self.page.answer(target, self.headers(**options), method, body)
        except server.Refusal as refusal:
            return (int(refusal.status), server.JSON,
                    json.dumps({'error': str(refusal)}).encode(), {'Allow': refusal.allow})
        except WorkspaceError as refusal:
            return 409, server.JSON, json.dumps({'error': str(refusal)}).encode(), {}
        status, kind, data, *extra = reply
        return int(status), kind, data, (extra[0] if extra else {})

    def answer(self, method: str, target: str, body: bytes | None = None, **options):
        status, kind, data, extra = self.raw(method, target, body, **options)
        self.assertEqual(kind, server.JSON)
        self.assertNotIn(b'<', data)
        return status, json.loads(data) if data else None, extra.get('Allow')

    def get(self, endpoint: str, expect: int = 200, **params):
        target = f'/api/{endpoint}' + (f'?{urlencode(params)}' if params else '')
        status, reply, _ = self.answer('GET', target)
        self.assertEqual(status, expect, reply)
        return reply

    def post(self, endpoint: str, sent, expect: int = 200, **options):
        """POST as the page does, unless `options` say otherwise."""
        options.setdefault('origin', self.origin)
        options.setdefault('kind', 'application/json')
        body = sent if isinstance(sent, (bytes, type(None))) else json.dumps(sent).encode()
        status, reply, _ = self.answer('POST', f'/api/{endpoint}', body, **options)
        self.assertEqual(status, expect, reply)
        return reply

    def started(self, uploads=None, **changes) -> str:
        sent = {'form': {**FORM, **changes}}
        if uploads:
            sent['uploads'] = {name: encoded(data) for name, data in uploads.items()}
        return self.post('decks', sent)['path']

    def run_of(self, path: str) -> dict:
        return self.get('run', path=path)

    def decided(self, path: str, gate: str | None = None, decision: str = 'approve',
                expect: int = 200, **more) -> dict:
        gate = gate or self.run_of(path)['gate']['name']
        if gate == 'gate:look' and decision == 'approve' and 'extra' not in more:
            more['extra'] = {'choice': self.run_of(path)['gate']['options'][0]['name']}
        return self.post('decide', {'path': path, 'gate': gate, 'decision': decision, **more},
                         expect)

    def on_disk(self) -> dict:
        return {path.relative_to(self.base).as_posix(): path.read_bytes()
                for path in sorted(self.base.rglob('*'))
                if path.is_file() and '.git' not in path.parts}


class PageCase(Asking, StudioCase):
    """The runner's page over a workspace on this computer."""

    def setUp(self):
        super().setUp()
        self.ready_page()


class CapabilityTests(PageCase):
    def test_the_runner_says_it_is_here(self):
        self.assertEqual(self.get('capabilities'), {'runner': True, 'version': VERSION})

    def test_every_address_is_listed_once_with_its_methods(self):
        self.assertEqual(set(self.page.reads), set(GETS))
        self.assertEqual(set(self.page.writes), set(POSTS))
        for target in GETS:
            self.assertEqual(self.page.allowed(target),
                             'GET, POST' if target in BOTH else 'GET', target)
        for target in POSTS:
            self.assertEqual(self.page.allowed(target),
                             'GET, POST' if target in BOTH else 'POST', target)


class RuleTests(PageCase):
    """The server's rules, on every address the runner adds."""

    def setUp(self):
        super().setUp()
        self.path = self.started()
        self.bodies = {target: {} for target in POSTS}
        self.bodies.update({
            '/api/setup/check': {'path': str(self.base / 'elsewhere')},
            '/api/setup': {'limits': {'parallel': 4}},
            '/api/decks': {'form': {**FORM, 'title': 'Health checks'}},
            '/api/run': {'path': self.path, 'action': 'stop'},
            '/api/decide': {'path': self.path, 'gate': 'gate:outline', 'decision': 'approve'},
            '/api/answer': {'path': self.path, 'id': 'x', 'answer': 'Yes.'},
            '/api/drive': {'path': self.path, 'action': 'take'},
            '/api/publish': {'path': self.path},
            '/api/deliver': {'path': self.path},
            '/api/delete': {'path': self.path, 'title': 'Rolling restarts'},
            '/api/bring': {'path': self.path},
            '/api/upgrade': {'version': '99.0.0'},
            '/api/versions': {'dismiss': 'presentation-studio 99.0.0'},
            '/api/brand': {'repository': str(self.base / 'brand.git')},
            '/api/brand/install': {'release': 'v1.2.0'},
            '/api/shared': {'seen': True}})
        self.reads = {target: target for target in GETS}
        self.reads.update({
            '/api/models': '/api/models?agent=claude',
            '/api/run': '/api/run?' + urlencode({'path': self.path}),
            '/api/slide': '/api/slide?' + urlencode({'path': self.path, 'kind': 'build',
                                                     'number': 1}),
            '/api/download': '/api/download?' + urlencode({'path': self.path}),
            '/api/delete': '/api/delete?' + urlencode({'path': self.path}),
            '/api/file': '/api/file?' + urlencode({'path': self.path, 'name': 'intake.md'})})
        self.before = self.on_disk()

    def refused(self, method: str, target: str, expect: int, **options) -> dict:
        if method == 'POST':
            body = json.dumps(self.bodies[target]).encode()
            options.setdefault('origin', self.origin)
            options.setdefault('kind', 'application/json')
        else:
            body, target = None, self.reads[target]
        status, reply, _ = self.answer(method, target, body, **options)
        self.assertEqual(status, expect, (target, reply))
        self.assertEqual(self.on_disk(), self.before, target)
        return reply

    def test_every_call_needs_the_key(self):
        for method, targets in (('GET', GETS), ('POST', POSTS)):
            for target in targets:
                with self.subTest(target=target, method=method):
                    for token in (False, 'not-the-key'):
                        said = self.refused(method, target, 403, token=token)
                        self.assertIn('needs the key', said['error'])

    def test_it_answers_only_at_its_own_local_address(self):
        for method, targets in (('GET', GETS), ('POST', POSTS)):
            for target in targets:
                with self.subTest(target=target, method=method):
                    said = self.refused(method, target, 403, host='example.com')
                    self.assertIn('only at its own local address', said['error'])

    def test_a_change_is_taken_only_from_the_page_itself(self):
        for target in POSTS:
            with self.subTest(target):
                for origin in ('', 'http://example.com', 'http://127.0.0.1:9999'):
                    said = self.refused('POST', target, 403, origin=origin)
                    self.assertIn('only from the page itself', said['error'])

    def test_a_change_is_taken_only_as_one_json_object_in_the_body(self):
        for target in POSTS:
            with self.subTest(target):
                self.refused('POST', target, 415, kind='application/x-www-form-urlencoded')
                status, said, _ = self.answer('POST', target, b'["a", "list"]',
                                              origin=self.origin, kind='application/json')
                self.assertEqual((status, said['error']),
                                 (400, 'Send the change as one JSON object.'))
                status, _, _ = self.answer('POST', target, None, origin=self.origin,
                                           kind='application/json')
                self.assertEqual(status, 413)
                status, _, _ = self.answer('POST', f'{target}?path=x', b'{}',
                                           origin=self.origin, kind='application/json')
                self.assertEqual(status, 400)
        self.assertEqual(self.on_disk(), self.before)

    def test_each_address_answers_only_its_own_methods(self):
        for target in set(GETS) - set(BOTH):
            status, _, allow = self.answer('POST', target, b'{}', origin=self.origin,
                                           kind='application/json')
            self.assertEqual((status, allow), (405, 'GET'), target)
        for target in set(POSTS) - set(BOTH):
            status, _, allow = self.answer('GET', target)
            self.assertEqual((status, allow), (405, 'POST'), target)
        for method in ('PUT', 'PATCH', 'DELETE'):
            status, _, allow = self.answer(method, '/api/run')
            self.assertEqual((status, allow), (405, 'GET, POST'))
        self.assertEqual(self.answer('GET', '/api/nothing')[0], 404)
        self.assertEqual(self.on_disk(), self.before)

    def test_only_a_decks_form_may_be_large_and_only_with_the_key(self):
        with_key, without = self.headers(), self.headers(token=False)
        self.assertEqual(self.page.body_limit('/api/decks', with_key), page.DECKS_LIMIT)
        self.assertEqual(page.DECKS_LIMIT, 120_000_000)
        self.assertEqual(self.page.body_limit('/api/decks', without), server.BODY_LIMIT)
        self.assertEqual(self.page.body_limit('/api/decks?x=1', with_key), page.DECKS_LIMIT)
        for target in set(POSTS) - {'/api/decks'}:
            self.assertEqual(self.page.body_limit(target, with_key), server.BODY_LIMIT, target)


class AgentTests(PageCase):
    def test_each_agent_says_whether_it_can_be_used_now(self):
        away = agents.Readiness('codex', True, None, False, '0.162', 'Codex is signed in but '
                                'cannot be used from this network. Try another network.')
        with mock.patch.object(self.engine.adapters['codex'], 'ready',
                               return_value=away) as looked:
            first = self.get('agents')
            self.assertEqual(self.get('agents'), first, 'a look is reused for a while')
            looked.assert_called_once_with()
        self.assertEqual(first['agents'][1], {
            'agent': 'codex', 'installed': True, 'signed_in': None, 'reachable': False,
            'version': '0.162', 'problem': away.problem})
        self.assertEqual(first['agents'][0]['agent'], 'claude')
        self.assertEqual(self.workers.jobs, [], 'looking starts no agent')

    def test_each_agents_models_are_listed_when_asked_and_kept(self):
        with mock.patch.object(self.engine.adapters['codex'], 'models', create=True,
                               return_value=agents.offered(LISTED)) as listed:
            first = self.get('models', agent='codex')
            self.assertEqual(self.get('models', agent='codex'), first, 'a list is kept')
            listed.assert_called_once_with()
        self.assertEqual((first['agent'], first['models'], first['problem']),
                         ('codex', LISTED, None))

    def test_models_are_asked_for_one_agent_this_runner_has(self):
        self.assertEqual(self.get('models', 400, agent='another')['error'],
                         'This runner has no agent called another.')
        self.assertEqual(self.get('models', 400)['error'], 'Give one agent.')


class StartTests(PageCase):
    def test_the_form_starts_a_deck_and_its_run_at_once(self):
        made = self.post('decks', {'form': FORM})
        root = self.space.deck('rolling-restarts')
        self.assertEqual(made, {'path': str(root), 'id': 'rolling-restarts'})
        run = self.run_of(made['path'])
        self.assertEqual((run['state'], run['gate']['name'], run['route']),
                         ('waiting', 'gate:outline', 'scratch'))
        listed = self.get('decks')
        self.assertEqual([item['id'] for item in listed['needs']], ['rolling-restarts'])
        self.assertEqual((listed['working'], listed['finished'], listed['elsewhere']),
                         ([], [], []))

    def test_an_upload_is_sent_in_base64_and_taken_in(self):
        path = self.started(uploads={'notes.md': NOTES}, route='document',
                            source={'kind': 'upload', 'name': 'notes.md'})
        gate = self.run_of(path)['gate']
        self.assertEqual((gate['name'], gate['documents'][0]['name']),
                         ('gate:classify', 'notes.md'))
        self.assertNotIn(encoded(NOTES), (Path(path) / 'run.json').read_text())

    def test_a_form_that_makes_no_sense_starts_nothing(self):
        for sent, said in (
                ({'form': {**FORM, 'title': ''}}, 'Give the deck a title.'),
                ({'form': {**FORM, 'route': 'nowhere'}}, 'Choose how to start'),
                ({'form': {**FORM, 'brand': 'another'}}, 'That brand is not one'),
                ({'form': {**FORM, 'output': 'keynote'}}, 'Choose an output'),
                ({'form': 'scratch'}, 'Send the form as one JSON object.'),
                ({}, 'Send the form as one JSON object.'),
                ({'form': FORM, 'uploads': ['notes.md']}, 'Send the uploads by their names.'),
                ({'form': FORM, 'uploads': {'notes.md': 'not base64!'}},
                 '"notes.md" did not arrive whole'),
                ({'form': FORM, 'uploads': {'notes.md': ''}}, '"notes.md" arrived empty')):
            with self.subTest(sent=sent):
                self.assertIn(said, self.post('decks', sent, 400)['error'])
        said = self.post('decks', {'form': {**FORM, 'route': 'document',
                                            'source': {'kind': 'upload',
                                                       'name': 'notes.md'}}}, 409)
        self.assertIn('"notes.md" was not sent with the form', said['error'])
        self.assertEqual((self.engine.every(), self.workers.jobs), ([], []))

    def test_a_deck_is_not_started_on_an_agent_that_cannot_be_used(self):
        away = agents.Readiness('claude', False, problem='Claude Code is not installed. '
                                'Install it and sign in, then try again.')
        with mock.patch.object(self.engine.adapters['claude'], 'ready', return_value=away):
            said = self.post('decks', {'form': FORM}, 409)
        self.assertEqual(said['error'], away.problem)
        self.assertEqual(self.engine.every(), [])


class RunTests(PageCase):
    def test_a_deck_goes_from_its_form_to_delivered_on_the_page(self):
        path = self.started()
        before = len(self.log())
        for gate in ('gate:outline', 'gate:look', 'gate:build'):
            self.assertEqual(self.run_of(path)['gate']['name'], gate)
            shown = self.decided(path, gate)
            self.assertNotEqual((shown['gate'] or {}).get('name'), gate)
        run = self.run_of(path)
        self.assertEqual(run['state'], 'finished')
        self.assertTrue(run['deliver']['download'])
        self.assertEqual([line for line in self.log()[before:] if ': approve the ' in line],
                         ['Rolling restarts: approve the outline',
                          'Rolling restarts: approve the look',
                          'Rolling restarts: approve the deck'])
        status, kind, data, extra = self.raw('GET', '/api/download?' + urlencode(
            {'path': path}))
        self.assertEqual((status, kind), (200, page.PPTX))
        self.assertTrue(data.startswith(b'PK\x03\x04'))
        self.assertEqual(extra, {'Content-Disposition':
                                 'attachment; filename="rolling-restarts.pptx"'})
        self.assertEqual(self.get('decks')['finished'][0]['id'], 'rolling-restarts')

    def test_a_slides_picture_is_only_what_the_engine_gives(self):
        path = self.started()
        self.decided(path, 'gate:outline')
        for query in ({'kind': 'look', 'number': '1'}, {'kind': 'look', 'name': 'Bold rule'}):
            status, kind, data, _ = self.raw('GET', '/api/slide?' + urlencode(
                {'path': path, **query}))
            self.assertEqual((status, kind), (200, 'image/png'), data[:200])
            self.assertTrue(data.startswith(b'\x89PNG'))
        self.decided(path, 'gate:look')
        for query in ({'kind': 'build', 'number': '2'},
                      {'kind': 'build', 'name': 'contact-sheet'}):
            status, kind, data, _ = self.raw('GET', '/api/slide?' + urlencode(
                {'path': path, **query}))
            self.assertEqual((status, kind, data[:4]), (200, 'image/png', b'\x89PNG'))
        for query, expect, said in (
                ({'kind': 'build', 'number': '99'}, 404, engines.NO_PICTURE),
                ({'kind': 'build', 'number': '-1'}, 400, 'Give number as a whole number.'),
                ({'kind': 'build', 'number': '1', 'name': 'x'}, 400, 'and not both'),
                ({'kind': 'build'}, 400, 'and not both'),
                ({'kind': 'secret', 'number': '1'}, 400, 'A picture is of the build'),
                ({'kind': 'look', 'name': '../../secret'}, 404, engines.NO_PICTURE)):
            with self.subTest(query=query):
                status, reply, _ = self.answer('GET', '/api/slide?' + urlencode(
                    {'path': path, **query}))
                self.assertEqual(status, expect, reply)
                self.assertIn(said, reply['error'])
        for elsewhere in (str(self.base), '/', str(Path(path) / 'work')):
            status, reply, _ = self.answer('GET', '/api/slide?' + urlencode(
                {'path': elsewhere, 'kind': 'build', 'number': '1'}))
            self.assertEqual((status, reply['error']), (404, page.NO_DECK))

    def test_a_deck_made_as_powerpoint_without_google_is_delivered_to_it_later(self):
        path = self.started()
        self.slides.run.drive = False
        for gate in ('gate:outline', 'gate:look', 'gate:build'):
            self.decided(path, gate)
        first = self.run_of(path)['deliver']
        self.assertEqual((first['output'], first['notice'], first['to_google']),
                         ('pptx', deliver.NOT_CONNECTED, True))
        before, commits = self.on_disk(), len(self.log())
        said = self.post('deliver', {'path': path}, 409)['error']
        self.assertEqual(said, engines.STILL_NOT_CONNECTED)
        self.assertEqual((self.on_disk(), len(self.log())), (before, commits))
        self.slides.run.drive = True
        shown = self.post('deliver', {'path': path})
        again = shown['deliver']
        self.assertEqual((again['output'], again['revision'], again['to_google']),
                         ('google', 2, False))
        self.assertTrue(again['url'].startswith('https://'))
        self.assertNotIn('notice', again)
        self.assertEqual(shown['state'], 'finished')
        self.assertEqual([one.get('url') is not None for one in again['revisions']],
                         [False, True])
        self.assertEqual(self.log()[-1], 'Rolling restarts: deliver revision 2 to Google Slides: '
                         + again['url'])
        # Once it is there, there is nothing more to send.
        self.assertIn('already', self.post('deliver', {'path': path}, 409)['error'])

    def test_a_deck_not_delivered_is_not_sent_to_google(self):
        path = self.started()
        self.assertIn('not been delivered', self.post('deliver', {'path': path}, 409)['error'])

    def test_a_deck_not_delivered_has_nothing_to_download(self):
        path = self.started()
        status, reply, _ = self.answer('GET', '/api/download?' + urlencode({'path': path}))
        self.assertEqual(status, 409, reply)

    def test_a_shared_file_is_read_by_name_and_nothing_else(self):
        path = self.started()
        shown = self.get('file', path=path, name='outline.md')
        self.assertEqual((shown['name'], shown['truncated']), ('outline.md', False))
        self.assertIn('Rolling restarts', shown['text'])
        self.assertIn('Platform teams', self.get('file', path=path, name='intake.md')['text'])
        self.assertIn('has not been written yet',
                      self.get('file', 404, path=path, name='research/report.md')['error'])
        for name in ('run.json', '../README.md', 'work/step.lock', '/etc/passwd',
                     'sources/incoming/upload', 'outline.json'):
            with self.subTest(name):
                self.assertIn('A file is one of', self.get('file', 400, path=path,
                                                           name=name)['error'])
        (Path(path) / 'look.md').symlink_to(self.base / 'gitconfig')
        self.assertIn('leads outside the deck folder',
                      self.get('file', 403, path=path, name='look.md')['error'])

    def test_a_decision_that_makes_no_sense_changes_nothing(self):
        path = self.started()
        before = self.on_disk()
        for sent, expect, said in (
                ({'gate': 'gate:nothing', 'decision': 'approve'}, 400, 'one of the gates'),
                ({'gate': 'gate:outline', 'decision': 'maybe'}, 400, 'to approve, or to ask'),
                ({'gate': 'gate:outline', 'decision': 'changes'}, 400,
                 'Say what should change.'),
                ({'gate': 'gate:outline', 'decision': 'changes', 'note': '  '}, 400,
                 'Say what should change.'),
                ({'gate': 'gate:outline', 'decision': 'approve', 'extra': ['x']}, 400,
                 'one JSON object'),
                ({'gate': 'gate:outline', 'decision': 'approve', 'note': 7}, 400,
                 'Give note as text.'),
                ({'gate': 'gate:look', 'decision': 'approve'}, 409,
                 'not waiting for a decision')):
            with self.subTest(sent=sent):
                said_now = self.post('decide', {'path': path, **sent}, expect)
                self.assertIn(said, said_now['error'])
        self.assertEqual(self.on_disk(), before)
        self.assertEqual(self.post('decide', {'path': str(self.base), 'gate': 'gate:outline',
                                              'decision': 'approve'}, 404)['error'],
                         page.NO_DECK)

    def test_changes_are_asked_for_with_a_note_and_the_step_runs_again(self):
        path = self.started()
        shown = self.decided(path, 'gate:outline', 'changes',
                             note='Make the objection its own section.')
        self.assertEqual((shown['gate']['name'], len(self.workers.of('outline'))),
                         ('gate:outline', 2))
        self.assertIn('Make the objection its own section.',
                      self.workers.of('outline')[-1].task)

    def test_a_run_can_be_paused_resumed_stopped_and_undone(self):
        path = self.started()
        self.assertIn('Only a deck that is working can be paused',
                      self.post('run', {'path': path, 'action': 'pause'}, 409)['error'])
        self.assertEqual(self.post('run', {'path': path, 'action': 'stop'})['state'], 'stopped')
        self.assertEqual(self.post('run', {'path': path, 'action': 'resume'})['state'],
                         'waiting')
        self.assertEqual(self.post('run', {'path': path, 'action': 'retry'}, 409)['error'],
                         'Nothing here failed, so there is nothing to try again.')
        self.assertIn('A run can be asked to',
                      self.post('run', {'path': path, 'action': 'explode'}, 400)['error'])
        self.assertEqual(self.post('run', {'path': '/', 'action': 'stop'}, 404)['error'],
                         page.NO_DECK)

    def test_a_workers_question_is_answered_on_the_page(self):
        self.workers.then('outline', asks('Which audience matters more?'))
        path = self.started()
        asked = self.run_of(path)['question']
        self.assertEqual(asked['text'], 'Which audience matters more?')
        self.assertEqual(self.post('answer', {'path': path, 'id': asked['id'],
                                              'answer': '  '}, 400)['error'],
                         'Write an answer first.')
        shown = self.post('answer', {'path': path, 'id': asked['id'],
                                     'answer': 'The operators.'})
        self.assertIsNone(shown['question'])
        self.assertEqual(shown['gate']['name'], 'gate:outline')
        self.assertIn('The operators.', self.workers.of('outline')[-1].task)
        self.assertEqual(self.post('answer', {'path': path, 'id': asked['id'],
                                              'answer': 'Again.'}, 409)['error'],
                         'That question is not waiting for an answer any more.')

    def test_reading_never_starts_or_wakes_a_run(self):
        path = self.started()
        jobs, log = len(self.workers.jobs), self.log()
        with mock.patch.object(self.engine, 'wake', never):
            for _ in range(3):
                self.run_of(path)
                self.get('decks')
                self.get('status')
                self.get('file', path=path, name='outline.md')
        self.assertEqual((len(self.workers.jobs), self.log()), (jobs, log))

    def test_every_request_tells_the_engine_a_page_is_open(self):
        self.assertFalse(self.engine.page_open())
        self.get('decks')
        self.assertTrue(self.engine.page_open())

    def test_the_status_screen_and_a_deletion(self):
        path = self.started()
        status = self.get('status')
        self.assertEqual([run['id'] for run in status['runs']], ['rolling-restarts'])
        leaving = self.get('delete', path=path)
        self.assertEqual((leaving['may'], leaving['title']), (True, 'Rolling restarts'))
        self.assertIn('not the title of this deck', self.post(
            'delete', {'path': path, 'title': 'Another'}, 409)['error'])
        gone = self.post('delete', {'path': path, 'title': 'Rolling restarts'})
        self.assertEqual((gone['deleted'], Path(path).exists()), (True, False))
        self.assertEqual(self.get('delete', 404, path=path)['error'], page.NO_DECK)

    def test_sharing_and_fetching_in_a_workspace_on_this_computer(self):
        self.assertEqual(self.post('fetch', {}), {'reached': None, 'received': 0,
                                                  'notice': None})
        self.assertEqual(self.post('drive', {'path': self.started(), 'action': 'take'},
                                   409)['error'], engines.NO_DRIVERS)


class BringTests(PageCase):
    def test_only_a_deck_this_computer_knows_is_brought_in(self):
        path = Path(self.started())
        outside = self.base / 'outside' / 'restarts'
        shutil.copytree(path, outside, ignore=shutil.ignore_patterns('work', 'sources'))
        said = self.post('bring', {'path': str(outside)}, 403)
        self.assertEqual(said['error'], 'That folder is not a deck this computer knows.')
        home.remember(outside, 'Rolling restarts')
        made = self.post('bring', {'path': str(outside)})
        self.assertEqual(made['id'], 'rolling-restarts-2')
        self.assertEqual(self.run_of(made['path'])['gate']['name'], 'gate:outline')
        self.assertTrue((outside / 'run.json').is_file(), 'the folder it came from is only read')


class Keeper:
    """A stand-in for what looks after the skills here: it records what it is asked."""

    def __init__(self):
        self.asked, self.refuse = [], None

    def report(self) -> dict:
        return {'stand_in': True}

    def again(self) -> None:
        self.asked.append('again')

    def close(self) -> None:
        pass

    def answer(self, *asked) -> dict:
        self.asked.append(asked)
        if self.refuse:
            raise WorkspaceError(self.refuse)
        return {'stand_in': True}

    def update(self, working: bool) -> dict:
        return self.answer('update', working)

    def upgrade(self, working: bool, version: str) -> dict:
        return self.answer('upgrade', working, version)

    def restart(self, working: bool) -> dict:
        return self.answer('restart', working)

    def dismiss(self, key: str) -> dict:
        return self.answer('dismiss', key)

    def install_brand(self, working: bool, release: str) -> dict:
        return self.answer('install_brand', working, release)

    def remember_brand(self, repository: str, listed: dict) -> None:
        self.asked.append(('remember_brand', repository, sorted(listed)))


class UpkeepTests(PageCase):
    def test_set_up_and_status_say_what_was_found_of_the_skills(self):
        self.assertEqual((self.get('setup')['upkeep'], self.get('status')['upkeep']),
                         (None, None))
        self.engine.upkeep = Keeper()
        self.assertEqual((self.get('setup')['upkeep'], self.get('status')['upkeep']),
                         ({'stand_in': True}, {'stand_in': True}))

    def test_what_looks_after_the_skills_is_asked_and_told_whether_a_deck_works(self):
        for endpoint, sent in (('companions', {}), ('upgrade', {'version': '99.0.0'}),
                               ('restart', {}), ('versions', {'dismiss': 'x 99.0.0'})):
            self.assertEqual(self.post(endpoint, sent, 409)['error'], page.NO_KEEPER)
        keeper = self.engine.upkeep = Keeper()
        self.assertEqual(self.post('upgrade', {}, 400)['error'], 'Give version as text.')
        self.assertEqual(self.post('versions', {'dismiss': 3}, 400)['error'],
                         'Give dismiss as text.')
        for endpoint, sent in (('companions', {}), ('upgrade', {'version': '99.0.0'}),
                               ('restart', {}), ('versions', {'dismiss': 'x 99.0.0'})):
            self.assertEqual(self.post(endpoint, sent), {'upkeep': {'stand_in': True}})
        keeper.refuse = 'A deck on this computer is working now.'
        self.assertEqual(self.post('companions', {}, 409)['error'], keeper.refuse)
        keeper.refuse, seen = None, []

        def looks(tools, job):
            seen.append(self.post('companions', {}))
            seen.append(self.post('restart', {}))
            self.workers.outline(tools, job)

        self.workers.then('outline', looks)
        self.started()
        self.assertEqual(keeper.asked, [
            ('update', False), ('upgrade', False, '99.0.0'), ('restart', False),
            ('dismiss', 'x 99.0.0'), ('update', False), ('update', True), ('restart', True)])

    def test_the_brand_skills_repository_is_kept_once_it_can_be_read(self):
        work, bare = self.base / 'brand-work', self.base / 'brand.git'
        for args in (('init', '-q', str(work)), ('init', '-q', '--bare', str(bare))):
            subprocess.run(['git', *args], cwd=self.base, check=True, capture_output=True)
        (work / 'SKILL.md').write_text('---\nname: acme-brand\n---\n')
        for args in (('add', '-A'), ('commit', '-q', '-m', 'Release'), ('tag', 'v1.2.0'),
                     ('tag', 'v2026.1.0'), ('push', '-q', '--tags', str(bare), 'HEAD:main')):
            subprocess.run(['git', '-c', 'user.name=A Test', '-c', 'user.email=t@example.com',
                            *args], cwd=work, check=True, capture_output=True)
        keeper = self.engine.upkeep = Keeper()
        said = self.post('brand', {'repository': str(self.base / 'nowhere.git')}, 400)
        self.assertTrue(said['error'].startswith("The brand skill's repository could not be "
                                                 'read. It was not found ('), said['error'])
        self.assertEqual(self.post('brand', {'repository': str(bare), 'release': 'v9.0.0'},
                                   400)['error'],
                         f'{bare} has no release v9.0.0. Its newest is v1.2.0. Leave the '
                         'release empty for the newest.')
        self.assertEqual(self.post('brand', {'release': 'v1.2.0'}, 400)['error'],
                         "A release is chosen from the brand skill's repository: give the "
                         'repository too.')
        self.assertIsNone(settings.load().brand_repository, 'nothing was kept')
        made = self.post('brand', {'repository': str(bare), 'release': '1.2.0'})
        self.assertEqual((made['brand']['repository'], made['brand']['release']),
                         (str(bare), 'v1.2.0'))
        self.assertEqual(settings.brand_source(), (str(bare), 'v1.2.0'))
        self.assertEqual(keeper.asked, [('remember_brand', str(bare), ['v1.2.0',
                                                                       'v2026.1.0'])])
        self.assertEqual(self.post('setup', {'limits': {'parallel': 3}})['brand']['repository'],
                         str(bare), 'a change to anything else leaves it as it was')
        cleared = self.post('brand', {'repository': ''})
        self.assertEqual((cleared['brand']['repository'], cleared['brand']['release']),
                         (None, None))

    def test_the_brand_skill_is_installed_only_when_asked_and_not_under_a_working_deck(self):
        self.assertEqual(self.post('brand/install', {'release': 'v1.2.0'}, 409)['error'],
                         page.NO_KEEPER)
        keeper = self.engine.upkeep = Keeper()
        self.assertEqual(self.post('brand/install', {}, 400)['error'],
                         'Give release as text.')
        self.assertEqual(self.post('brand/install', {'release': 'v1.2.0'}),
                         {'upkeep': {'stand_in': True}})
        keeper.refuse = 'The brand skill is being installed already.'
        self.assertEqual(self.post('brand/install', {'release': 'v1.2.0'}, 409)['error'],
                         keeper.refuse)
        keeper.refuse, seen = None, []

        def looks(tools, job):
            seen.append(self.post('brand/install', {'release': 'v1.2.0'}))
            self.workers.outline(tools, job)

        self.workers.then('outline', looks)
        self.started()
        self.assertEqual(keeper.asked, [('install_brand', False, 'v1.2.0'),
                                        ('install_brand', False, 'v1.2.0'),
                                        ('install_brand', True, 'v1.2.0')],
                         'a deck working in the background is said to be working')

    def test_checking_this_computer_again_looks_at_the_skills_and_what_a_deck_needs(self):
        keeper = self.engine.upkeep = Keeper()
        seen = {'checked_at': '2026-10-14T09:00:00Z', 'ready': True, 'assistants': ['Codex'],
                'wrong': [], 'items': []}
        with mock.patch.object(computer, 'check', lambda google=False: seen):
            self.assertEqual(self.get('computer'), {'computer': None})
            self.assertEqual(keeper.asked, [], 'reading the last look looks at nothing')
            looked = self.post('computer', {})['computer']
        self.assertEqual(keeper.asked, ['again'])
        names = [item['id'] for item in looked['items']]
        self.assertEqual(names, ['deck-slides', 'deck-brand', 'deck-previews',
                                 'deck-pictures', 'deck-research'])
        self.assertEqual(looked['ready'], not looked['wrong'])


class TeamPageTests(Asking, TeamCase):
    """A deck in a shared workspace, asked about on each person's own page."""

    def setUp(self):
        super().setUp()
        self.ready_page()
        self.blakes = page.RunnerPage(self.PORT, self.blake.engine)

    def as_blake(self, method: str, target: str, sent=None):
        """Ask Blake's page, as Blake."""
        with self.be(self.blake):
            mine, self.page = self.page, self.blakes
            try:
                headers = self.headers(origin=self.origin, kind='application/json')
                body = None if sent is None else json.dumps(sent).encode()
                try:
                    status, _, data = self.page.answer(target, headers, method, body)
                except server.Refusal as refusal:
                    return int(refusal.status), {'error': str(refusal)}
                except WorkspaceError as refusal:
                    return 409, {'error': str(refusal)}
                return int(status), json.loads(data)
            finally:
                self.page = mine

    def theirs_path(self, path: str) -> str:
        return str(self.theirs(self.blake, Path(path)))

    def shared_deck(self) -> str:
        with self.be(self.alex):
            path = self.started()
        self.as_blake('POST', '/api/fetch', {})
        return path

    def test_a_deck_someone_else_drives_is_read_and_refused_every_change(self):
        path = self.shared_deck()
        theirs = self.theirs_path(path)
        status, listed = self.as_blake('GET', '/api/decks')
        self.assertEqual([item['id'] for item in listed['elsewhere']], ['rolling-restarts'])
        status, run = self.as_blake('GET', '/api/run?' + urlencode({'path': theirs}))
        self.assertEqual((status, run['mine'], run['driver']['name']), (200, False, 'Alex'))
        for target, sent in (
                ('/api/decide', {'path': theirs, 'gate': 'gate:outline',
                                 'decision': 'approve'}),
                ('/api/run', {'path': theirs, 'action': 'stop'}),
                ('/api/answer', {'path': theirs, 'id': 'x', 'answer': 'Yes.'}),
                ('/api/publish', {'path': theirs})):
            with self.subTest(target):
                status, said = self.as_blake('POST', target, sent)
                self.assertEqual(status, 409, said)
                self.assertIn('Alex has been running this deck from another computer', said['error'])
        with self.be(self.alex):
            self.assertEqual(self.run_of(path)['gate']['name'], 'gate:outline')

    def test_a_deck_is_taken_over_and_handed_over_on_the_page(self):
        path = self.shared_deck()
        theirs = self.theirs_path(path)
        status, shown = self.as_blake('POST', '/api/drive', {'path': theirs, 'action': 'take'})
        self.assertEqual((status, shown['mine'], shown['driver']['name']), (200, True, 'Blake'))
        status, said = self.as_blake('POST', '/api/drive', {'path': theirs, 'action': 'fly'})
        self.assertEqual((status, said['error']), (400, 'A deck can be asked to: take, '
                                                        'hand-over.'))
        status, shown = self.as_blake('POST', '/api/drive', {'path': theirs,
                                                             'action': 'hand-over'})
        self.assertEqual((status, shown['driver']), (200, None))

    def test_a_deck_is_published_and_its_revisions_listed_on_the_page(self):
        with self.be(self.alex):
            path = self.started()
            made = self.post('publish', {'path': path})
            self.assertEqual((made['revision'], made['ready'], made['shared']), (1, False, True))
            listed = self.get('published')['published']
        self.assertEqual([(entry['id'], entry['revision']) for entry in listed],
                         [('rolling-restarts', 1)])
        self.assertEqual(self.tags(), ['presentations/rolling-restarts/r1'])

    def test_a_deck_is_deleted_on_the_page_and_the_deletion_shared(self):
        with self.be(self.alex):
            path = self.started()
            gone = self.post('delete', {'path': path, 'title': 'Rolling restarts'})
        self.assertEqual((gone['deleted'], gone['shared']), (True, True))
        self.assertIn('Rolling restarts: Alex deletes this deck', self.shared()[0])

    def test_a_deck_is_brought_in_on_the_page_and_taken(self):
        path = Path(self.shared_deck())
        outside = self.base / 'outside' / 'restarts'
        shutil.copytree(path, outside, ignore=shutil.ignore_patterns('work', 'sources'))
        with self.be(self.blake):
            home.remember(outside, 'Rolling restarts')
        status, made = self.as_blake('POST', '/api/bring', {'path': str(outside)})
        self.assertEqual((status, made['id']), (200, 'rolling-restarts-2'))
        status, run = self.as_blake('GET', '/api/run?' + urlencode({'path': made['path']}))
        self.assertEqual((run['driver']['name'], run['gate']['name']), ('Blake', 'gate:outline'))

    def test_nothing_is_told_through_the_computer_while_a_page_is_open(self):
        with self.be(self.alex):
            settings.save(replace(settings.load(), notify=True))
            self.started()
            self.get('decks')
            self.assertEqual(self.engine.tell(), [])
            with mock.patch.object(engines, 'PAGE_OPEN', 0):
                self.assertEqual(self.engine.tell(), ['Rolling restarts'])
        self.assertEqual(self.notifier.sent, ['Rolling restarts'])


class WireCase(StudioCase):
    """The runner's server on a port the system chose, serving a page of the test's own."""

    def setUp(self):
        super().setUp()
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.page_dir = Path(holder.name)
        for name in ('index.html', 'app.js', 'markdown.js', 'style.css'):
            (self.page_dir / name).write_text(f'/* {name} */\n', encoding='utf-8')
        for patcher in (mock.patch.object(computer, 'run', never),
                        mock.patch.object(computer, 'reach', never),
                        mock.patch.object(server, 'PAGE_DIR', self.page_dir)):
            patcher.start()
            self.addCleanup(patcher.stop)
        try:
            self.server = page.Studio(self.engine)
        except PermissionError as refused:
            self.skipTest(f'This environment does not allow listening on a local port: {refused}')
        self.addCleanup(self.server.stop)
        self.server.start()
        self.origin = f'http://127.0.0.1:{self.server.port}'

    def ask(self, target: str, sent=None, method: str | None = None, token: bool = True,
            **headers):
        headers = {name.replace('_', '-'): value for name, value in headers.items()}
        if token:
            headers[server.TOKEN_HEADER] = self.server.token
        body = None
        if sent is not None:
            body = sent if isinstance(sent, bytes) else json.dumps(sent).encode()
            headers = {'Origin': self.origin, 'Content-Type': 'application/json', **headers}
        request = urllib.request.Request(self.origin + target, data=body, headers=headers,
                                         method=method or ('POST' if body else 'GET'))
        try:
            with DIRECT.open(request, timeout=30) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as refused:
            with refused:
                return refused.code, refused.headers, refused.read()


class WireTests(WireCase):
    def test_the_page_and_the_runner_are_served_together(self):
        status, headers, body = self.ask('/', token=False)
        self.assertEqual((status, headers.get_content_type()), (200, 'text/html'))
        self.assertEqual(body, (self.page_dir / 'index.html').read_bytes())
        status, headers, body = self.ask('/api/capabilities')
        self.assertEqual((status, json.loads(body)), (200, {'runner': True,
                                                            'version': VERSION}))
        self.assertEqual(headers['Content-Security-Policy'],
                         "default-src 'self'; img-src 'self' blob:")
        self.assertEqual(self.ask('/api/capabilities', token=False)[0], 403)
        self.assertTrue(self.server.url.endswith(f'#token={self.server.token}'))

    def test_a_deck_is_started_decided_pictured_and_downloaded_over_the_wire(self):
        status, _, body = self.ask('/api/decks', {'form': FORM})
        self.assertEqual(status, 200, body)
        path = json.loads(body)['path']
        query = urlencode({'path': path})
        for gate in ('gate:outline', 'gate:look', 'gate:build'):
            run = json.loads(self.ask(f'/api/run?{query}')[2])
            self.assertEqual(run['gate']['name'], gate)
            extra = {'choice': run['gate']['options'][0]['name']} if gate == 'gate:look' \
                else None
            if gate == 'gate:build':
                status, headers, picture = self.ask('/api/slide?' + urlencode(
                    {'path': path, 'kind': 'build', 'number': 1}))
                self.assertEqual((status, headers.get_content_type()), (200, 'image/png'))
                self.assertTrue(picture.startswith(b'\x89PNG'))
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            status, _, body = self.ask('/api/decide', {'path': path, 'gate': gate,
                                                       'decision': 'approve', 'extra': extra})
            self.assertEqual(status, 200, body)
        status, headers, deck = self.ask(f'/api/download?{query}')
        self.assertEqual((status, headers.get_content_type()), (200, page.PPTX))
        self.assertEqual(headers['Content-Disposition'],
                         'attachment; filename="rolling-restarts.pptx"')
        self.assertEqual(headers['Content-Security-Policy'],
                         "default-src 'self'; img-src 'self' blob:")
        self.assertTrue(deck.startswith(b'PK\x03\x04'))

    def test_something_that_cannot_be_done_is_answered_with_a_sentence_and_409(self):
        path = json.loads(self.ask('/api/decks', {'form': FORM})[2])['path']
        status, _, body = self.ask('/api/run', {'path': path, 'action': 'retry'})
        self.assertEqual((status, json.loads(body)), (409, {
            'error': 'Nothing here failed, so there is nothing to try again.'}))

    def test_a_decks_form_is_the_only_long_body_and_only_with_the_key(self):
        large = os.urandom(300_000)
        sent = {'form': {**FORM, 'route': 'document',
                         'source': {'kind': 'upload', 'name': 'notes.md'}},
                'uploads': {'notes.md': encoded(NOTES + large.hex().encode())}}
        self.assertGreater(len(json.dumps(sent)), server.BODY_LIMIT)
        for label, expect, options in (
                ('no key', 403, {'token': False}),
                ('another origin', 403, {'Origin': 'http://example.com'}),
                ('a form', 415, {'Content_Type': 'application/x-www-form-urlencoded'}),
                ('another host', 403, {'Host': 'example.com'})):
            with self.subTest(label):
                try:
                    status, _, body = self.ask('/api/decks', sent, **options)
                except urllib.error.URLError as reset:
                    self.assertIsInstance(reset.reason, (ConnectionResetError, BrokenPipeError))
                    continue
                self.assertEqual(status, expect, body)
        self.assertEqual(self.engine.every(), [])
        status, _, body = self.ask('/api/decks', sent)
        self.assertEqual(status, 200, body[:300])
        path = json.loads(body)['path']
        for target in ('/api/answer', '/api/decide', '/api/run', '/api/setup'):
            try:
                status, _, body = self.ask(target, {'path': path, 'id': 'x' * 70_000})
            except urllib.error.URLError as reset:
                self.assertIsInstance(reset.reason, (ConnectionResetError, BrokenPipeError),
                                      target)
                continue
            self.assertEqual((status, json.loads(body)['error']), (413, 'A change is at most '
                             '64,000 bytes, with its length stated.'), target)

    def test_stopping_the_server_ends_the_engine(self):
        self.server.stop()
        self.assertTrue(self.engine._closing)


class LiveWireTests(WireCase):
    """The whole of it as the runner serves it: threads of its own, and a real connection."""

    BACKGROUND = True

    def run_of(self, path: str) -> dict:
        return json.loads(self.ask('/api/run?' + urlencode({'path': path}))[2])

    def until(self, path: str, check, seconds: float = 60) -> dict:
        deadline, run = time.monotonic() + seconds, None
        while time.monotonic() < deadline:
            run = self.run_of(path)
            if check(run):
                return run
            time.sleep(0.05)
        self.fail(f'It did not happen in time: {run}')

    def test_a_deck_goes_from_the_form_to_finished_on_the_page(self):
        status, _, body = self.ask('/api/decks', {'form': FORM})
        self.assertEqual(status, 200, body)
        path = json.loads(body)['path']
        for gate in ('gate:outline', 'gate:look', 'gate:build'):
            run = self.until(path, lambda run: run['state'] == 'waiting'
                             and (run['gate'] or {}).get('name') == gate)
            extra = {'choice': run['gate']['options'][0]['name']} if gate == 'gate:look' \
                else None
            status, _, body = self.ask('/api/decide', {'path': path, 'gate': gate,
                                                       'decision': 'approve', 'extra': extra})
            self.assertEqual(status, 200, body)
        done = self.until(path, lambda run: run['state'] == 'finished')
        self.assertTrue(done['deliver']['url'].startswith('https://'))
        self.until(path, lambda run: self.git('status', '--porcelain') == '')


if __name__ == '__main__':
    unittest.main()
