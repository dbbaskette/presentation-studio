"""The runner's server: the page, with the engine behind it.

What a caller needs to know
---------------------------
    server = page.Studio(engine, port)    # the page's server, answering for the runner
    server.url                            # the link, with its key; for a person only
    server.serve()                        # until interrupted; server.stop() ends the engine

- It keeps every rule of `server.Page`: it answers on the local machine only, checks the
  `Host` header, needs the key (X-Presentation-Studio-Token) for every call, and takes a
  change only as a POST with a JSON body from the page's own origin. `RunnerPage` adds
  addresses and never loosens a rule. Every answer is JSON, except a slide's picture
  (image/png) and the deck itself (the .pptx).
- Reads (GET):
  - `/api/capabilities` {"runner": true, "version"}; `/api/setup`, what `setup.describe`
    says; `/api/agents` {"agents": [{"agent", "installed", "signed_in", "reachable",
    "version", "problem"}]}; `/api/models?agent=` what an agent offers to choose from
    ({"agent", "models", "levels", "source", "problem"}; a list that could not be made is
    answered with no models and `problem`, and listing holds up nothing else).
  - `/api/decks`, every deck in the engine's four lists {"needs", "working", "finished",
    "elsewhere"}; `/api/run?path=` one deck's view (`engine.view`).
  - `/api/slide?path=&kind=build|look|original&number=` (or `&name=` for a look by its
    name, or `contact-sheet` for the build's sheet): one picture as image/png, only what
    `engine.picture` gives. Nothing is ever read from a place the request names.
  - `/api/download?path=`: the rendered deck, only what `engine.download` gives, as an
    attachment named for the deck.
  - `/api/file?path=&name=`: one of a deck's shared files, by name, only from FILES:
    {"name", "size", "text", "truncated"}. A file that leads out of the deck's folder is
    refused.
  - `/api/status` (`engine.standing`), `/api/published` {"published": [...]},
    `/api/delete?path=` what deleting would do (`engine.leaving`), and `/api/computer`, the
    last look at this computer with what a deck needs here.
- Changes (POST):
  - `/api/setup/check` and `/api/setup`: see `setup`.
  - `/api/decks` {"form", "uploads"?}: start a deck. `form` is what `decks.check_form`
    reads; `uploads` maps an uploaded file's name to its bytes in base64. Answers
    {"path", "id"}. It alone may carry up to DECKS_LIMIT bytes, and only with the key.
  - `/api/run` {"path", "action"}: pause, resume, stop, retry or undo; answers the view.
  - `/api/decide` {"path", "gate", "decision", "note"?, "extra"?}: the only way a gate
    moves; answers the view. `/api/answer` {"path", "id", "answer"}: a worker's question.
  - `/api/share` {}, `/api/fetch` {}, `/api/drive` {"path", "action": take|hand-over},
    `/api/publish` {"path"}, `/api/delete` {"path", "title"}, `/api/bring` {"path"}: a
    deck this computer knows from outside the workspace, copied in (`engine.bring`).
  - `/api/companions` {}, `/api/upgrade` {"version"}, `/api/restart` {}, `/api/versions`
    {"dismiss"}: asked of `engine.upkeep`, each answering {"upkeep"}; 409 where nothing
    looks after the skills here, and while a deck is working (`upkeep` says so).
  - `/api/computer` {}: look at this computer again, and at the skills, and wake the decks
    that were waiting on what was missing.
- A refusal is {"error": "<a sentence>"}. Something sent in the wrong shape is 400; a deck
  that is not one of this workspace's is 404; something that cannot be done as things
  stand, such as a change to a deck someone else drives, is 409.
- Every request that passes the rules tells the engine a page is open, which is how the
  runner knows not to notify through the computer instead. Reading never starts or wakes
  a run.
- Ported from Training Studio's runner/page.py. Its desk lists, gates, documents, copies,
  outline, assets and adopt are gone: a deck has one view, one decision address and its
  start form.
"""
from __future__ import annotations

import base64
import binascii
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import home
import server
from workspace import WorkspaceError

from runner import decks, gitstate, settings, setup
from runner import engine as engines

READS = ('/api/capabilities', '/api/setup', '/api/agents', '/api/models', '/api/decks',
         '/api/run', '/api/slide', '/api/download', '/api/status', '/api/published',
         '/api/delete', '/api/file')
WRITES = ('/api/setup/check', '/api/setup', '/api/decks', '/api/run', '/api/decide',
          '/api/answer', '/api/share', '/api/fetch', '/api/drive', '/api/publish',
          '/api/delete', '/api/bring', '/api/companions', '/api/upgrade', '/api/restart',
          '/api/versions')
PNG = 'image/png'
PPTX = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
DECKS = '/api/decks'
DECKS_LIMIT = 120_000_000    # bytes: a deck's form with its uploads, in base64
FILES = ('README.md', 'intake.md', 'classify.md', 'outline.md', 'look.md',
         'research/plan.md', 'research/report.md')
PREVIEW_LIMIT = 1_000_000    # bytes of a file sent to the page
NO_DECK = 'There is no deck there.'
NO_KEEPER = ('This runner does not look after the skills on this computer. Run the installer '
             'to update them.')
NAMED = re.compile(r'[^A-Za-z0-9._-]')


def shaped(action, *args):
    """Run something that reads what was sent. Its refusal means the request was wrong."""
    try:
        return action(*args)
    except WorkspaceError as refusal:
        raise server.Refusal(HTTPStatus.BAD_REQUEST, str(refusal))


class RunnerPage(server.Page):
    """What the page may ask the runner."""
    reads = (*server.READS, *READS)
    writes = (*server.WRITES, *WRITES)

    def __init__(self, port: int, engine: engines.Engine):
        super().__init__(port)
        self.engine = engine

    # --- reads ---------------------------------------------------------------------------

    def read(self, path: str, one):
        self.engine.seen()
        if path == '/api/capabilities':
            return server.as_json(HTTPStatus.OK, {'runner': True,
                                                  'version': gitstate.installed()})
        if path == '/api/setup':
            return server.as_json(HTTPStatus.OK, setup.describe(self.engine))
        if path == '/api/agents':
            return server.as_json(HTTPStatus.OK, {'agents': self.agents()})
        if path == '/api/models':
            return server.as_json(HTTPStatus.OK, shaped(self.engine.models, one('agent')))
        if path == '/api/decks':
            return server.as_json(HTTPStatus.OK, self.engine.decks())
        if path == '/api/run':
            return server.as_json(HTTPStatus.OK, self.run(one('path')))
        if path == '/api/slide':
            return HTTPStatus.OK, PNG, self.slide(one)
        if path == '/api/download':
            return self.download(one('path'))
        if path == '/api/file':
            return server.as_json(HTTPStatus.OK, self.file(one('path'), one('name')))
        if path == '/api/status':
            return server.as_json(HTTPStatus.OK, self.engine.standing())
        if path == '/api/published':
            return server.as_json(HTTPStatus.OK, {'published': self.engine.published()})
        if path == '/api/delete':
            return server.as_json(HTTPStatus.OK, self.engine.leaving(self.deck(one('path'))))
        return super().read(path, one)

    def deck(self, path: str) -> str:
        """A deck of this workspace, or 404 for any other folder, whatever it holds."""
        if self.engine.driven(path) is None:
            raise server.Refusal(HTTPStatus.NOT_FOUND, NO_DECK)
        return path

    def run(self, path: str) -> dict:
        found = self.engine.view(self.deck(path))
        if found is None:
            raise server.Refusal(HTTPStatus.NOT_FOUND, NO_DECK)
        return found

    def slide(self, one) -> bytes:
        """One picture of a deck. The request names the deck, the kind of picture and a
        slide's number or a name, and nothing else: where it is kept is the engine's."""
        def given(name: str) -> str | None:
            try:
                return one(name)
            except server.Refusal:
                return None

        path, kind = self.deck(one('path')), one('kind')
        number, name = given('number'), given('name')
        if kind not in engines.PICTURE_KINDS:
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'A picture is of the build, a look or '
                                 'the original deck: ' + ', '.join(engines.PICTURE_KINDS) + '.')
        if (number is None) == (name is None):
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'Name the slide by its number, or by '
                                 'a name, and not both.')
        if number is not None and not (number.isascii() and number.isdigit()):
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'Give number as a whole number.')
        try:
            return shaped(self.engine.picture, path, kind,
                          int(number) if number is not None else name)
        except OSError:
            raise server.Refusal(HTTPStatus.NOT_FOUND, engines.NO_PICTURE)

    def download(self, path: str) -> tuple:
        """The rendered deck, as a file to keep."""
        name, data = self.engine.download(self.deck(path))
        name = NAMED.sub('-', name) or 'deck.pptx'
        return HTTPStatus.OK, PPTX, data, {
            'Content-Disposition': f'attachment; filename="{name}"'}

    def file(self, path: str, name: str) -> dict:
        """One of a deck's shared files, by its name: only those in FILES."""
        root = Path(self.deck(path))
        if name not in FILES:
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'A file is one of: '
                                 + ', '.join(FILES) + '.')
        file = (root / name).resolve()
        if root.resolve() not in file.parents:
            raise server.Refusal(HTTPStatus.FORBIDDEN, f'{name} leads outside the deck folder.')
        if not file.is_file():
            raise server.Refusal(HTTPStatus.NOT_FOUND, f'{name} has not been written yet.')
        with open(file, 'rb') as stream:
            data = stream.read(PREVIEW_LIMIT)
        truncated = file.stat().st_size > len(data)
        return {'name': name, 'size': file.stat().st_size,
                'text': data.decode('utf-8', 'replace'), 'truncated': truncated}

    def agents(self) -> list[dict]:
        """Each agent: installed, signed in and reachable now. Looked at when asked, both
        at once, and each look is reused for a minute."""
        names = list(self.engine.adapters)
        with ThreadPoolExecutor(max_workers=len(names) or 1) as pool:
            found = list(pool.map(self.engine.ready, names))
        return [{'agent': name, 'installed': ready.installed, 'signed_in': ready.signed_in,
                 'reachable': ready.reachable, 'version': ready.version,
                 'problem': ready.problem} for name, ready in zip(names, found)]

    def uses_google(self) -> bool:
        """Whether a new deck is made in Google Slides, or a deck here was."""
        if settings.load().output == 'google':
            return True
        for root in self.engine.every():
            try:
                if (decks.read_run(root).get('form') or {}).get('output') == 'google':
                    return True
            except (OSError, ValueError, AttributeError):
                continue
        return False

    def computer(self, look: bool) -> dict | None:
        """The last look at this computer, with what a deck needs here. A new look is a new
        look at those too and at the skills, and wakes the decks waiting on them."""
        seen = super().computer(look)
        if seen is None:
            return None
        keep = getattr(self.engine, 'upkeep', None)
        if look and keep is not None:
            keep.again()
        needs = self.engine.look_again() if look else self.engine.deck_needs()
        items = [{**item, 'optional': False} for item in needs['items']]
        wrong = [*seen['wrong'], *(item['name'] for item in items if item['state'] != 'ok')]
        return {**seen, 'items': [*seen['items'], *items], 'wrong': wrong,
                'ready': seen['ready'] and not wrong}

    def body_limit(self, target: str, headers) -> int:
        """A deck's form may carry its uploads whole, to its own address, from whoever holds
        the key. Anyone else's request there is held to the usual limit, so it is refused
        unread."""
        if target.partition('?')[0] == DECKS:
            try:
                self.check_token(headers)
            except server.Refusal:
                return super().body_limit(target, headers)
            return DECKS_LIMIT
        return super().body_limit(target, headers)

    # --- changes -------------------------------------------------------------------------

    def write(self, path: str, sent: dict):
        self.engine.seen()
        if path == '/api/setup/check':
            return server.as_json(HTTPStatus.OK, shaped(setup.check, sent))
        if path == '/api/setup':
            return server.as_json(HTTPStatus.OK,
                                  setup.apply(self.engine, shaped(setup.read, sent)))
        if path == DECKS:
            return server.as_json(HTTPStatus.OK, self.start(sent))
        if path == '/api/run':
            return server.as_json(HTTPStatus.OK, self.act(sent))
        if path == '/api/decide':
            return server.as_json(HTTPStatus.OK, self.decide(sent))
        if path == '/api/answer':
            return server.as_json(HTTPStatus.OK, self.answered(sent))
        if path == '/api/share':
            return server.as_json(HTTPStatus.OK, self.engine.share())
        if path == '/api/fetch':
            return server.as_json(HTTPStatus.OK, self.engine.fetch())
        if path == '/api/drive':
            return server.as_json(HTTPStatus.OK, self.drive(sent))
        if path == '/api/publish':
            return server.as_json(HTTPStatus.OK, self.engine.publish(
                self.deck(server.text(sent, 'path'))))
        if path == '/api/delete':
            title = server.text(sent, 'title')
            return server.as_json(HTTPStatus.OK, self.engine.delete(
                self.deck(server.text(sent, 'path')), title))
        if path == '/api/bring':
            return server.as_json(HTTPStatus.OK, self.bring(sent))
        if path == '/api/companions':
            return server.as_json(HTTPStatus.OK, {'upkeep': self.keeper().update(
                self.working())})
        if path == '/api/upgrade':
            version = server.text(sent, 'version')
            return server.as_json(HTTPStatus.OK, {'upkeep': self.keeper().upgrade(
                self.working(), version)})
        if path == '/api/restart':
            return server.as_json(HTTPStatus.OK, {'upkeep': self.keeper().restart(
                self.working())})
        if path == '/api/versions':
            dismissed = server.text(sent, 'dismiss')
            return server.as_json(HTTPStatus.OK, {'upkeep': self.keeper().dismiss(dismissed)})
        return super().write(path, sent)

    def keeper(self):
        """What looks after the skills here, or a refusal where nothing does."""
        keep = getattr(self.engine, 'upkeep', None)
        if keep is None:
            raise server.Refusal(HTTPStatus.CONFLICT, NO_KEEPER)
        return keep

    def working(self) -> bool:
        return setup.working(self.engine)

    def start(self, sent: dict) -> dict:
        """Start a deck from its form and what was uploaded with it."""
        form, given = sent.get('form'), sent.get('uploads') or {}
        if not isinstance(form, dict):
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'Send the form as one JSON object.')
        if not isinstance(given, dict) or not all(isinstance(name, str) and name.strip()
                                                  for name in given):
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'Send the uploads by their names.')
        uploads = {}
        for name, content in given.items():
            if not isinstance(content, str) or not content:
                raise server.Refusal(HTTPStatus.BAD_REQUEST, f'"{name}" arrived empty. Choose '
                                     'the file again.')
            try:
                uploads[name] = base64.b64decode(content, validate=True)
            except (binascii.Error, ValueError):
                raise server.Refusal(HTTPStatus.BAD_REQUEST, f'"{name}" did not arrive whole. '
                                     'Choose the file again.')
        brands = self.engine.brands() if self.engine.workspace is not None else None
        if brands is not None:   # what makes no sense is said as such; the rest is the engine's
            shaped(decks.check_form, form, brands)
        return self.engine.start(form, uploads)

    def act(self, sent: dict) -> dict:
        path, action = server.text(sent, 'path'), server.text(sent, 'action')
        if action not in engines.ACTIONS:
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'A run can be asked to: '
                                 + ', '.join(engines.ACTIONS) + '.')
        return self.engine.act(self.deck(path), action)

    def decide(self, sent: dict) -> dict:
        """A person's decision at a gate: approve, or ask for changes with a note."""
        path, gate = server.text(sent, 'path'), server.text(sent, 'gate')
        decision, note = server.text(sent, 'decision'), server.text(sent, 'note', False)
        extra = sent.get('extra')
        if gate not in engines.WORDS:
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'A decision is made at one of the '
                                 'gates: ' + ', '.join(engines.WORDS) + '.')
        if decision not in engines.DECISIONS:
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'A decision is to approve, or to ask '
                                 'for changes: ' + ', '.join(engines.DECISIONS) + '.')
        if extra is not None and not isinstance(extra, dict):
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'Send what comes with a decision as '
                                 'one JSON object.')
        if decision == 'changes' and not (note or '').strip():
            raise server.Refusal(HTTPStatus.BAD_REQUEST, engines.NO_NOTE)
        return self.engine.decide(self.deck(path), gate, decision, note, extra)

    def answered(self, sent: dict) -> dict:
        path, ident = server.text(sent, 'path'), server.text(sent, 'id')
        answer = server.text(sent, 'answer')
        if not answer.strip():
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'Write an answer first.')
        return self.engine.answer(self.deck(path), ident, answer)

    def drive(self, sent: dict) -> dict:
        """Take a deck, which takes over one someone else drives, or hand it over."""
        path, action = server.text(sent, 'path'), server.text(sent, 'action')
        if action not in engines.DRIVING:
            raise server.Refusal(HTTPStatus.BAD_REQUEST, 'A deck can be asked to: '
                                 + ', '.join(engines.DRIVING) + '.')
        return self.engine.drive(self.deck(path), action)

    def bring(self, sent: dict) -> dict:
        """Copy a deck this computer knows, made outside the workspace, into it. Any other
        folder is refused, whatever it holds; the folder it came from is only read."""
        path = server.text(sent, 'path')
        if path not in [entry['path'] for entry in home.decks()]:
            raise server.Refusal(HTTPStatus.FORBIDDEN, 'That folder is not a deck this '
                                 'computer knows.')
        return self.engine.bring(path)


class Studio(server.Desk):
    """The runner's server: the page, answering for the engine."""

    def __init__(self, engine: engines.Engine, port: int = 0, token: str | None = None):
        super().__init__(port, page=lambda chosen: RunnerPage(chosen, engine))
        self.engine = engine
        if token:   # a runner opened again in its own place keeps the key its page holds
            self.page.token = self.token = token

    def serve(self) -> None:
        self.engine.serving()
        super().serve()

    def leave(self, after: float = 0.5) -> None:
        """Stop serving shortly, once what is being answered has gone out."""
        threading.Timer(after, self.server.shutdown).start()

    def start(self) -> None:
        self.engine.serving()
        super().start()

    def stop(self) -> None:
        super().stop()
        self.engine.close()
