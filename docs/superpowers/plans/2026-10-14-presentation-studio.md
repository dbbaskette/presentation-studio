# Presentation Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Presentation Studio — a local, approval-gated page that makes Tanzu-branded decks from scratch, from a document, or from an existing deck, using harness-slides, harness-research and tanzu-brand, with every decision shared through the team repository under `presentations/`.

**Architecture:** A fork-and-trim of Training Studio (`/Users/dbbaskette/Projects/training-studio`, revision `b19c743673297fa44e245bb76b9e1e36f094223d`). Domain-neutral modules (git workspace, team claims, agents, worker tools, the slides/brand/research wrappers, documents, settings, companions, upkeep, the page server's security base) are copied and renamed. The training domain (levels, blueprints, scenarios, Yoodli, Word copies, the training core's session/gate model) is dropped and replaced by a deck domain: `decks.py` (the deck folder and its run record), `stages.py` (the pipeline as data, with a skip map per route and level), and step modules for intake, research, outline, look, build, existing decks and delivery, driven by a new `engine.py`. The page is a new `app.js` on Training Studio's vendored `style.css` and `markdown.js`, reusing its slide-picture viewer.

**Tech Stack:** Python 3.11+ standard library only; vanilla JS/HTML/CSS (no build step); git; Node 20+ for the companions (harness-slides, harness-research, tanzu-brand); `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-14-presentation-studio-design.md`

## Global Constraints

- Python 3.11 or newer, standard library only, no third-party packages, no build step. On this computer run Python as `PY=/Users/dbbaskette/.local/share/uv/python/cpython-3.12-macos-x86_64-none/bin/python3.12` (system `python3` is 3.9 and too old).
- Source of every ported file: `/Users/dbbaskette/Projects/training-studio` at revision `b19c743673297fa44e245bb76b9e1e36f094223d`. Record each ported file in `vendor.json` as `{"path": "<ours>", "from": "<theirs>", "revision": "b19c7436…"}`.
- Renames applied to every ported file: `Training Studio` → `Presentation Studio`; `training-studio` → `presentation-studio`; `TRAINING_STUDIO_` env prefix → `PRESENTATION_STUDIO_`; `.training-studio` state dir → `.presentation-studio`; HTTP header `X-Training-Studio-Token` → `X-Presentation-Studio-Token`; "a training"/"trainings" → "a deck"/"decks" in person-facing sentences.
- Workspace folder in the team repo: `presentations/` with marker `hub.json` = `{"schema": 1, "tool": "presentation-studio"}`. The runner never reads or writes outside that folder.
- Per-user data folder: `~/.local/share/presentation-studio/` (overridable by `PRESENTATION_STUDIO_DATA`, which every test sets to a temporary directory).
- Routes: `scratch`, `document`, `existing`. Existing-deck levels: `brand-only`, `polish`, `redesign`, `rework`, `selected`. Outputs: `google` (default), `pptx`. Brands come from tanzu-brand; default brand `tanzu`, variant `light`.
- Agents: the person's own `claude` or `codex` CLI as a subprocess, stripped environment, no built-in tools, only the runner's MCP worker tools (plus web search for research questions), no session persistence. Agents never approve; only a decision on the page approves.
- All slide work goes through the harness-slides CLI; the studio never edits slide files itself.
- Never shared (gitignored under `presentations/`): `*/sources/`, `*/work/`, `*.lock`, `**/.presentation-studio/lock`, `**/.harness-research/guidance/`, `**/.harness-slides/guidance/`.
- Person-facing sentences never say "artifact", "stale" or "lineage" (Training Studio's rule).
- Page server: 127.0.0.1 only, `Host` header checked, key required on every call, changes only as POST with a JSON body from the page's own origin, CSP `default-src 'self'; img-src 'self' blob:`.
- Tests never start an agent, call Google, render, or run a real companion: they use the stand-ins in `tests/stand_ins/`.
- Commit after each task with a message ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A deck whose route is `existing` and whose source is a Google Slides link while Google is not signed in** — refused at intake with one sentence telling the person to sign in or upload a `.pptx`; nothing is created. Test owned by Task 9.
2. **A document that is neither a clear slide spec nor clear material (e.g. a short bullet list)** — classified anyway with the reason shown, and the person's correction at the classify gate switches the route branch without losing the document. Test owned by Task 7.
3. **Asking for changes at the build gate after delivery when the original Google Slides file was deleted by the person** — a new file is made and `deliver.json` records the new link; nothing crashes on the missing file. Test owned by Task 10.
4. **Two computers start a deck with the same title at the same moment** — the second gets a distinct deck ID (`<slug>-2`) or is told the name is taken; never a merge of two decks into one folder. Test owned by Task 4.
5. **A Brand-only or Polish redesign where the extracted outline changes a word of the original** — refused by the verbatim check before build, worker retried with the reason; the person never sees altered wording. Test owned by Task 9.

---

## File Structure

```
presentation-studio/
  VERSION                                   0.1.0
  README.md  AGENTS.md  LICENSE  vendor.json
  guidance/manifest.json                    {"schema":1,"content_root":"skills/presentation-studio","minimum_runtime":"0.1.0"}
  scripts/ci/run_tests.py                   ported parallel test runner
  bootstrap/presentation-studio/SKILL.md    small entrypoint the installer registers
  installer/  install.sh  install.py  "Install Presentation Studio.command"  companions.json
  skills/presentation-studio/
    SKILL.md                                chat use: routes, how to drive harness-slides + tanzu-brand
    references/{routes,levels,workspace}.md
    scripts/                                the core (put on sys.path by runner/__init__.py)
      home.py hub.py sync_guidance.py computer.py   ported, renamed
      workspace.py                          lean: WorkspaceError, write_atomic, STATE_DIR, SKILL_DIR
      server.py                             ported security base of desk.py (Page, Handler, Refusal)
      gdrive.py                             Drive access through gcloud: export a Google Doc as text
      desk/ index.html app.js style.css markdown.js
  runner/
    __init__.py studio.py page.py setup.py settings.py upkeep.py companion.py
    gitstate.py team.py agents.py worker_tools.py claude-code-models.json
    slides.py brand.py research.py documents.py
    decks.py        the deck folder: form, create, run record, README, index
    stages.py       the pipeline as data; survey(run) -> next step
    steps/          one module per stage family, each pure-ish and called by the engine
      intake.py     classify a document; read a Google Doc; inventory an existing deck
      outline.py    outline from material/spec/brief, restructure, extract (verbatim)
      look.py       sample slide 2–3 ways, previews, choice
      build.py      brand export, sections, merge, compile, preview, review, repair, render
      existing.py   selected-changes patch path, before/after pairing
      deliver.py    render/import, deliver.json, contact sheet, revisions
    engine.py       walks each deck, runs workers, stops at gates, claims, commits, shares
    briefs/         worker prompts (*.md) + __init__.py guidance()
  tests/
    helpers.py runner_support.py stand_ins/{slides,brand,research}.py fixtures/
    test_*.py
  docs/ runner.md development.md acceptance.md superpowers/...
```

---

### Task 1: Scaffold and the ported core

**Files:**
- Create: `VERSION`, `AGENTS.md`, `LICENSE` (copy Training Studio's), `vendor.json`, `guidance/manifest.json`, `.gitignore` (`__pycache__/`, `*.pyc`, `.DS_Store`)
- Create (port): `scripts/ci/run_tests.py` ← `training-studio/scripts/ci/run_tests.py`
- Create (port): `skills/presentation-studio/scripts/home.py` ← `skills/training-studio/scripts/home.py`; `hub.py` ← `hub.py`; `sync_guidance.py` ← `sync_guidance.py`; `computer.py` ← `computer.py`
- Create (new): `skills/presentation-studio/scripts/workspace.py`
- Create (port): `runner/__init__.py` (CORE path → `skills/presentation-studio/scripts`, docstring lists our modules), `runner/companion.py`, `runner/settings.py`
- Create (port): `tests/helpers.py` (env `PRESENTATION_STUDIO_DATA`, `SKILL`/`SCRIPTS` paths; drop training CONTENT/RESEARCH samples not used), `tests/test_runner_companion.py`, `tests/test_sync.py` (only cases still meaningful), `tests/test_core_home.py` (new)

**Interfaces:**
- Produces: `workspace.WorkspaceError(Exception)` (message is a sentence for a person); `workspace.write_atomic(path: Path, text: str) -> None`; `workspace.STATE_DIR = '.presentation-studio'`; `workspace.SKILL_DIR: Path`; `home.data_root() -> Path`, `home.read_json(path, default=None)`, `home.write_json(path, value)`, `home.now() -> str` (ISO UTC), `home.alive(pid) -> bool`, `home.decks() -> Path` (renamed from `trainings()`); everything `hub`, `sync_guidance`, `companion`, `settings` exported in Training Studio, unchanged in name.

- [ ] **Step 1: Copy the files listed above, apply the Global Constraints renames, and remove training-only names** (`LEVELS`, `BRIEF_KINDS`, yoodli profile paths, `trainings()` → `decks()`). `workspace.py` is new and contains only:

```python
"""What every part of Presentation Studio shares: the refusal a person reads, and safe writes."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

STATE_DIR = '.presentation-studio'
SKILL_DIR = Path(__file__).resolve().parent.parent
CHECKOUT_MARK = Path('skills') / 'presentation-studio' / 'SKILL.md'


class WorkspaceError(Exception):
    """A refusal or failure, said in one sentence a person can read as it is."""


def write_atomic(path: Path, text: str) -> None:
    """Write text so a reader sees the old file or the new one, never half of either."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            out.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
```

Any other `workspace.<name>` a ported module used (e.g. `workspace.SKILL_DIR`, `workspace.STATE_DIR`) must resolve to the above; where a ported module used a training-session function (`workspace.load`, `workspace.session_path`, `workspace.training`), delete that use or move the need into a later task's module and note it in the commit message.

- [ ] **Step 2: Write `tests/test_core_home.py`**

```python
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
```

- [ ] **Step 3: Run** `cd tests && $PY -m unittest test_core_home test_runner_companion test_sync -v` — expect PASS. Fix ported code (not the tests' intent) until it does.
- [ ] **Step 4: Run** `$PY scripts/ci/run_tests.py` — expect all pass.
- [ ] **Step 5: Commit** `git add -A && git commit -m "Scaffold Presentation Studio and port the core from Training Studio"`

---

### Task 2: The shared workspace and team claims

**Files:**
- Create (port): `runner/gitstate.py` (`TOOL = 'presentation-studio'`, `FOLDER = 'presentations'`, `README` text for decks, `IGNORED = ('work/', 'sources/', '**/.harness-research/guidance/', '**/.harness-slides/guidance/', '*.lock', '**/.presentation-studio/lock')`)
- Create (port): `runner/team.py` (claims, take/hand-over, publish as numbered revision tags `presentations/<deck>/r<N>`, notifications)
- Test (port): `tests/test_runner_gitstate.py`, `tests/test_runner_team.py`
- Test (new): `tests/test_shared_root.py`

**Interfaces:**
- Consumes: Task 1 core.
- Produces: `gitstate.Workspace` (`.root`, `.repo`, `.folder`, `.branch`, `.share`), `gitstate.join(address, folder=None, branch=None)`, `gitstate.local(path, folder=None, branch=None)`, `gitstate.current()`, `gitstate.commit(ws, message, paths=None) -> bool`, `gitstate.sync(ws, push=True, ...) -> dict`, `gitstate.discard`, `undo`, `remove`, `set_aside`, `kept`, `moved`, `arrived`, `theirs`; `team.ours(path) -> bool`, `team.claim(...)`, `team.publish(...)` etc. exactly as Training Studio names them (the deck folder replaces the training folder; "item" naming stays generic).

- [ ] **Step 1: Port both modules and both test files; rename training → deck in identifiers that name the item** (e.g. `workspace.training(id)` becomes `workspace.deck(id)`), keep every behavior.
- [ ] **Step 2: Write `tests/test_shared_root.py`** — a bare remote that already has `trainings/hub.json` (tool `training-studio`) and `blogs/README.md`; `gitstate.join(remote)` lays out `presentations/` beside them, commits only under `presentations/`, and pushing leaves `trainings/` and `blogs/` byte-identical:

```python
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from runner import gitstate


def git(cwd, *args):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


class SharedRootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
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
```

- [ ] **Step 3: Run** `cd tests && $PY -m unittest test_runner_gitstate test_runner_team test_shared_root -v` — PASS.
- [ ] **Step 4: Run the whole suite** — PASS.
- [ ] **Step 5: Commit** `"Port the shared workspace and team claims, under presentations/"`

---

### Task 3: Agents, worker tools and the tool wrappers

**Files:**
- Create (port): `runner/agents.py`, `runner/claude-code-models.json`, `runner/worker_tools.py`, `runner/slides.py`, `runner/brand.py`, `runner/research.py`, `runner/documents.py`
- Create (new): `skills/presentation-studio/scripts/gdrive.py`
- Create (port): `tests/runner_support.py`, `tests/stand_ins/{__init__,slides,brand,research,assets,review}.py`, `tests/test_runner_agents.py`, `tests/test_runner_worker_tools.py`, `tests/test_runner_slides.py`, `tests/test_runner_brand.py`, `tests/test_runner_research.py`, `tests/test_runner_documents.py`
- Test (new): `tests/test_gdrive.py`, additions to `tests/test_runner_slides.py`

**Interfaces:**
- Produces, in addition to everything those modules export in Training Studio:
  - `worker_tools.VALIDATORS` holds only: `'research-plan'`, `'classify'`, `'outline'`, `'section'`, `'look'`, `'patch'` (the last three are registered by later tasks through `worker_tools.register(kind: str, check: Callable[[str, dict], tuple[list[str], list[dict], list[str], str]])`). Training validators (`blueprint`, `document`, `brief`, `scenario`, `yoodli`) are removed with their checks. The `outline` validator no longer applies `deck.rules` (objectives/blueprint); it applies the slides tool's `outline check` plus the rules passed in the spec under `'rules'` (a list of callables `(outline: dict) -> list[str]`), so later tasks add the verbatim rule.
  - `Slides.pptx_inspect(deck: Path) -> dict` → `pptx inspect --file deck --json`.
  - `Slides.pptx_patch(deck: Path, plan: Path, output: Path) -> dict` → `pptx patch`.
  - `Slides.pptx_compare(deck: Path, after: Path, allow: Path) -> dict` → `pptx compare`.
  - `Slides.pictures_of(deck: Path, folder: Path, renderer: str, file_id: str | None = None) -> dict` → `review --file deck --output folder --renderer local|google [--file-id]`, returning `{'slides': [{'number', 'image'}], 'contactSheet', 'fileId', 'url'}` (under the same `PREVIEWING` lock as `preview`).
  - `Slides.drive_export(file_id: str, deck: Path) -> Path` → `drive export --file-id --output`.
  - `Slides.outline_draft(outline: Path, brand: Path, output: Path) -> Path` → `outline draft`.
  - `gdrive.FILE_ID` regex; `gdrive.file_id(link: str) -> str` (accepts a bare ID or a `docs.google.com/.../d/<id>/...` URL, else WorkspaceError); `gdrive.Drive(run=None, urlopen=None).export_text(file_id) -> str` (Drive v3 `files/{id}/export?mimeType=text/plain`, token from `gcloud auth print-access-token`, ported from Training Studio `gdocs.DriveTransport`; token never appears in an error).
  - `documents.add(root, name, data)`, `documents.listed(root)`, `documents.remove(root, name)`, `documents.text_of(root, entry) -> str` (new, reads the kept text), `documents.add_text(root, title, text) -> dict` (new, pasted text or an exported Google Doc kept as `<slug>.md`).

- [ ] **Step 1: Port the files.** Remove from `worker_tools.py` and `deck`-dependent code every training validator and the blueprint/objective coupling; keep the generic tools (`list_inputs`, `read_input`, `submit_artifact`, `ask_person`, `search_web`/`fetch_page`/`save_source` for research, `record_finding`), the deck tools (`check_outline`, `submit_outline`, `check_section`, `preview_section`, `search_icons`, `submit_section`, `look_at_slide`, `submit_assessment`) and the job folder protocol. Where the ported `worker_tools` imported Training Studio's `runner/deck.py` helpers (`deck.kept`, `deck.fixed`, `deck.checked`, …), copy those helpers into `runner/steps/build.py` (created now as a module of pure functions; Task 10 adds the step functions) and import them from there, dropping the blueprint/objectives parts.
- [ ] **Step 2: Add the six new `Slides` methods** with the stand-in in `tests/stand_ins/slides.py` behaving like the real command (writes a fake `.pptx` that starts with `PK\x03\x04`, PNGs from the existing stand-in picture helper, an inspect JSON shaped like the real one: `{'sha256', 'size', 'slides': [{'number','id','title','hidden','objects': [{'id','type','text','runs','alt','title','box','contentHash','structureHash'}]}]}`).
- [ ] **Step 3: Write tests for the new methods** in `tests/test_runner_slides.py`:

```python
class NewCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.slides = stand_in_slides()          # helper from runner_support

    def test_inspect_returns_slides_and_objects(self):
        deck = self.tmp / 'in.pptx'
        deck.write_bytes(b'PK\x03\x04 stand-in')
        found = self.slides.pptx_inspect(deck)
        self.assertIn('slides', found)
        self.assertIn('objects', found['slides'][0])

    def test_pictures_of_a_deck(self):
        deck = self.tmp / 'in.pptx'
        deck.write_bytes(b'PK\x03\x04 stand-in')
        shown = self.slides.pictures_of(deck, self.tmp / 'shots', 'local')
        self.assertTrue(all(Path(s['image']).is_file() for s in shown['slides']))

    def test_patch_refuses_an_existing_output(self):
        deck = self.tmp / 'in.pptx'
        deck.write_bytes(b'PK\x03\x04 stand-in')
        (self.tmp / 'out.pptx').write_bytes(b'x')
        plan = self.tmp / 'plan.json'
        plan.write_text('{"sourceSha256": "x", "operations": []}')
        with self.assertRaises(slides_tool.Refused):
            self.slides.pptx_patch(deck, plan, self.tmp / 'out.pptx')
```

- [ ] **Step 4: Write `tests/test_gdrive.py`**

```python
import unittest
from unittest import mock

import helpers  # noqa: F401
import gdrive
from workspace import WorkspaceError


class FileIdTests(unittest.TestCase):
    def test_url_and_bare_id(self):
        url = 'https://docs.google.com/document/d/1AbC_d-9/edit?usp=sharing'
        self.assertEqual(gdrive.file_id(url), '1AbC_d-9')
        self.assertEqual(gdrive.file_id('1AbC_d-9'), '1AbC_d-9')

    def test_not_a_link(self):
        with self.assertRaises(WorkspaceError):
            gdrive.file_id('https://example.com/x')


class ExportTests(unittest.TestCase):
    def test_token_never_in_an_error(self):
        run = mock.Mock(return_value=mock.Mock(returncode=0, stdout='SECRET\n'))
        def refuse(request, timeout=None):
            raise OSError('failed with SECRET')
        drive = gdrive.Drive(run=run, urlopen=refuse)
        with self.assertRaises(WorkspaceError) as caught:
            drive.export_text('abc')
        self.assertNotIn('SECRET', str(caught.exception))
```

- [ ] **Step 5: Run** the ported and new test modules, then the whole suite — PASS.
- [ ] **Step 6: Commit** `"Port agents, worker tools and the slides, brand, research and documents wrappers"`

---

### Task 4: The deck folder and its run record (`decks.py`)

**Files:**
- Create: `runner/decks.py`
- Test: `tests/test_decks.py`

**Interfaces:**
- Consumes: `gitstate.Workspace`, `workspace.WorkspaceError`, `workspace.write_atomic`, `home.now`.
- Produces:
  - `ROUTES = ('scratch', 'document', 'existing')`, `LEVELS = ('brand-only', 'polish', 'redesign', 'rework', 'selected')`, `OUTPUTS = ('google', 'pptx')`, `LIMITS = {'title': 120, 'audience': 2000, 'goal': 2000, 'notes': 4000, 'minutes': 240, 'selected': 4000}`
  - `check_form(sent: dict, brands: list[dict]) -> dict` — returns `{'route', 'title', 'audience', 'goal', 'minutes' (int|None), 'brand', 'variant', 'output', 'research' (bool), 'level' (existing only), 'selected' (existing+selected only: free text naming slides and changes), 'source' (document: {'kind': 'upload'|'paste'|'google', ...}; existing: {'kind': 'upload'|'google', ...})}`; raises `WorkspaceError` with one sentence for: unknown route, missing title, over a limit, unknown brand/variant (from `brands` = `[{'brand','variants':[...]}]`), `level` missing for `existing`, `selected` text missing for `selected`, `research` true on `existing`.
  - `deck_id(space, title) -> str` — slug of the title (`[a-z0-9-]`, ≤ 48), with `-2`, `-3`… when a folder of that name exists locally **or** on the remote branch as last fetched (`gitstate.known`).
  - `create(space, form) -> Path` — makes `<root>/<id>/` with `intake.md` (headings: Title, Route, Audience, Goal, Length, Brand, Output, Research, Change level, Selected changes — only those that apply), `run.json`, `README.md`; commits `"<title>: start the deck"`.
  - `RUN = 'run.json'`; `read_run(root: Path) -> dict`; `write_run(root: Path, run: dict) -> None` (atomic). Run record shape: `{'schema': 1, 'id', 'title', 'route', 'form': {...}, 'created', 'driver': None|{'name','computer','since'}, 'gates': {gate_name: {'state': 'waiting'|'approved'|'changes', 'note', 'at', 'by', 'round'}}, 'steps': {step_name: {'tries': [...], 'done': bool, 'at'}}, 'classified': None|'spec'|'material', 'look': None|{...}, 'revisions': [], 'halted': None|{'why','at'}, 'agent', 'model', 'level_of_effort', 'limits'}`.
  - `readme(run: dict, deliver: dict | None) -> str`; `index(space) -> str` (one row per deck: title, route, state, link) written to `<root>/README.md` by `write_index(space)`.

- [ ] **Step 1: Write the failing tests** `tests/test_decks.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from runner import decks, gitstate
from workspace import WorkspaceError

BRANDS = [{'brand': 'tanzu', 'variants': ['light']},
          {'brand': 'vmware', 'variants': ['light', 'dark']}]


def form(**over):
    sent = {'route': 'scratch', 'title': 'Spring AI on Tanzu', 'audience': 'Platform teams',
            'goal': 'Show the path to production', 'brand': 'tanzu', 'variant': 'light',
            'output': 'google', 'research': False}
    sent.update(over)
    return sent


class FormTests(unittest.TestCase):
    def test_scratch_form(self):
        checked = decks.check_form(form(), BRANDS)
        self.assertEqual(checked['route'], 'scratch')
        self.assertEqual(checked['output'], 'google')

    def test_unknown_route(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='video'), BRANDS)

    def test_existing_needs_a_level(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='existing', source={'kind': 'upload', 'name': 'a.pptx'}),
                             BRANDS)

    def test_selected_needs_what_to_change(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='existing', level='selected',
                                  source={'kind': 'upload', 'name': 'a.pptx'}), BRANDS)

    def test_no_research_for_existing(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(route='existing', level='polish', research=True,
                                  source={'kind': 'upload', 'name': 'a.pptx'}), BRANDS)

    def test_unknown_variant(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(variant='dark'), BRANDS)

    def test_title_limit(self):
        with self.assertRaises(WorkspaceError):
            decks.check_form(form(title='x' * 121), BRANDS)


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.space = gitstate.local(Path(tempfile.mkdtemp()) / 'ws')

    def test_create_writes_intake_run_and_readme(self):
        root = decks.create(self.space, decks.check_form(form(), BRANDS))
        self.assertEqual(root.name, 'spring-ai-on-tanzu')
        run = decks.read_run(root)
        self.assertEqual(run['route'], 'scratch')
        self.assertIn('# Spring AI on Tanzu', (root / 'README.md').read_text())
        self.assertIn('Platform teams', (root / 'intake.md').read_text())

    def test_same_title_twice_gets_a_new_id(self):
        first = decks.create(self.space, decks.check_form(form(), BRANDS))
        second = decks.create(self.space, decks.check_form(form(), BRANDS))
        self.assertEqual(second.name, first.name + '-2')

    def test_run_round_trip(self):
        root = decks.create(self.space, decks.check_form(form(), BRANDS))
        run = decks.read_run(root)
        run['gates']['outline'] = {'state': 'waiting', 'round': 1}
        decks.write_run(root, run)
        self.assertEqual(decks.read_run(root)['gates']['outline']['state'], 'waiting')

    def test_index_lists_decks(self):
        decks.create(self.space, decks.check_form(form(), BRANDS))
        decks.write_index(self.space)
        self.assertIn('Spring AI on Tanzu', (self.space.root / 'README.md').read_text())
```

- [ ] **Step 2: Run** `cd tests && $PY -m unittest test_decks -v` — FAIL (no module).
- [ ] **Step 3: Implement `runner/decks.py`** to the interface above (module docstring in Training Studio's "What a caller needs to know" style).
- [ ] **Step 4: Run** — PASS; then the whole suite.
- [ ] **Step 5: Commit** `"Add the deck folder, its form and its run record"`

---

### Task 5: The pipeline as data (`stages.py`)

**Files:**
- Create: `runner/stages.py`
- Test: `tests/test_stages.py`

**Interfaces:**
- Consumes: run record shape from Task 4.
- Produces:
  - `Step = dataclass(frozen=True)(name: str, stage: str, kind: Literal['code','agent','gate'], label: str, doing: str)`.
  - `PIPELINE: tuple[Step, ...]` in this order (name / stage / kind):
    `intake-source/intake/code` (read the document or fetch the deck),
    `classify/classify/agent` (document only) or `inventory/classify/code` (existing only),
    `gate:classify/classify/gate`,
    `research-plan/research/agent`, `gate:research-plan/research/gate`, `research/research/agent`, `research-report/research/code`, `gate:research/research/gate`,
    `extract/outline/agent` (existing: verbatim outline from the inventory),
    `outline/outline/agent` (scratch; document material; document spec = parse; existing rework = restructure),
    `gate:outline/outline/gate`,
    `brand/look/code` (tanzu-brand contract export),
    `look/look/agent`, `look-preview/look/code`, `gate:look/look/gate`,
    `patch/build/agent` (selected only), `build-start/build/code`, `build-sections/build/agent`, `build-whole/build/code`, `build-review/build/agent`, `build-repair/build/agent`, `build-render/build/code`,
    `gate:build/build/gate`,
    `deliver/deliver/code`,
    `rehearse/rehearse/gate` (never active; shown as "coming later").
  - `steps(run: dict) -> list[Step]` — the steps this deck has, per this skip map:
    - research steps only when `form.research` and (route `scratch`, or route `document` and `run.classified == 'material'`);
    - `classify` only for `document`; `inventory` only for `existing`; `gate:classify` for both;
    - `extract` only for `existing` with level in `brand-only`, `polish`, `redesign`, `rework`;
    - `outline` + `gate:outline` for `scratch`, `document`, and `existing`+`rework` only;
    - `brand` always (all routes need the exported contract, including `selected` for the audit);
    - `look`, `look-preview`, `gate:look` for `scratch`, `document`, `existing`+`redesign`, `existing`+`rework`;
    - `patch` only for `selected`; `build-start`…`build-repair` for every route except `selected`; `build-render` always; `gate:build`, `deliver` always; `rehearse` always listed.
  - `Survey = dataclass(next: Step | None, done: list[str], waiting: str | None, halted: str | None)`.
  - `survey(run: dict) -> Survey` — `next` is the first listed step that is not done (`run['steps'][name]['done']`, or for a gate `run['gates'][name]['state'] == 'approved'`); `waiting` is the gate name when `next` is a gate whose state is `waiting`; a gate in state `changes` sends `next` back to the step that feeds it (`FEEDS = {'gate:classify': 'classify'|'inventory', 'gate:research-plan': 'research-plan', 'gate:research': 'research', 'gate:outline': 'outline' (or 'extract'), 'gate:look': 'look', 'gate:build': 'build-repair' when the request names slides else 'build-sections'; for `selected` → 'patch'}`); `rehearse` is never `next` (the pipeline ends at `deliver`).
  - `reopen(run: dict, gate: str) -> dict` — marks every step after the step that feeds `gate` as not done (used by "Ask for changes" and by changing the classification).
  - `timeline(run) -> list[dict]` — `[{'name','label','state': 'done'|'current'|'upcoming'|'later'}]` grouped by stage for the page.

- [ ] **Step 1: Write the failing table test** `tests/test_stages.py`:

```python
import unittest

import helpers  # noqa: F401
from runner import stages


def run(route, level=None, research=False, classified=None):
    form = {'route': route, 'research': research}
    if level:
        form['level'] = level
    return {'route': route, 'form': form, 'classified': classified, 'gates': {}, 'steps': {}}


def names(r):
    return [s.name for s in stages.steps(r)]


class SkipMapTests(unittest.TestCase):
    CASES = [
        (run('scratch'), ['intake-source', 'outline', 'gate:outline', 'brand', 'look',
                          'look-preview', 'gate:look', 'build-start', 'build-sections',
                          'build-whole', 'build-review', 'build-repair', 'build-render',
                          'gate:build', 'deliver', 'rehearse']),
        (run('existing', 'brand-only'), ['intake-source', 'inventory', 'gate:classify',
                                         'extract', 'brand', 'build-start', 'build-sections',
                                         'build-whole', 'build-review', 'build-repair',
                                         'build-render', 'gate:build', 'deliver', 'rehearse']),
        (run('existing', 'selected'), ['intake-source', 'inventory', 'gate:classify', 'brand',
                                       'patch', 'build-render', 'gate:build', 'deliver',
                                       'rehearse']),
        (run('existing', 'rework'), ['intake-source', 'inventory', 'gate:classify', 'extract',
                                     'outline', 'gate:outline', 'brand', 'look', 'look-preview',
                                     'gate:look', 'build-start', 'build-sections', 'build-whole',
                                     'build-review', 'build-repair', 'build-render',
                                     'gate:build', 'deliver', 'rehearse']),
    ]

    def test_cases(self):
        for r, expected in self.CASES:
            with self.subTest(route=r['route'], level=r['form'].get('level')):
                self.assertEqual(names(r), expected)

    def test_research_only_when_asked(self):
        self.assertIn('research-plan', names(run('scratch', research=True)))
        self.assertNotIn('research-plan', names(run('scratch')))

    def test_document_research_only_for_material(self):
        self.assertNotIn('research', names(run('document', research=True, classified='spec')))
        self.assertIn('research', names(run('document', research=True, classified='material')))

    def test_polish_and_brand_only_skip_look(self):
        for level in ('brand-only', 'polish'):
            self.assertNotIn('gate:look', names(run('existing', level)))
        self.assertIn('gate:look', names(run('existing', 'redesign')))


class SurveyTests(unittest.TestCase):
    def test_first_step_is_next(self):
        self.assertEqual(stages.survey(run('scratch')).next.name, 'intake-source')

    def test_waiting_gate(self):
        r = run('scratch')
        r['steps'] = {'intake-source': {'done': True}, 'outline': {'done': True}}
        r['gates'] = {'gate:outline': {'state': 'waiting'}}
        found = stages.survey(r)
        self.assertEqual(found.waiting, 'gate:outline')

    def test_changes_go_back_to_the_feeding_step(self):
        r = run('scratch')
        r['steps'] = {'intake-source': {'done': True}, 'outline': {'done': True}}
        r['gates'] = {'gate:outline': {'state': 'changes', 'note': 'shorter'}}
        r = stages.reopen(r, 'gate:outline')
        self.assertEqual(stages.survey(r).next.name, 'outline')

    def test_finished_deck_has_no_next(self):
        r = run('existing', 'selected')
        for s in stages.steps(r):
            if s.kind == 'gate':
                r['gates'][s.name] = {'state': 'approved'}
            else:
                r['steps'][s.name] = {'done': True}
        self.assertIsNone(stages.survey(r).next)

    def test_rehearse_is_later_in_the_timeline(self):
        rows = stages.timeline(run('scratch'))
        self.assertEqual(rows[-1]['state'], 'later')
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS, then whole suite.
- [ ] **Step 5: Commit** `"Add the deck pipeline as data, with a skip map for each route and level"`

---

### Task 6: Worker briefs

**Files:**
- Create: `runner/briefs/__init__.py` (port the loader: `guidance(kind: str, **flags) -> str`), and briefs: `classify.md`, `research-plan.md` (port), `research-question.md` (port), `outline-brief.md` (from scratch), `outline-material.md`, `outline-spec.md`, `extract.md` (verbatim from inventory; freedom-specific notes keyed by level), `restructure.md` (rework), `look.md`, `section.md` (port `deck-section.md`, objectives removed), `section-repair.md` (port `deck-repair.md`), `review.md` (port `deck-review.md`), `patch.md` (selected changes as a `pptx patch` plan), `change-request.md` (what a person's note at a gate means for each step)
- Test: `tests/test_briefs.py`

**Interfaces:**
- Produces: `briefs.guidance(kind, level=None, repair=False) -> str`; `briefs.KINDS` tuple of the names above (without `.md`). Every brief names only worker tools (never a helper command or a file path), says what is handed back and under what name, and for `extract` states the verbatim rule: every title, point, caveat and note text must be copied from the inventory's text exactly (whitespace may be normalised); for `brand-only` keep each slide's relation and point count; for `polish` keep wording and order but choose a better relation; for `redesign` keep each slide's message and qualifications but design freely.

- [ ] **Step 1: Write `tests/test_briefs.py`**

```python
import re
import unittest

import helpers  # noqa: F401
from runner import briefs

TOOLS = {'list_inputs', 'read_input', 'submit_artifact', 'ask_person', 'check_outline',
         'submit_outline', 'check_section', 'preview_section', 'search_icons', 'submit_section',
         'look_at_slide', 'submit_assessment', 'search_web', 'fetch_page', 'save_source',
         'record_finding', 'check_look', 'submit_look', 'check_patch', 'submit_patch',
         'submit_classification'}


class BriefTests(unittest.TestCase):
    def test_every_kind_loads(self):
        for kind in briefs.KINDS:
            with self.subTest(kind=kind):
                self.assertGreater(len(briefs.guidance(kind)), 200)

    def test_briefs_name_only_worker_tools(self):
        for kind in briefs.KINDS:
            named = set(re.findall(r'`([a-z_]+)`', briefs.guidance(kind)))
            self.assertLessEqual({n for n in named if '_' in n}, TOOLS, kind)

    def test_no_commands_or_paths(self):
        for kind in briefs.KINDS:
            text = briefs.guidance(kind)
            self.assertNotIn('harness-slides.mjs', text, kind)
            self.assertNotRegex(text, r'(?m)^\s*node ', kind)

    def test_extract_states_the_verbatim_rule(self):
        self.assertIn('exactly', briefs.guidance('extract', level='brand-only'))

    def test_no_training_words(self):
        for kind in briefs.KINDS:
            self.assertNotRegex(briefs.guidance(kind).lower(), r'blueprint|learner|yoodli', kind)
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Write the briefs** (port the four deck briefs, removing objectives/blueprint; write the new ones in the same voice). **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `"Add the workers' briefs for decks"`

---

### Task 7: Intake steps — documents, classification, Google Docs (`steps/intake.py`)

**Files:**
- Create: `runner/steps/__init__.py`, `runner/steps/intake.py`
- Modify: `runner/worker_tools.py` (register `'classify'`)
- Test: `tests/test_step_intake.py`

**Interfaces:**
- Consumes: `documents.add/add_text/listed/text_of`, `gdrive.file_id/Drive.export_text`, `worker_tools.register/prepare`, `briefs.guidance`, `decks.read_run/write_run`.
- Produces:
  - `take_document(root, source: dict, drive=None) -> dict` — `source` from the form: `{'kind': 'upload', 'name', 'data' (bytes)}` → `documents.add`; `{'kind': 'paste', 'text'}` → `documents.add_text(root, 'Pasted text', text)`; `{'kind': 'google', 'link'}` → `drive.export_text(gdrive.file_id(link))` then `add_text`. Returns the documents entry. Refuses an unreadable document with its `problem` sentence.
  - `classify_work(root, run, request: dict | None, error: str | None) -> Work` (`Work` as in Training Studio's pipeline: `{'brief', 'task', 'inputs', 'artifacts', 'sources'}`) — inputs are the document text (parts); the artifact is `classification` of kind `'classify'`.
  - `check_classification(text, spec) -> (problems, outcomes, notes, kept_text)` — JSON `{"kind": "spec"|"material", "reason": "<one or two sentences>", "slides": <int|null>}`; `slides` required for `spec`.
  - `keep_classification(root, run, handed) -> None` — writes `classify.md` (verdict, reason, and for spec the slide count), sets `run['classified']`, sets `gates['gate:classify'] = {'state': 'waiting', 'round': n}`.
  - `correct(run, kind: 'spec'|'material') -> dict` — the person's correction at the gate: sets `classified`, rewrites `classify.md`'s verdict line ("Corrected by you"), calls `stages.reopen` so later steps are redone, and approves the gate.

- [ ] **Step 1: Write failing tests** covering: upload of `.md` kept and readable; paste kept as `pasted-text.md`; Google link with a stand-in `Drive` whose `export_text` returns text; Google link when `gcloud` is missing → `WorkspaceError` naming sign-in; classification JSON accepted for `spec` with `slides`, refused for `spec` without `slides`, refused for an unknown kind; **Review Focus 2:** a five-line bullet list classified as `material` with a reason, then `correct(run, 'spec')` switches `classified`, keeps the document entry, and `stages.steps(run)` loses the research steps:

```python
def test_correction_switches_branch_and_keeps_the_document(self):
    root, run = self.deck(route='document', research=True)
    intake.take_document(root, {'kind': 'paste', 'text': '- a\n- b\n- c\n- d\n- e\n'})
    intake.keep_classification(root, run, {'kind': 'material', 'reason': 'Short notes.',
                                           'slides': None})
    self.assertIn('research', [s.name for s in stages.steps(run)])
    run = intake.correct(run, 'spec')
    self.assertEqual(run['classified'], 'spec')
    self.assertEqual(len(documents.listed(root)), 1)
    self.assertNotIn('research', [s.name for s in stages.steps(run)])
    self.assertEqual(run['gates']['gate:classify']['state'], 'approved')
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS, whole suite.
- [ ] **Step 5: Commit** `"Take in documents and Google Docs, and classify a document as a spec or material"`

---

### Task 8: Outline steps (`steps/outline.py`)

**Files:**
- Create: `runner/steps/outline.py`
- Modify: `runner/worker_tools.py` (outline validator takes `'rules'`)
- Test: `tests/test_step_outline.py`

**Interfaces:**
- Consumes: `slides.outline_check/outline_contract/outline_draft`, `documents.text_of`, research report (`research/report.md`), `classify.md`, the inventory (`classify.json` from Task 9), `briefs.guidance`.
- Produces:
  - `OUTLINE = 'outline.json'` (shared; harness-slides outline v1), `OUTLINE_MD = 'outline.md'` (shared, readable rendering: one `## n. Title` per slide with understand/points/notes).
  - `outline_work(root, run, request, error, brand: Path) -> Work` — chooses the brief: `outline-brief` (scratch), `outline-material` / `outline-spec` (document), `restructure` (existing rework); inputs: intake, document text, research report if any, the current outline and the person's note on a second round.
  - `extract_work(root, run, request, error, brand) -> Work` — `extract` brief with the level; inputs: the inventory text per slide.
  - `verbatim_rule(inventory: dict) -> Callable[[dict], list[str]]` — every text in the outline (title, subtitle, detail, understand is exempt, points' label/text, caveat, source, notes) must appear in the inventory's slide texts after whitespace normalisation; returns one sentence per offending string naming the slide.
  - `count_rule(inventory, level) -> Callable` — for `brand-only` and `polish`: same number of slides, same order (each outline slide carries `sources: ['slide-<n>']`).
  - `keep_outline(root, run, handed) -> None` — writes `outline.json`, `outline.md`, sets `gates['gate:outline']` waiting (not for `extract` on brand-only/polish/redesign, which have no outline gate).
  - `apply_edits(root, run, edited: list[dict]) -> None` — the page's editable outline (reorder, add, remove, retitle) saved back into `outline.json` and re-checked with `outline check`; refusals come back as sentences.

- [ ] **Step 1: Write failing tests** — each route picks the right brief; `verbatim_rule` passes copied text and refuses `"Run Tanzu faster"` when the inventory says `"Run Tanzu fast"` (**Review Focus 5**: an outline handed back by the stand-in worker with one changed word is refused by `worker_tools` before it is kept, and the step's second try carries the sentence); `count_rule` refuses a dropped slide for `polish`; `apply_edits` reorders two slides and `outline.md` follows.
- [ ] **Step 2–4:** FAIL → implement → PASS, whole suite.
- [ ] **Step 5: Commit** `"Write, extract and restructure outlines, with the verbatim rule for redesigns"`

---

### Task 9: Existing decks — fetch, inventory, pictures, selected changes (`steps/existing.py`)

**Files:**
- Create: `runner/steps/existing.py`
- Modify: `runner/worker_tools.py` (register `'patch'`)
- Test: `tests/test_step_existing.py`

**Interfaces:**
- Consumes: `slides.drive_export/pptx_inspect/pictures_of/pptx_patch/pptx_compare/drive_check`.
- Produces:
  - `SOURCE = 'sources/original.pptx'` (never shared); `INVENTORY = 'classify.json'` (shared: the inspect JSON minus `box`/hashes it does not need, plus `sha256` and source name); `ORIGINAL_SHOTS = 'work/original'`.
  - `fetch(root, source: dict, slides, google_ready: bool) -> Path` — upload: write bytes to `SOURCE` after checking the `PK\x03\x04` signature and a 100 MB limit; google: refuse with `"Sign in to Google on the Check this computer screen, or download the deck as .pptx and upload it."` when `google_ready` is false (**Review Focus 1**: the test asserts nothing is written under the deck folder), else `slides.drive_export`.
  - `inventory(root, run, slides, renderer) -> dict` — `pptx_inspect`, writes `classify.json` and `classify.md` (a table: slide number, title, word count), renders `pictures_of` into `ORIGINAL_SHOTS`, sets `gates['gate:classify']` waiting.
  - `patch_work(root, run, request, error) -> Work` — `patch` brief; inputs: the inventory of the slides the person named and their `selected` text; artifact kind `'patch'`.
  - `check_patch(text, spec) -> (...)` — JSON patch `{sourceSha256, operations:[{slide, object, expectedHash, text|runs|alt|title}]}`; refuses operations on slides the person did not name, unknown object IDs, wrong `expectedHash`, wrong `sourceSha256`.
  - `apply_patch(root, run, slides) -> Path` — `pptx_patch` to `work/patched.pptx`, `pptx_compare` with an allow list built from the operations; a failed compare refuses delivery with the tool's lines.
  - `pairs(root, run) -> list[dict]` — before/after per slide number for `brand-only`, `polish`, `redesign`, `selected` (`{'number', 'before': image path, 'after': image path | None}`); `[]` for `rework`.

- [ ] **Step 1: Write failing tests** for: upload with a bad signature refused; Google with `google_ready=False` refused and folder unchanged (Review Focus 1); inventory writes `classify.json` and pictures; `check_patch` refuses an unnamed slide and a wrong hash; `apply_patch` produces `work/patched.pptx` through the stand-in; `pairs` lines up numbers.
- [ ] **Step 2–4:** FAIL → implement → PASS, whole suite.
- [ ] **Step 5: Commit** `"Bring in existing decks: fetch, inventory, pictures and selected changes"`

---

### Task 10: Brand, look, build and delivery (`steps/look.py`, `steps/build.py`, `steps/deliver.py`)

**Files:**
- Create: `runner/steps/look.py`, `runner/steps/deliver.py`; complete `runner/steps/build.py` (pure helpers already moved there in Task 3)
- Modify: `runner/worker_tools.py` (register `'look'`)
- Test: `tests/test_step_look.py`, `tests/test_step_build.py`, `tests/test_step_deliver.py`

**Interfaces:**
- Consumes: `brand.Brand.export(...)` (port name as in Training Studio `runner/brand.py`), `slides.outline_start/compose_contract/layouts/compile/merge/preview/critique/render/drive_import/drive_check`, `worker_tools` deck tools, `steps.outline.OUTLINE`, `steps.existing.pairs`.
- Produces:
  - `build.export_brand(root, run, brand_skill) -> Path` — `brand/brand-contract.json`, `DESIGN.md`, `VOICE.md`, `brand/version.txt`; reused if the brand version is unchanged, otherwise the deck stops with "The brand changed since this deck began…" (Training Studio's rule).
  - `look.look_work(root, run, request, error, brand) -> Work` — `look` brief; inputs: outline, layouts, compose contract; artifact kind `'look'`: `{"options": [{"name", "direction": {focal, neutral, meanings?, motif?}, "why", "composition": <single-slide composition for the outline's first content slide>}]}` with 2 or 3 options.
  - `look.preview_options(root, run, slides, renderer) -> list[dict]` — compiles and previews each option into `work/look/<n>/`, returns `[{'name','why','image'}]`; writes `look.md` (shared) listing the options; sets `gates['gate:look']` waiting.
  - `look.choose(root, run, name) -> None` — records `look.json` `{chosen, direction, why}`, writes the direction and the person's words into `outline.json` (`direction`, `approval`), approves the gate.
  - `build.start(root, run, slides, brand) -> dict` — `outline start` into `work/build/start/`; for existing levels adds the freedom's house lines (`brand-only`: "Keep each slide's composition as close to the original as the brand's layouts allow. Add no icons.", `polish`: "Keep wording and order; improve spacing, alignment and composition.", `redesign`: "Design each slide again from its content; keep its message and qualifications.").
  - `build.section_work(root, run, section, request, error) -> Work`, `build.whole(root, run, slides, renderer) -> dict` (merge, compile, preview into `work/build/preview/`, contact sheet copied to the shared `contact-sheet.png`), `build.review_work(root, run) -> Work`, `build.keep_review(root, run, handed) -> list[dict]` (findings; drawing findings major/critical → sections to repair, at most 2 rounds), `build.repair_sections(found) -> list[str]`, `build.render(root, run, slides) -> Path` (`work/deck.pptx`; for `selected` the patched deck).
  - `build.gate_view(root, run) -> dict` — `{'slides': [{'number','title','image','findings'}], 'contactSheet', 'pairs': existing.pairs(...), 'changed': [numbers re-rendered since the last round], 'audit': tanzu-brand presentation audit summary}`; sets `gates['gate:build']` waiting.
  - `deliver.deliver(root, run, slides) -> dict` — output `google`: `slides.drive_import(deck, title)` → `{'fileId','url'}`; output `pptx` (or Google not reachable → pptx with the sentence "Google isn't connected, so this deck was made as a PowerPoint file."): `deck.pptx` kept under `work/` and offered for download; writes `deliver.json` `{'output','url','fileId','pptx','revision','at'}`, appends to `run['revisions']`, rewrites `README.md` and the index.
  - `deliver.again(root, run, slides, note) -> dict` — "Ask for changes" on a finished deck: reopens `gate:build` with the note; on the next delivery a missing earlier Google file is not an error — a new file is imported and `deliver.json` records the new link (**Review Focus 3**: test with a stand-in whose `drive_import` is called again after the earlier file ID is reported missing).

- [ ] **Step 1: Write failing tests** for: brand reuse vs brand changed; look with 1 option refused, with 3 accepted; `preview_options` writes three pictures; `choose` writes direction into `outline.json`; freedom house lines per level in `start`; review → repair limited to two rounds; `gate_view` includes pairs for `polish` and none for `rework`; deliver google vs pptx fallback; Review Focus 3.
- [ ] **Step 2–4:** FAIL → implement (port the build loop from Training Studio `runner/pipeline.py` lines 1491–2280 and `runner/engine.py` deck steps, using the non-design path: no `design propose/respond`) → PASS, whole suite.
- [ ] **Step 5: Commit** `"Add the look, the build loop and delivery"`

---

### Task 11: The engine

**Files:**
- Create: `runner/engine.py`
- Test: `tests/test_engine.py`, `tests/test_engine_team.py` (port the claim/take-over/hand-over/clash cases from Training Studio's `test_runner_engine.py` and `test_runner_team.py`)

**Interfaces:**
- Consumes: everything above.
- Produces (names kept from Training Studio where the meaning is the same):
  - `Engine(adapters=None, research=None, slides=None, brand=None, drive=None, background=True)`
  - `start(form: dict, uploads: dict[str, bytes] | None = None) -> dict` → `{'path','id'}`; claims the deck before work in a shared workspace.
  - `resume(wait=True)`, `view(path) -> dict` (`{'id','title','route','level','state','sentence','timeline','gate': gate payload | None,'driver','mine','notice','deliver','spent','queue'}`), `decks() -> dict` (`needs`, `working`, `finished`, `elsewhere`).
  - `decide(path, gate, decision: 'approve'|'changes', note: str|None, extra: dict|None) -> dict` — the only way a gate moves: records `{'state','note','at','by'}`, applies gate-specific extras (`classify`: `{'kind'}` correction; `look`: `{'choice'}`; `outline`: `{'edited': [...]}`; `build`: `{'slides': [numbers]}` per-slide notes), commits `"<title>: <decision> the <gate words>"`, shares if `share == 'decision'`, wakes the run.
  - `act(path, 'pause'|'resume'|'stop'|'retry'|'undo')`, `answer(path, question_id, text)`, `picture(path, kind: 'build'|'look'|'original', number|name) -> bytes`, `download(path) -> (name, bytes)` for the `.pptx`.
  - `drive(path, 'take'|'hand-over')`, `hold(path)`, `share()`, `fetch()`, `publish(path)`, `published()`, `leaving(path)`, `delete(path, title)`, `standing()`, `serving()`, `close()` — ported.
  - `deck_needs() -> dict` — what this computer has: slides tool/version, brand skill/brands, local/drive previews, Google sign-in, research tool.
  - Step dispatch: a table `RUN = {'intake-source': ..., 'classify': ..., ...}` mapping each `stages.PIPELINE` name to a function in `steps/*`; agent steps go through one `_job(path, work)` that prepares a worker folder, runs the adapter, collects, retries up to 3 times with the reason, honours limits and questions (port).
- [ ] **Step 1: Write failing tests** using `runner_support`'s scripted workers and stand-ins: (a) a scratch deck runs to `gate:outline` and waits; `decide(approve)` moves it to `gate:look`; choosing an option moves to `gate:build`; approving delivers and the state is `finished`; every decision is a commit (`git log` count). (b) `changes` at `gate:outline` reruns `outline` with the note in the task. (c) agent failure three times halts with the sentence; `retry` resumes. (d) a deck someone else drives answers `hold` with who has it. (e) **Review Focus 4**: two workspaces cloned from one remote both `start` "Same Title" before either shares; after both share, the remote has `same-title` and `same-title-2` (or the second start is refused with the sentence naming the teammate) and no folder contains both run records.
- [ ] **Step 2–4:** FAIL → implement → PASS, whole suite.
- [ ] **Step 5: Commit** `"Add the engine that walks each deck and stops at its gates"`

---

### Task 12: The server, setup, upkeep and command line

**Files:**
- Create (port): `skills/presentation-studio/scripts/server.py` (from `desk.py`: `Refusal`, `as_json`, `Server`, `Handler`, `Page` base with the security rules only — no training reads), `runner/page.py`, `runner/setup.py`, `runner/upkeep.py`, `runner/studio.py`
- Test (port/new): `tests/test_server_security.py` (port the desk security cases), `tests/test_runner_page.py`, `tests/test_runner_setup.py`, `tests/test_runner_upkeep.py`, `tests/test_runner_studio.py`

**Interfaces:**
- Produces the HTTP API (all JSON; key in `X-Presentation-Studio-Token`):
  - GET `/api/capabilities`, `/api/setup`, `/api/agents`, `/api/models?agent=`, `/api/decks`, `/api/run?path=`, `/api/slide?path=&kind=build|look|original&number=|name=`, `/api/download?path=` (the `.pptx`, `application/vnd.openxmlformats-officedocument.presentationml.presentation`), `/api/status`, `/api/published`, `/api/delete?path=`, `/api/file?path=&name=` (only `README.md`, `intake.md`, `classify.md`, `outline.md`, `look.md`, `research/plan.md`, `research/report.md`).
  - POST `/api/setup/check`, `/api/setup`, `/api/decks` (start: form + base64 uploads, body limit 120 MB for this address only), `/api/run` (`{path, action}`), `/api/decide` (`{path, gate, decision, note?, extra?}`), `/api/answer`, `/api/share`, `/api/fetch`, `/api/drive`, `/api/publish`, `/api/delete`, `/api/companions`, `/api/upgrade`, `/api/restart`, `/api/versions`.
  - `setup`: workspace join/local (folder `presentations`), defaults (`agent`, `model`, `name`, `brand`, `variant`, `output`, `renderer`, `share`, `limits`). `upkeep`: Presentation Studio and its three companions (harness-slides, harness-research, tanzu-brand) present and current. `studio serve [--port N] [--open]`, `studio status`.
- [ ] **Step 1: Port the security tests first** (Host check, key, POST-only changes, origin, body limit, CSP headers) and run them — FAIL. **Step 2: Port `server.py`** — PASS.
- [ ] **Step 3: Write page tests** for each address above against an `Engine` with stand-ins (start a scratch deck through `/api/decks`, read `/api/run`, decide through `/api/decide`, fetch a slide picture, download the pptx; a deck driven elsewhere answers 409 to `/api/decide`).
- [ ] **Step 4: Port `setup`, `upkeep`, `studio`** with their tests renamed; run — PASS, whole suite.
- [ ] **Step 4b: Shared studios config** (added 2026-10-14 at the user's request; issues dbbaskette/training-studio#67, dbbaskette/blog-studio#94). Create `skills/presentation-studio/scripts/studios_config.py`: `PATH = ~/.config/studios-config.json` (env `STUDIOS_CONFIG` overrides; tests set it to a temp file); `read() -> (dict, problem: str | None)` (missing → `({}, None)`; unreadable/invalid → `({}, sentence)`); `update(changes: dict) -> dict` (merged, atomic, keeps unknown keys, refuses a repository address with credentials). Schema: `{"schema": 1, "team": {"repository", "branch"}, "person": {"name"}, "assistant": {"agent", "model", "effort"}, "brand": {"brand", "variant"}, "output", "share"}`, every key optional. `setup` pre-fills the workspace address, name, agent/model/effort, brand/variant, output, share from it; `POST /api/setup` takes `"for_all_studios": true` to also write the shared values it changed; `GET /api/setup` carries `shared` (the file's values) and `shared_problem`. Tests: no file → defaults unchanged; pre-fill; write only changed keys with unknown keys preserved byte-for-byte; invalid file never blocks setup and its sentence is shown.
- [ ] **Step 5: Commit** `"Add the server, setup, upkeep and the studio command"`

---

### Task 13: The page

**Files:**
- Create: `skills/presentation-studio/scripts/desk/index.html` (from Training Studio's, sidebar: Home, Decks, Status, Settings), `style.css` and `markdown.js` (vendored unchanged, pinned in `vendor.json`), `app.js` (new)
- Create (port): `tests/page_harness.js` and `tests/test_desk.py` (node-driven DOM-free checks as in Training Studio)
- Test: `tests/test_page_app.py`

**Interfaces:**
- Consumes: the API in Task 12.
- Produces in `app.js` (port the marked sections of Training Studio's `app.js`: "small builders", "talking to the server", "pictures of slides", "the window", "the sheet", "status", "settings", "set-up", "with a team", "deleting", "versions"; write new: home, new deck, deck screen):
  - **Set-up**: Check this computer (with Fix it), Workspace (join team repo / just this computer), Defaults.
  - **Home**: Needs you · In progress · Finished (Slides link + contact-sheet thumbnail) · Run by your teammates.
  - **New deck**: three route cards → a two- or three-step form per route; existing-deck level as five cards with one-line examples; uploads read with `FileReader` and sent base64.
  - **Deck screen**: stage timeline (`done`/`current`/`upcoming`/`later` with "Coming later" on Rehearse with Yoodli), and the gate panel: classify (verdict + "That's wrong" switch, or original slide pictures), research (plan/report markdown), outline (editable list: retitle, reorder up/down, add, remove; save sends `extra.edited`), look (2–3 rendered options, click to choose), build (slide pager, contact sheet, per-slide findings and notes, before/after pairs, changed-slide markers), deliver (Open in Google Slides, Download .pptx, revisions). Controls: Approve, Ask for changes (text), Pause, Stop, Undo.
- [ ] **Step 1: Write `tests/test_page_app.py`** — static checks: every API path `app.js` calls is in the server's READS/WRITES; no external URL other than links the server returned; no `innerHTML` with server text (port Training Studio's rule); the words "artifact", "stale", "lineage" absent; "Coming later" present for Yoodli.
- [ ] **Step 2: Run** — FAIL. **Step 3: Write the page.** **Step 4: Run** — PASS; start `studio serve` against a stand-in engine (`PRESENTATION_STUDIO_FAKE=1` wiring in `studio.py` used only by tests and the visual check) and check each screen renders with no console errors.
- [ ] **Step 5: Commit** `"Add the page: set-up, home, new deck, and the deck screen with its slide viewer"`

---

### Task 13b: Any brand — the brand skill is an input (added 2026-10-14 at the user's request)

Presentation Studio is for any brand. The brand skill, and the repository it is installed from, is an input the person gives; nothing in the product names, defaults to or pins a particular brand.

**Files:**
- Port, the same way in all three studios (Training Studio is the source; Blog Studio is vendoring the same files as `studio_brand/` from `training-studio` at `0881ce7`): from `training-studio` `origin/main` at `0881ce768039ebeb9e1fa39b89cedf792bf5d40e`, the brand-skill-repository feature of its PR #66 (`87981a0`): `runner/brand_source.py` (a brand skill's repository: its releases, fetching one by tag and commit, running its own installer) and `runner/brand.py`'s current form; `brand_repository` / `brand_release` in `runner/settings.py` with `check_repository` / `check_release`; `setup.save_brand`; `upkeep.install_brand` and `upkeep` reporting `versions.brand`; `POST /api/brand` `{repository, release}` and `POST /api/brand/install` `{release}` (409 while a deck is working or anything else is in hand, or when the release is not the one shown) in `runner/page.py`; the Settings and Versions parts of the page that name the repository and release and install/upgrade it; their tests; the docs wording. Record each in `vendor.json` with revision `0881ce7`.
- Modify: every file that names Tanzu (`git grep -n -i tanzu`): `runner/settings.py`, `runner/upkeep.py`, `runner/__init__.py`, `vendor.json`, all tests and stand-ins (use a neutral stand-in brand, e.g. `acme` with variants `light`/`dark`), `README.md`, `docs/superpowers/specs/…-design.md` (add a dated "Amendment: any brand" note at the top and neutralise the text), this plan's text, `AGENTS.md`.
- The brand skill's repository and release are shared values: see Task 13c.

**Rules:**
- No brand literal in product code. The default brand and variant are the first the installed brand skill lists, unless Settings or the studios config name one.
- Companions pinned by the installer are harness-slides and harness-research only. The brand skill is installed from the repository and release named in Settings, by its own installer, exactly as Training Studio does; the pinned companions are left alone.
- Without a brand skill, everything up to the brand step works; the deck stops at `brand` with one sentence saying to name the brand skill's repository in Settings.
- Person-facing words say "your brand" / "the brand skill", never a brand's name.

- [ ] **Step 1:** Port `brand_source` + settings + `/api/brand` + setup/upkeep brand-skill parts with their tests — PASS.
- [ ] **Step 2:** Neutralise every Tanzu mention found by `git grep -n -i tanzu` (code, tests, docs); add `test_no_brand_named.py` asserting `git grep -i tanzu` over tracked files outside `vendor.json`'s recorded upstream notes finds nothing.
- [ ] **Step 3:** Whole suite — PASS. Commit `"Make Presentation Studio brand-neutral: the brand skill is an input"`.

### Task 13c: The studios config is the single source of truth for shared values (added 2026-10-14 at the user's request)

Issues dbbaskette/training-studio#70 and dbbaskette/blog-studio#96 describe the convention all three studios adopt.

**Rules:**
- Shared values live only in `~/.config/studios-config.json` (`STUDIOS_CONFIG` overrides): `team.repository`, `team.branch`, `person.name`, `assistant.agent|model|effort`, `brand.repository|release|brand|variant`, `output`, `share`. The runner reads them from that file every time it needs them (a short cache is fine) and keeps no copy in its own settings. There is no "for all studios" flag: saving one of these in setup/Settings writes the shared file (merged, atomic, only changed members, unknown keys and bytes preserved, credentials refused; `brand.repository`/`brand.release` checked with `check_repository`/`check_release`).
- Per-studio settings (limits, preview renderer, concurrent runs, anything only Presentation Studio uses) stay in its own settings file.
- An unreadable shared file: the studio works on built-in defaults, says so in one sentence on setup and status, refuses to save a shared value until it is readable, and never overwrites it.
- Migration: on start, shared values found in this studio's own settings file are written into the shared file where it lacks them, then removed from the own file; values the shared file already has are left as they are and the person is told once.
- The workspace (team repository and branch) a studio has joined is a clone under its own data folder; which repository and branch to use is the shared value.

**Files:** `skills/presentation-studio/scripts/studios_config.py` (brand repository/release members, schema validation), `runner/settings.py` (shared fields removed from the own settings; accessors that read the shared file), `runner/setup.py` (no `for_all_studios`; save shared values to the shared file; migration), `runner/page.py` (GET/POST `/api/setup` and `/api/brand` contract updated; docstring), the page's setup/Settings screens (no "for all studios" toggle; one sentence saying these are shared by every studio), tests for each, docs (`docs/runner.md` shared-values section; README "Shared settings").

- [ ] **Step 1:** Tests first: shared values read only from the file; saving writes the file and a second Settings read (and a fresh studios_config read) sees it; brand repository/release accepted, checked, preserved; per-studio settings unaffected; unreadable file → defaults, sentence, save refused, file untouched; migration moves own copies without overwriting. Run — FAIL.
- [ ] **Step 2:** Implement; run — PASS; whole suite — PASS.
- [ ] **Step 3:** Commit `"Keep shared values only in the studios config, the brand skill's repository and release among them"`.

---

### Task 14: Installer, companions, chat skill and docs

**Files:**
- Create (port): `installer/install.sh`, `installer/install.py`, `installer/Install Presentation Studio.command`, `bootstrap/presentation-studio/SKILL.md`
- Create: `installer/companions.json` pinning harness-research `0.8.0` (`547506e9ba5b0d848267033886624d6cea75c365`, sha256 from Training Studio's pins), harness-slides `0.14.1` (commit `79eaf89f39ae5ba7b11f345a2f018833b53bbc59`, sha256 computed with `install.py`'s `tree_digest` of that revision). No brand skill is pinned: it is installed from the repository the person gives (Task 13b).
- Create: `skills/presentation-studio/SKILL.md`, `references/routes.md`, `references/levels.md`, `references/workspace.md`, `README.md`, `AGENTS.md` (Presentation Studio's working agreements), `docs/runner.md`, `docs/development.md`, `docs/acceptance.md`
- Test (port): `tests/test_installer.py`, `tests/test_package.py` (package contents, SKILL.md links resolve, budgets)

**Interfaces:**
- Produces: `sh installer/install.sh` installs to `~/.local/share/presentation-studio/` with the `studio` launcher and `Open Presentation Studio.command`; registers the bootstrap skill for Claude Code and Codex; brings the three companions at their pins when agreed.
- [ ] **Step 1: Port installer tests** with the new names; run — FAIL. **Step 2: Port the installer and write `companions.json`** (compute sha256 values by running the ported `tree_digest` on fresh clones at the pinned commits). **Step 3: Write SKILL.md** (chat use: the three routes, the five levels, the folder layout, and that decks are made with harness-slides plus a tanzu-brand contract; links every reference) and the docs. **Step 4: Run** installer and package tests, then the whole suite — PASS.
- [ ] **Step 5: Commit** `"Add the installer, the pinned companions, the chat skill and the docs"`

---

### Task 15: End-to-end routes and acceptance

**Files:**
- Create: `tests/test_flow_routes.py`
- Modify: `docs/acceptance.md`

- [ ] **Step 1: Write one end-to-end test per route and per existing level** through the page API with stand-ins and scripted workers: scratch (with and without research), document-spec, document-material (with a classify correction), existing brand-only, polish, redesign, rework, selected. Each asserts the gate sequence matches `stages.steps`, a `deliver.json` with a link exists, `contact-sheet.png` is committed, nothing under `sources/` or `work/` is tracked by git, and the commit log has one commit per decision.
- [ ] **Step 2: Run** — fix any defects found in the owning modules (not the tests' intent) until PASS; run the whole suite.
- [ ] **Step 3: Manual acceptance** (recorded in `docs/acceptance.md`): install harness-slides, harness-research and tanzu-brand from the local checkouts into a disposable home (`HOME=$(mktemp -d)`), run `studio serve` against a disposable workspace, and walk a scratch deck and a Brand-only redesign of `tanzu-brand/assets/presentations/tanzu-presentation-template.pptx` as far as this computer allows (LibreOffice/Google may be absent — record exactly where it stopped and the sentence the page showed).
- [ ] **Step 4: Commit** `"Add end-to-end route tests and the acceptance record"`
