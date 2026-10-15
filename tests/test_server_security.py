"""The page server's rules, which every address the runner adds keeps: it answers on this
computer only, at its own address, with its key; it changes something only for a POST of one
JSON object from the page's own origin; a body is never read past its limit; and every answer,
refused or not, carries the same security headers and is JSON that no reader takes for markup.

Ported from Training Studio's tests/test_desk.py (RefusalTests, PageTests, WriteRuleTests,
WireTests, AnnounceTests). The page there read trainings; here a small page with one read and
one change of its own stands in for the runner's, so only the rules are tested. Classes on
SocketCase talk to a real server on a local port and are skipped where a port cannot be
opened. RuleCase asks the same questions without a socket.
"""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode, urlsplit

import helpers  # noqa: F401  keeps every test away from the real per-user files

import computer
import server
from workspace import WorkspaceError

PAGE_FILES = ('index.html', 'app.js', 'markdown.js', 'style.css')
SECURITY_HEADERS = {'Content-Security-Policy': "default-src 'self'; img-src 'self' blob:",
                    'X-Content-Type-Options': 'nosniff',
                    'X-Frame-Options': 'DENY',
                    'Referrer-Policy': 'no-referrer',
                    'Cache-Control': 'no-store'}
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def never(*args, **kwargs):
    raise AssertionError('A test must never look at the real computer.')


def ask(url: str, headers: dict | None = None, method: str = 'GET', body: bytes | None = None):
    """One request. Returns the status, the headers and the body, refused or not."""
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with DIRECT.open(request, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as refused:
        with refused:
            return refused.code, refused.headers, refused.read()


class Sample(server.Page):
    """A page with one read and one change of its own, standing in for the runner's."""
    reads = (*server.READS, '/api/sample')
    writes = (*server.WRITES, '/api/note')

    def __init__(self, port: int):
        super().__init__(port)
        self.notes = []

    def read(self, path: str, one):
        if path == '/api/sample':
            if one('what') == 'boom':
                raise RuntimeError('<b>boom</b>')
            if one('what') == 'refused':
                raise WorkspaceError('That cannot be done now.')
            return server.as_json(HTTPStatus.OK, {'what': one('what'), 'markup': '<i>x</i>'})
        return super().read(path, one)

    def write(self, path: str, sent: dict):
        if path == '/api/note':
            self.notes.append(server.text(sent, 'note'))
            return server.as_json(HTTPStatus.OK, {'notes': len(self.notes)})
        return super().write(path, sent)


class PageFolder(unittest.TestCase):
    """The page's own files, in a folder of the test's, and no look at the real computer."""

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.folder = Path(holder.name)
        for name in PAGE_FILES:
            (self.folder / name).write_text(f'/* {name} */\n', encoding='utf-8')
        for patcher in (mock.patch.object(server, 'PAGE_DIR', self.folder),
                        mock.patch.object(computer, 'run', never),
                        mock.patch.object(computer, 'reach', never)):
            patcher.start()
            self.addCleanup(patcher.stop)


class RuleCase(PageFolder):
    """The page's answers with no socket, so these run where a port cannot be opened."""

    PORT = 8765

    def setUp(self):
        super().setUp()
        self.page = Sample(self.PORT)
        self.origin = f'http://127.0.0.1:{self.PORT}'
        self.note = {'note': 'Hello.'}

    def headers(self, token=True, host=None, origin=None, kind=None) -> Message:
        made = Message()
        made['Host'] = host or f'127.0.0.1:{self.PORT}'
        if token:
            made[server.TOKEN_HEADER] = self.page.token if token is True else token
        for name, values in (('Origin', origin), ('Content-Type', kind)):
            for value in [values] if isinstance(values, str) else values or []:
                made[name] = value
        return made

    def answer(self, method: str, target: str, body: bytes | None = None, **options):
        try:
            status, _, data = self.page.answer(target, self.headers(**options), method, body)
        except server.Refusal as refusal:
            return int(refusal.status), {'error': str(refusal)}, refusal.allow
        self.assertNotIn(b'<', data)
        return int(status), json.loads(data) if data else None, None

    def post(self, sent, expect: int = 200, target: str = '/api/note', **options) -> dict:
        options.setdefault('origin', self.origin)
        options.setdefault('kind', 'application/json')
        body = sent if isinstance(sent, (bytes, type(None))) else json.dumps(sent).encode()
        status, reply, _ = self.answer('POST', target, body, **options)
        self.assertEqual(status, expect, reply)
        return reply

    def refused(self, expect: int, sent=None, **options) -> dict:
        reply = self.post(self.note if sent is None else sent, expect, **options)
        self.assertEqual(self.page.notes, [])
        return reply


class WriteRuleTests(RuleCase):
    def test_the_page_itself_is_answered(self):
        self.assertEqual(self.post(self.note), {'notes': 1})
        self.assertEqual(self.page.notes, ['Hello.'])

    def test_the_page_is_answered_at_localhost_too(self):
        host = f'localhost:{self.PORT}'
        self.post(self.note, host=host, origin=f'http://{host}')
        self.assertEqual(self.page.notes, ['Hello.'])

    def test_a_change_needs_the_key(self):
        for token in (False, 'wrong', self.page.token[:-1], self.page.token + 'x'):
            with self.subTest(token):
                self.assertIn('needs the key', self.refused(403, token=token)['error'])

    def test_a_change_needs_the_pages_own_origin(self):
        other_port = f'http://127.0.0.1:{self.PORT + 1}'
        for origin in (None, 'null', 'http://example.com', other_port,
                       f'https://127.0.0.1:{self.PORT}', f'http://localhost:{self.PORT}',
                       f'{self.origin}.example.com', f'{self.origin}/', 'http://127.0.0.1',
                       [self.origin, 'http://example.com'], [self.origin, self.origin]):
            with self.subTest(origin):
                self.assertEqual(self.refused(403, origin=origin),
                                 {'error': 'A change is accepted only from the page itself.'})

    def test_a_change_is_refused_at_any_other_address(self):
        for host in ('example.com', f'example.com:{self.PORT}', '127.0.0.1',
                     f'127.0.0.1.example.com:{self.PORT}', f'[::1]:{self.PORT}'):
            with self.subTest(host):
                refusal = self.refused(403, host=host, origin=f'http://{host}')
                self.assertIn('only at its own local address', refusal['error'])

    def test_a_change_is_json_in_the_body(self):
        for kind in (None, 'text/plain', 'application/x-www-form-urlencoded',
                     'multipart/form-data'):
            with self.subTest(kind):
                self.assertEqual(self.refused(415, kind=kind),
                                 {'error': 'Send the change as JSON.'})
        for body in (b'', b'{not json', b'[]', b'"note"', b'null', b'\xff\xfe',
                     urlencode(self.note).encode()):
            with self.subTest(body):
                self.assertIn('one JSON object', self.refused(400, body)['error'])

    def test_every_field_is_text(self):
        for value in (None, 7, '', ['Hello.'], {'a': 1}, 'x' * (server.NOTE_LIMIT + 1)):
            with self.subTest(value=str(value)[:20]):
                sent = {} if value is None else {'note': value}
                self.assertEqual(self.refused(400, sent), {'error': 'Give note as text.'})

    def test_a_body_that_is_too_long_or_has_no_length_is_never_read(self):
        refusal = self.post(None, 413)
        self.assertIn('64,000 bytes', refusal['error'])
        self.assertEqual(self.page.notes, [])

    def test_what_changes_is_never_named_in_the_address(self):
        status, reply, _ = self.answer('POST', f'/api/note?{urlencode(self.note)}', b'{}',
                                       origin=self.origin, kind='application/json')
        self.assertEqual((status, reply), (400, {'error': 'Send what is to change in the '
                                                          'body.'}))

    def test_a_change_is_never_made_with_get_and_a_read_never_with_post(self):
        for target in ('/api/note', f'/api/note?{urlencode(self.note)}'):
            with self.subTest(target):
                status, _, allow = self.answer('GET', target)
                self.assertEqual((status, allow), (405, 'POST'))
        for target in ('/', '/app.js', '/api/sample', '/api/nothing', '/api/note/'):
            with self.subTest(target):
                status, _, allow = self.answer('POST', target, b'{"note": "x"}',
                                               origin=self.origin, kind='application/json')
                self.assertEqual((status, allow), (405, 'GET'))
        self.assertEqual(self.page.notes, [])

    def test_each_address_answers_only_its_own_methods(self):
        self.assertEqual(self.page.allowed('/api/sample'), 'GET')
        self.assertEqual(self.page.allowed('/api/note?x=1'), 'POST')
        self.assertEqual(self.page.allowed('/api/computer'), 'GET, POST')
        self.assertEqual(self.page.allowed('/nothing'), 'GET')
        for method in ('PUT', 'PATCH', 'DELETE'):
            status, _, allow = self.answer(method, '/api/computer')
            self.assertEqual((status, allow), (405, 'GET, POST'))

    def test_a_read_needs_the_key_and_one_of_each_value(self):
        for token in (False, 'wrong'):
            status, said, _ = self.answer('GET', '/api/sample?what=x', token=token)
            self.assertEqual(status, 403)
            self.assertIn('needs the key', said['error'])
        for target in ('/api/sample', '/api/sample?what=', '/api/sample?what=a&what=b'):
            with self.subTest(target):
                status, said, _ = self.answer('GET', target)
                self.assertEqual((status, said), (400, {'error': 'Give one what.'}))
        self.assertEqual(self.answer('GET', '/api/sample?what=x')[:2],
                         (200, {'what': 'x', 'markup': '<i>x</i>'}))

    def test_the_key_is_taken_from_the_header_only(self):
        query = urlencode({'what': 'x', 'token': self.page.token,
                           server.TOKEN_HEADER: self.page.token})
        self.assertEqual(self.answer('GET', f'/api/sample?{query}', token=False)[0], 403)

    def test_a_large_body_is_only_for_an_address_that_says_so(self):
        self.assertEqual(self.page.body_limit('/api/note', self.headers()), server.BODY_LIMIT)
        self.assertEqual(server.BODY_LIMIT, 64_000)


class SocketCase(PageFolder):
    """A page serving on a port the system chose."""

    def setUp(self):
        super().setUp()
        try:
            self.desk = server.Desk(page=Sample)
        except PermissionError as refused:
            self.skipTest(f'This environment does not allow listening on a local port: {refused}')
        self.addCleanup(self.desk.stop)
        self.desk.start()
        self.origin = f'http://127.0.0.1:{self.desk.port}'
        self.targets = ('/api/sample?what=x', '/api/computer')

    def fetch(self, target: str, token=True, host: str | None = None, method: str = 'GET',
              body: bytes | None = None, headers: dict | None = None):
        headers = dict(headers or {})
        if token:
            headers[server.TOKEN_HEADER] = self.desk.token if token is True else token
        if host:
            headers['Host'] = host
        return ask(f'http://127.0.0.1:{self.desk.port}{target}', headers, method, body)

    def send(self, sent, expect: int = 200, target: str = '/api/note', **headers) -> dict:
        wanted = {'Origin': self.origin, 'Content-Type': 'application/json', **headers}
        body = sent if isinstance(sent, bytes) else json.dumps(sent).encode()
        status, replied, data = self.fetch(target, method='POST', body=body, headers=wanted)
        self.assertEqual(status, expect, data)
        self.assertEqual(replied.get_content_type(), 'application/json')
        return json.loads(data)

    def assert_refused(self, reply, status: int = 403) -> dict:
        code, headers, body = reply
        self.assertEqual(code, status, body)
        self.assertEqual(headers.get_content_type(), 'application/json')
        return json.loads(body)


class RefusalTests(SocketCase):
    def test_the_right_key_and_address_are_answered(self):
        for target in self.targets:
            self.assertEqual(self.fetch(target)[0], 200, target)
            self.assertEqual(self.fetch(target, host=f'localhost:{self.desk.port}')[0], 200)
            self.assertEqual(self.fetch(target, host=f'LOCALHOST:{self.desk.port}')[0], 200)

    def test_a_call_without_the_key_or_with_a_wrong_one_is_refused(self):
        for target in self.targets:
            self.assert_refused(self.fetch(target, token=False))
        for token in ('wrong', self.desk.token[:-1], self.desk.token + 'x',
                      self.desk.token.swapcase(), 'café'):
            with self.subTest(token):
                self.assert_refused(self.fetch(self.targets[0], token=token))

    def test_a_wrong_host_header_is_refused(self):
        port = self.desk.port
        for host in ('example.com', f'example.com:{port}', '127.0.0.1', 'localhost',
                     f'127.0.0.1:{port + 1}', f'127.0.0.1.example.com:{port}',
                     f'localhost.example.com:{port}', f'[::1]:{port}', f'0.0.0.0:{port}'):
            for target in ('/', '/app.js', *self.targets):
                with self.subTest(host=host, target=target):
                    said = self.assert_refused(self.fetch(target, host=host))
                    self.assertIn('only at its own local address', said['error'])

    def test_what_is_read_answers_get_only(self):
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD', 'TRACE', 'BREW'):
            for target in ('/', self.targets[0]):
                with self.subTest(method=method, target=target):
                    status, headers, _ = self.fetch(target, method=method)
                    self.assertIn(status, (405, 501))
                    if status == 405:
                        self.assertEqual(headers['Allow'], 'GET')

    def test_another_site_is_given_no_way_to_read_an_answer(self):
        self.assertEqual(self.fetch(self.targets[0], method='OPTIONS')[0], 405)
        status, headers, _ = self.fetch('/api/note', method='OPTIONS', token=False, headers={
            'Origin': 'http://example.com', 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-presentation-studio-token'})
        self.assertEqual(status, 405)
        for target in ('/', *self.targets):
            names = [name.lower() for name in self.fetch(target)[1]]
            self.assertFalse([name for name in names if name.startswith('access-control')])
        self.assertFalse([name for name in headers if name.lower().startswith('access-control')])

    def test_the_security_headers_are_on_every_response(self):
        replies = {
            'the page': self.fetch('/', token=False),
            'the script': self.fetch('/app.js', token=False),
            'the styles': self.fetch('/style.css', token=False),
            'the icon': self.fetch('/favicon.ico', token=False),
            'a read': self.fetch(self.targets[0]),
            'no token': self.fetch(self.targets[0], token=False),
            'wrong host': self.fetch('/', host='example.com'),
            'not found': self.fetch('/nothing'),
            'no such endpoint': self.fetch('/api/nothing'),
            'missing parameter': self.fetch('/api/sample'),
            'refused': self.fetch('/api/sample?what=refused'),
            'post': self.fetch(self.targets[0], method='POST'),
            'head': self.fetch('/', method='HEAD'),
            'unknown method': self.fetch('/', method='BREW'),
        }
        expected = {'the page': 200, 'the script': 200, 'the styles': 200, 'the icon': 204,
                    'a read': 200, 'no token': 403, 'wrong host': 403, 'not found': 404,
                    'no such endpoint': 404, 'missing parameter': 400, 'refused': 409,
                    'post': 405, 'head': 405, 'unknown method': 501}
        for label, (status, headers, _) in replies.items():
            with self.subTest(label):
                self.assertEqual(status, expected[label])
                for name, value in SECURITY_HEADERS.items():
                    self.assertEqual(headers.get_all(name), [value])
                self.assertNotIn('Python', headers.get('Server', ''))

    def test_markup_never_leaves_as_itself(self):
        status, _, body = self.fetch(self.targets[0])
        self.assertEqual(status, 200)
        self.assertNotIn(b'<', body)
        self.assertEqual(json.loads(body)['markup'], '<i>x</i>')

    def test_a_failure_inside_is_answered_as_json_with_the_headers(self):
        status, headers, body = self.fetch('/api/sample?what=boom')
        self.assertEqual((status, headers.get_content_type()), (500, 'application/json'))
        self.assertEqual(json.loads(body), {'error': 'RuntimeError: <b>boom</b>'})
        self.assertNotIn(b'<', body)
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')


class PageTests(SocketCase):
    def test_the_page_and_its_files_are_served_without_a_key(self):
        for target, name, kind in (('/', 'index.html', 'text/html'),
                                   ('/index.html', 'index.html', 'text/html'),
                                   ('/app.js', 'app.js', 'text/javascript'),
                                   ('/markdown.js', 'markdown.js', 'text/javascript'),
                                   ('/style.css', 'style.css', 'text/css')):
            with self.subTest(target):
                status, headers, body = self.fetch(target, token=False)
                self.assertEqual((status, headers.get_content_type()), (200, kind))
                self.assertEqual(headers.get_content_charset(), 'utf-8')
                self.assertEqual(body, (self.folder / name).read_bytes())

    def test_a_page_file_that_is_not_there_is_not_found(self):
        (self.folder / 'app.js').unlink()
        said = self.assert_refused(self.fetch('/app.js', token=False), 404)
        self.assertEqual(said, {'error': 'Nothing is served here.'})

    def test_nothing_else_beside_the_page_is_served(self):
        for target in ('/server.py', '/home.py', '/../server.py', '/desk/../server.py',
                       '/%2e%2e/server.py', '/..%2fserver.py', '/index.html/../../server.py',
                       '/desk/index.html', '/app.js/', '/api', '/api/', '/api/sample/',
                       '/api/../server.py'):
            with self.subTest(target):
                status, _, body = self.fetch(target)
                self.assertEqual(status, 404, body)
                self.assertEqual(json.loads(body), {'error': 'Nothing is served here.'})

    def test_the_link_carries_the_key_in_its_fragment_only(self):
        url = urlsplit(self.desk.url)
        self.assertEqual((url.scheme, url.hostname, url.port, url.path, url.query),
                         ('http', '127.0.0.1', self.desk.port, '/', ''))
        self.assertEqual(url.fragment, f'token={self.desk.token}')
        self.assertRegex(self.desk.token, r'^[A-Za-z0-9_-]{32,}$')
        self.assertNotIn(self.desk.token, self.desk.address)

    def test_each_server_makes_its_own_key(self):
        other = server.Desk(page=Sample)
        self.addCleanup(other.stop)
        self.assertNotEqual(other.token, self.desk.token)
        self.assertNotEqual(other.port, self.desk.port)

    def test_it_listens_on_this_computer_only(self):
        self.assertEqual(self.desk.server.server_address[0], '127.0.0.1')

    def test_a_stopped_server_no_longer_answers(self):
        self.desk.stop()
        with self.assertRaises(urllib.error.URLError):
            self.fetch('/')


class WireTests(SocketCase):
    def test_a_change_from_the_page_is_made(self):
        self.assertEqual(self.send({'note': 'Hello.'}), {'notes': 1})
        self.assertEqual(self.desk.page.notes, ['Hello.'])

    def test_a_change_without_the_key_the_origin_or_json_is_refused(self):
        body = json.dumps({'note': 'Hello.'}).encode()
        json_kind = {'Content-Type': 'application/json'}
        for label, expect, options in (
                ('no key', 403, {'token': False, 'headers': {**json_kind,
                                                             'Origin': self.origin}}),
                ('no origin', 403, {'headers': json_kind}),
                ('another origin', 403, {'headers': {**json_kind,
                                                     'Origin': 'http://example.com'}}),
                ('a form', 415, {'headers': {
                    'Origin': self.origin, 'Content-Type': 'application/x-www-form-urlencoded'}}),
                ('another host', 403, {'host': 'example.com',
                                       'headers': {**json_kind, 'Origin': self.origin}})):
            with self.subTest(label):
                status, headers, data = self.fetch('/api/note', method='POST', body=body,
                                                   **options)
                self.assertEqual(status, expect, data)
                self.assertEqual(headers.get_content_type(), 'application/json')
                for name, value in SECURITY_HEADERS.items():
                    self.assertEqual(headers.get_all(name), [value])
        self.assertEqual(self.desk.page.notes, [])

    def test_a_body_that_is_too_long_is_refused_unread(self):
        long = json.dumps({'note': 'x' * server.BODY_LIMIT}).encode()
        refusal = self.send(long, 413)
        self.assertIn('64,000 bytes', refusal['error'])
        self.assertEqual(self.desk.page.notes, [])

    def test_every_other_method_is_still_refused(self):
        body = json.dumps({'note': 'Hello.'}).encode()
        headers = {'Origin': self.origin, 'Content-Type': 'application/json'}
        for method in ('PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD', 'TRACE'):
            for target, allow in (('/api/note', 'POST'), ('/api/computer', 'GET, POST'),
                                  ('/api/sample', 'GET')):
                with self.subTest(method=method, target=target):
                    status, replied, _ = self.fetch(target, method=method, body=body,
                                                    headers=headers)
                    self.assertEqual((status, replied['Allow']), (405, allow))
        self.assertEqual(self.desk.page.notes, [])

    def test_the_computer_is_looked_at_only_when_asked(self):
        with mock.patch.object(computer, 'check', return_value={'ready': True}) as looked:
            self.assertEqual(json.loads(self.fetch('/api/computer')[2]), {'computer': None})
            self.assertEqual(self.send({}, target='/api/computer'),
                             {'computer': {'ready': True}})
            self.assertEqual(json.loads(self.fetch('/api/computer')[2]),
                             {'computer': {'ready': True}})
        looked.assert_called_once_with(google=True)


class AnnounceTests(unittest.TestCase):
    """What `studio serve` prints, and to whom."""

    class Server:
        address = 'http://127.0.0.1:4321/'
        url = 'http://127.0.0.1:4321/#token=the-key-only-a-person-may-hold'

    def test_a_terminal_is_given_the_link_whole_and_nothing_is_opened(self):
        printed = server.announce(self.Server, True, opener=never)
        self.assertEqual(printed, {'url': self.Server.url})

    def test_anything_else_is_given_the_address_without_its_key(self):
        opened = []
        printed = server.announce(self.Server, False,
                                  opener=lambda url: opened.append(url) or True)
        self.assertEqual(printed, {'address': 'http://127.0.0.1:4321/', 'opened': True,
                                   'note': server.NOT_A_PERSON})
        self.assertEqual(opened, [self.Server.url])
        self.assertNotIn('the-key', json.dumps(printed))
        self.assertNotIn('token', json.dumps(printed))
        self.assertIn('run this command in a terminal of your own', printed['note'])

    def test_where_no_browser_can_be_opened_it_says_so(self):
        printed = server.announce(self.Server, False, opener=lambda url: False)
        self.assertEqual((printed['opened'], printed['address']),
                         (False, 'http://127.0.0.1:4321/'))
        with mock.patch.dict(os.environ, {'BROWSER': 'a-browser'}):
            with mock.patch.object(server.webbrowser, 'open',
                                   side_effect=RuntimeError('none')):
                self.assertFalse(server.show(self.Server.url))
            with mock.patch.object(server.webbrowser, 'open', return_value=True) as opened:
                self.assertTrue(server.show(self.Server.url))
            opened.assert_called_once_with(self.Server.url)

    def test_with_no_screen_no_browser_is_started_at_all(self):
        without = {name: value for name, value in os.environ.items()
                   if name not in ('BROWSER', 'DISPLAY', 'WAYLAND_DISPLAY')}
        with mock.patch.dict(os.environ, without, clear=True), \
                mock.patch.object(server.sys, 'platform', 'linux'), \
                mock.patch.object(server.webbrowser, 'open', never):
            self.assertFalse(server.show(self.Server.url))
            self.assertFalse(server.announce(self.Server, False)['opened'])

    def test_a_port_is_a_number_a_port_can_be(self):
        self.assertEqual((server.port('0'), server.port('65535')), (0, 65535))
        for text in ('-1', '65536', 'http'):
            with self.subTest(text), self.assertRaises(ValueError):
                server.port(text)


if __name__ == '__main__':
    unittest.main()
