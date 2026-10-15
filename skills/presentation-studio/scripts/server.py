"""The page's server: the rules every address keeps, and nothing about decks.

What a caller needs to know
---------------------------
    desk = server.Desk(port, page=MyPage)   # MyPage subclasses Page and is given the port
    desk.url                                # the link, with its key; for a person only
    desk.start(); desk.stop()               # on a thread; or desk.serve() until interrupted
    print(json.dumps(server.announce(desk, sys.stdout.isatty())))

- It answers on 127.0.0.1 only, and only to a request whose `Host` is its own address. Every
  call but the page's own files needs the key, sent in the X-Presentation-Studio-Token
  header and never in the address. Reading is GET. A change is a POST of one JSON object,
  from the page's own origin, with nothing in its address but the path, and a body no
  longer than `body_limit` says: a longer one, or one whose length is not stated, is never
  read.
- Every answer, refused or not, is JSON (or one of the page's files, or a picture or a
  file an address of a subclass sends), carries SECURITY_HEADERS, and never holds "<" as
  itself. A refusal is {"error": "<a sentence for a person>"}; a WorkspaceError raised
  while answering is 409, and anything else 500.
- `Page` holds the key and every rule, in `answer` and `change`. A program that serves more
  behind the page makes a subclass: it adds addresses to `reads` and `writes`, answers them
  in `read` and `write`, may let one address of its own carry a larger body through
  `body_limit`, and never loosens a rule. `read` and `write` may answer (status, kind,
  bytes) or (status, kind, bytes, headers), the last a dict of headers such as
  Content-Disposition.
- Ported from Training Studio's desk.py, keeping its security base only: `Refusal`,
  `as_json`, `Server`, `Handler`, `Page` and `Desk`, with the `/api/computer` look at this
  computer. The training reads are gone. `announce`, `show`, `port` and `interrupt` come
  from its cmd_desk.py, for `studio serve`.
"""
from __future__ import annotations

import json
import os
import secrets
import socketserver
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import computer
from workspace import WorkspaceError

HOST = '127.0.0.1'
TOKEN_HEADER = 'X-Presentation-Studio-Token'
PAGE_DIR = Path(__file__).resolve().parent / 'desk'
PAGE = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/markdown.js': ('markdown.js', 'text/javascript; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
    '/deck.css': ('deck.css', 'text/css; charset=utf-8'),
}
JSON = 'application/json; charset=utf-8'
SECURITY_HEADERS = {
    'Content-Security-Policy': "default-src 'self'; img-src 'self' blob:",
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'Cache-Control': 'no-store',
}
BODY_LIMIT = 64_000      # bytes a POST may carry
NOTE_LIMIT = 10_000      # characters in one text field
COMPUTER_CACHE = 60      # seconds a look at this computer is reused
READS = ('/api/computer',)
WRITES = ('/api/computer',)
NOT_A_PERSON = ('The link that opens the page carries its key, and the key is shown only to a '
                'person. To get the link, run this command in a terminal of your own.')


class Refusal(Exception):
    """A request the page will not answer, with the HTTP status to refuse it with."""

    def __init__(self, status: int, message: str, allow: str | None = None):
        super().__init__(message)
        self.status = status
        self.allow = allow


def describe(failure: Exception) -> str:
    """An error as a sentence: a refusal's own, else its kind and what it said."""
    if isinstance(failure, (WorkspaceError, Refusal)):
        return str(failure)
    return f'{type(failure).__name__}: {failure}'


def as_json(status: int, value) -> tuple[int, str, bytes]:
    # "<" never leaves as itself, so no reader can take an answer for markup.
    text = json.dumps(value, sort_keys=True).replace('<', '\\u003c')
    return status, JSON, text.encode('utf-8')


def allowed(target: str, reads=READS, writes=WRITES) -> str:
    """The methods an address answers, for the `Allow` header of a refusal."""
    path = target.partition('?')[0]
    methods = [method for method, paths in (('GET', (*PAGE, *reads)), ('POST', writes))
               if path in paths]
    return ', '.join(methods) or 'GET'


def text(sent: dict, name: str, needed: bool = True) -> str | None:
    """One field of a change, which must be text of a sensible length."""
    value = sent.get(name)
    if value is None and not needed:
        return None
    if not isinstance(value, str) or (needed and not value) or len(value) > NOTE_LIMIT:
        raise Refusal(HTTPStatus.BAD_REQUEST, f'Give {name} as text.')
    return value


# --- the command's words ---------------------------------------------------------------

def interrupt(*_):
    raise KeyboardInterrupt


def port(text: str) -> int:
    number = int(text)
    if not 0 <= number <= 65535:
        raise ValueError(text)
    return number


def has_a_screen() -> bool:
    """Whether a browser with a window can be expected. A text browser is never started:
    it would take over the output the command is printing to."""
    return (sys.platform in ('darwin', 'win32')
            or any(os.environ.get(name) for name in ('BROWSER', 'DISPLAY', 'WAYLAND_DISPLAY')))


def show(url: str) -> bool:
    """Open the page in the default browser. False if there is none to open it in."""
    if not has_a_screen():
        return False
    try:
        return bool(webbrowser.open(url))
    except Exception:  # no browser after all: the person runs the command themselves
        return False


def announce(desk, to_a_person: bool, opener=show) -> dict:
    """What the command prints, once. A terminal is a person and is given the link, whole.

    Anything else, an assistant or a pipe, is given the address without its key. The page is
    then opened in the browser instead, so that only the person ever holds the key.
    """
    if to_a_person:
        return {'url': desk.url}
    return {'address': desk.address, 'opened': opener(desk.url), 'note': NOT_A_PERSON}


# --- the server ------------------------------------------------------------------------

class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        """A reader that hangs up early gets no traceback: the command's output stays one line."""

    def server_bind(self):
        # The base class looks its own name up, which can ask the network. Nothing here does.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class Handler(BaseHTTPRequestHandler):
    timeout = 30  # seconds a connection may sit idle before it is dropped

    def version_string(self):
        return 'PresentationStudio'

    def respond(self, body: bytes | None = None):
        allow, extra = None, None
        try:
            reply = self.server.desk.answer(self.path, self.headers, self.command, body)
        except Refusal as refusal:
            reply, allow = as_json(refusal.status, {'error': str(refusal)}), refusal.allow
        except WorkspaceError as refusal:
            reply = as_json(HTTPStatus.CONFLICT, {'error': str(refusal)})
        except Exception as failure:  # answered like any other, never a dropped connection
            reply = as_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': describe(failure)})
        if len(reply) == 4:
            *reply, extra = reply
        self.reply(*reply, allow=allow, extra=extra)

    def do_GET(self):
        self.respond()

    def do_POST(self):
        """Read the body, up to the limit, and hand it over. A body that is too long, or
        whose length is not stated, is never read: the request is refused and the line closed."""
        length = self.headers.get('Content-Length', '')
        limit = self.server.desk.page.body_limit(self.path, self.headers)
        if not length.isdigit() or int(length) > limit:
            self.close_connection = True
            return self.respond(None)
        self.respond(self.rfile.read(int(length)))

    def refuse_method(self):
        allow = self.server.desk.page.allowed(self.path)
        self.close_connection = True
        self.reply(*as_json(HTTPStatus.METHOD_NOT_ALLOWED,
                            {'error': 'The page reads with GET and sends a change with POST. '
                                      'Nothing else is answered.'}), allow=allow)

    do_HEAD = do_PUT = do_PATCH = do_DELETE = refuse_method
    do_OPTIONS = do_TRACE = do_CONNECT = refuse_method

    def reply(self, status: int, kind: str | None, body: bytes, allow: str | None = None,
              extra: dict | None = None):
        self.send_response(status)
        if kind:
            self.send_header('Content-Type', kind)
        if allow:
            self.send_header('Allow', allow)
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def end_headers(self):
        """Every response leaves through here, so every response carries these."""
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def send_error(self, code, message=None, explain=None):
        """The base class's own refusals, as JSON like the rest rather than as a page."""
        self.close_connection = True
        self.reply(*as_json(code, {'error': message or HTTPStatus(code).phrase}))

    def log_message(self, format, *args):
        """Nothing is logged: the command's output is one line, and stays one line."""


class Page:
    """What the page may ask for and what it is refused. It holds the key; it has no socket.

    A program that serves the page with more behind it makes a subclass: it adds addresses
    to `reads` and `writes` and answers them in `read` and `write`. Every rule about who may
    ask stays here, in `answer` and `change`.
    """
    reads, writes = READS, WRITES

    def __init__(self, port: int):
        self.token = secrets.token_urlsafe(32)
        self.port = port
        self.hosts = {f'{name}:{port}' for name in (HOST, 'localhost')}
        self._looking = threading.Lock()
        self._looked: tuple[float, dict] | None = None

    def uses_google(self) -> bool:
        """Whether Google matters here, so that its command line is not optional. A deck is
        made in Google Slides unless chosen otherwise."""
        return True

    def computer(self, look: bool) -> dict | None:
        """The last look at this computer. `look` takes a new one unless one was just taken."""
        if look:
            with self._looking:
                seen = self._looked
                if not seen or time.monotonic() - seen[0] >= COMPUTER_CACHE:
                    self._looked = (time.monotonic(), computer.check(google=self.uses_google()))
        return self._looked[1] if self._looked else None

    def answer(self, target: str, headers, method: str = 'GET',
               body: bytes | None = None) -> tuple:
        """Answer one request, or raise the refusal."""
        hosts = headers.get_all('Host') or []
        if len(hosts) != 1 or hosts[0].strip().lower() not in self.hosts:
            raise Refusal(HTTPStatus.FORBIDDEN, 'The page answers only at its own local address.')
        try:
            url = urlsplit(target)
        except ValueError:
            raise Refusal(HTTPStatus.BAD_REQUEST, 'That address cannot be read.')
        if method == 'POST':
            return self.change(url, hosts[0].strip().lower(), headers, body)
        if method != 'GET':
            raise Refusal(HTTPStatus.METHOD_NOT_ALLOWED, 'Nothing else is answered.',
                          self.allowed(url.path))
        if url.path in PAGE:
            name, kind = PAGE[url.path]
            try:
                return HTTPStatus.OK, kind, (PAGE_DIR / name).read_bytes()
            except OSError:
                raise Refusal(HTTPStatus.NOT_FOUND, 'Nothing is served here.')
        if url.path == '/favicon.ico':
            return HTTPStatus.NO_CONTENT, None, b''
        if url.path not in self.reads:
            if url.path in self.writes:
                raise Refusal(HTTPStatus.METHOD_NOT_ALLOWED,
                              'This is sent with POST, from the page.', self.allowed(url.path))
            raise Refusal(HTTPStatus.NOT_FOUND, 'Nothing is served here.')
        self.check_token(headers)
        query = parse_qs(url.query, keep_blank_values=True)

        def one(name: str) -> str:
            values = query.get(name, [])
            if len(values) != 1 or not values[0]:
                raise Refusal(HTTPStatus.BAD_REQUEST, f'Give one {name}.')
            return values[0]

        return self.read(url.path, one)

    def allowed(self, target: str) -> str:
        return allowed(target, self.reads, self.writes)

    def body_limit(self, target: str, headers) -> int:
        """The most bytes a POST to this address may carry. A subclass may let one address
        of its own carry more; nothing else about a request depends on this."""
        return BODY_LIMIT

    def read(self, path: str, one) -> tuple:
        """Answer one GET that passed every rule. `one(name)` is a query value."""
        return as_json(HTTPStatus.OK, {'computer': self.computer(look=False)})

    def check_token(self, headers) -> None:
        supplied = headers.get(TOKEN_HEADER, '')
        if not secrets.compare_digest(supplied.encode('utf-8'), self.token.encode('utf-8')):
            raise Refusal(HTTPStatus.FORBIDDEN, 'This needs the key from the link the page '
                                                'was opened with.')

    def change(self, url, host: str, headers, body: bytes | None) -> tuple:
        """Answer one POST, once it has passed every rule."""
        if url.path not in self.writes:
            raise Refusal(HTTPStatus.METHOD_NOT_ALLOWED, 'This is read with GET.',
                          self.allowed(url.path))
        self.check_token(headers)
        origins = headers.get_all('Origin') or []
        if len(origins) != 1 or origins[0].strip().lower() != f'http://{host}':
            raise Refusal(HTTPStatus.FORBIDDEN, 'A change is accepted only from the page itself.')
        if url.query:
            raise Refusal(HTTPStatus.BAD_REQUEST, 'Send what is to change in the body.')
        if headers.get_content_type() != 'application/json':
            raise Refusal(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, 'Send the change as JSON.')
        if body is None:
            limit = self.body_limit(url.path, headers)
            raise Refusal(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                          f'A change is at most {limit:,} bytes, with its length stated.')
        try:
            sent = json.loads(body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            sent = None
        if not isinstance(sent, dict):
            raise Refusal(HTTPStatus.BAD_REQUEST, 'Send the change as one JSON object.')
        return self.write(url.path, sent)

    def write(self, path: str, sent: dict) -> tuple:
        """Answer one POST that passed every rule. `sent` is its JSON object."""
        return as_json(HTTPStatus.OK, {'computer': self.computer(look=True)})


class Desk:
    """The page's server. `start` serves on a thread, `serve` blocks, `stop` ends either.

    `page` makes what answers: Page here, or a subclass of it given the port.
    """

    def __init__(self, port: int = 0, page=Page):
        self.server = Server((HOST, port), Handler)
        self.server.desk = self
        self.port = self.server.server_address[1]
        self.page = page(self.port)
        self.token, self.hosts, self.answer = self.page.token, self.page.hosts, self.page.answer
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> str:
        """Where the page is, without its key."""
        return f'http://{HOST}:{self.port}/'

    @property
    def url(self) -> str:
        """The link for the person. The key rides in the fragment, which is never sent."""
        return f'{self.address}#token={self.token}'

    def serve(self) -> None:
        self.server.serve_forever()

    def start(self) -> None:
        self._thread = threading.Thread(target=self.server.serve_forever, args=(0.05,),
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self.server.shutdown()
            self._thread.join()
            self._thread = None
        self.server.server_close()
