"""Shared setup for the runner's tests: its import path, a job folder, a pretend web,
processes a test started, and small stand-ins for the slides tool and a brand skill behind
their wrappers; the engine's stand-ins (scripted workers, a person and a team); and
`fake_studio`, the same engine for a process, which `studio serve --fake` serves for tests
and the page's visual check."""
import hashlib
import json
import os
import signal
import struct
import sys
import tempfile
import threading
import time
import unittest
import zlib
from pathlib import Path

import helpers

sys.path.insert(0, str(helpers.REPO))

from runner import worker_tools  # noqa: E402

PUBLIC = '93.184.216.34'    # an address on the public internet; nothing ever connects to it
PLAN = {'topic': 'Rolling restarts', 'items': [
    {'id': 'instance-min', 'question': 'How many instances keep capacity during a restart?',
     'public_query': 'rolling restart minimum instances'},
    {'id': 'health-checks', 'question': 'What starts the next batch?',
     'public_query': 'rolling restart health check batch'}]}
PAGE = """<html><head><title>Rolling  restarts</title><style>p {color: red}</style></head>
<body><script>var hidden = 1;</script>
<h1>Rolling restarts</h1>
<p>A rolling restart replaces instances one batch at a time, so the app keeps serving
traffic while it restarts.</p>
<p>Capacity holds only when more than one instance is running. The platform’s health
check decides when the next batch starts.</p>
</body></html>"""


class Web:
    """A pretend web: what each address answers, and the addresses each host name has."""

    def __init__(self):
        self.pages, self.hosts, self.asked = {}, {}, []

    def page(self, url: str, body, kind: str | None = 'text/html; charset=utf-8',
             status: int = 200, headers: dict | None = None, addresses=(PUBLIC,)) -> str:
        host = url.split('/')[2].rpartition('@')[2].partition(':')[0]
        self.hosts.setdefault(host, list(addresses))
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.pages[url] = (status, {**({'content-type': kind} if kind else {}),
                                    **(headers or {})}, data)
        return url

    def resolver(self, host: str) -> list[str]:
        if host not in self.hosts:
            raise OSError('Name or service not known')
        return self.hosts[host]

    def opener(self, url: str, address: str, limit: int):
        self.asked.append((url, address))
        answer = self.pages[url]
        if isinstance(answer, Exception):
            raise answer
        status, headers, data = answer
        return status, headers, data[:limit + 1]


class JobCase(unittest.TestCase):
    """A test with an empty folder for one job at self.job, and a pretend web."""

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        self.job = self.base / 'job'
        self.web = Web()

    def tools(self, **prepared) -> worker_tools.WorkerTools:
        """Prepare the job, when anything to prepare is given, and return its tools."""
        if prepared or not (self.job / 'job.json').exists():
            worker_tools.prepare(self.job, **prepared)
        return worker_tools.WorkerTools(self.job, opener=self.web.opener,
                                        resolver=self.web.resolver,
                                        pdf=lambda path: 'Text of the PDF.\n')

    def ok(self, outcome) -> str:
        self.assertTrue(outcome[0], outcome[1])
        return outcome[1]

    def refused(self, outcome) -> str:
        self.assertFalse(outcome[0], outcome[1])
        return outcome[1]


class DeckCase(unittest.TestCase):
    """A test with an empty deck folder at self.root: one that holds a run record."""

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / 'deck'
        self.root.mkdir()
        (self.root / 'run.json').write_text('{}\n', encoding='utf-8')

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path


# --- processes a test started ------------------------------------------------------------

# A command that leaves a sleep behind holding its output open, writes its own process ID
# and the sleep's to the file it is given, and waits.
LEAVES = ('sleep 300 &\nprintf "%s\\n%s\\n" $$ $! > "$1.part" && mv "$1.part" "$1"\n'
          'sleep 300\n')


def gone(pid: int) -> bool:
    """True when a process has ended, whether or not anything has collected it yet."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    try:
        state = Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()[0]
    except (OSError, IndexError):
        return False
    return state == 'Z'


def still_running(pids, seconds: float = 5) -> list[int]:
    """Those of `pids` still running after up to `seconds`. Each is killed then, so that
    no test leaves a process behind whatever it finds."""
    deadline = time.monotonic() + seconds
    while True:
        left = [pid for pid in pids if not gone(pid)]
        if not left or time.monotonic() >= deadline:
            break
        time.sleep(0.05)
    for pid in left:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return left


def written(path: Path, seconds: float = 10) -> list[int]:
    """The process IDs a command writes to a file, one a line, once it has written them."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            text = path.read_text()
        except OSError:
            text = ''
        if text.endswith('\n'):
            return [int(line) for line in text.split()]
        time.sleep(0.02)
    raise AssertionError(f'Nothing was written to {path}.')




# --- a deck's tools, with nothing real behind them ----------------------------------------

OUTLINE = {'version': 1, 'title': 'Rolling restarts', 'delivery': 'reading', 'minutes': 25, 'slides': [
    {'id': 'cover-restarts', 'kind': 'cover', 'title': 'Rolling restarts',
     'subtitle': 'What they do, and when capacity holds',
     'notes': '1 min. Welcome, and what is assumed.'},
    {'id': 'what-it-does', 'kind': 'content', 'relation': 'order', 'focal': 'One batch at a time',
     'title': 'A rolling restart replaces instances one batch at a time',
     'understand': 'Instances are replaced in batches while the app keeps serving.',
     'points': [{'label': 'Batch', 'text': 'Instances are replaced one batch at a time.'},
                {'label': 'Traffic', 'text': 'The app keeps serving while it restarts.'}],
     'source': 'Platform documentation: restarts',
     'notes': '6 min. Walk the three-instance example.', 'sources': ['O1']},
    {'id': 'when-capacity-holds', 'kind': 'content', 'relation': 'contrast',
     'focal': 'More than one instance',
     'title': 'Capacity holds only with more than one instance',
     'understand': 'A single instance has nothing to hold capacity while it restarts.',
     'points': [{'label': 'Several', 'text': 'The others carry the load.'},
                {'label': 'One', 'text': 'Requests are dropped while it restarts.'}],
     'caveat': 'A single-instance app still drops requests while it restarts.',
     'notes': '7 min. Health checks start the next batch.', 'sources': ['O2']},
    {'id': 'the-objection', 'kind': 'content', 'relation': 'contrast', 'rhythm': 'breathing',
     'focal': 'It depends on the instance count',
     'title': 'Rolling does not always mean zero downtime',
     'understand': 'The claim is true only for an app with several instances.',
     'points': [{'label': 'Claim', 'text': 'Rolling always means zero downtime.'},
                {'label': 'Correction', 'text': 'Only with more than one instance.'}],
     'notes': '7 min. Correct the claim without dismissing the customer.', 'sources': ['O3']},
    {'id': 'check-yourself', 'kind': 'content', 'relation': 'order', 'focal': 'Say it aloud',
     'title': 'Check what you can now explain',
     'understand': 'Each question checks one point.',
     'points': [{'label': 'Describe', 'text': 'What happens to the instances?'},
                {'label': 'Explain', 'text': 'Why does one instance lose capacity?'}],
     'notes': '3 min. One question for each point.', 'sources': ['O1', 'O2', 'O3']},
    {'id': 'closing-practice', 'kind': 'closing', 'title': 'Next: try it on a test app',
     'notes': '1 min. Point to the sandbox.'}]}


def judgements(packets: list[dict], issues=()) -> list[dict]:
    """A reviewer's answer to a review against the design: a pass for every criterion of
    every slide, each with a reason of its own, except those `issues` gives, each as
    {'slide', 'criterion', 'severity', 'about', 'reason', 'fix'?}."""
    raised = {(issue['slide'], issue['criterion']): issue for issue in issues}
    made = []
    for packet in packets:
        prompt, checks = packet['slide'], []
        for criterion in prompt['criteria']:
            issue = raised.get((prompt['slide'], criterion['id']))
            cites = list(prompt.get('proseCards') or prompt['objects'])[:1]
            checks.append({'criterion': criterion['id'], 'status': 'pass',
                           'reason': f"On {prompt['slide']}, {criterion['id']} holds: "
                                     f"{prompt['title']}.", 'objects': cites}
                          if issue is None else {
                              'criterion': criterion['id'],
                              'status': issue.get('status', 'issue'), 'objects': cites,
                              **{key: issue[key] for key in ('severity', 'about', 'reason',
                                                             'fix') if key in issue}})
        made.append({'slide': prompt['slide'], 'checks': checks})
    return made


def png(shade: int = 0) -> bytes:
    """A real PNG, one pixel across, in a shade of grey that tells one from another."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data)))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes([0, shade % 256]))) + chunk(b'IEND', b''))


def drawn(spec: dict, wording=None, placing=None) -> dict:
    """A section as a composer would hand it in: every approved word, plainly stacked, and
    each approved intent copied. `wording` changes a piece of text on its way to the slide,
    and `placing` adds nodes below the words of a slide, by its ID."""
    wording, slides = wording or (lambda text: text), []
    for slide in spec['slides']:
        stem = f"{spec['prefix']}{slide['id'].replace('-', '_')}"
        texts = [{'type': 'text', 'id': f'{stem}_{mark}{number}', 'text': wording(point[key]),
                  **({'textRole': 'label'} if key == 'label' else {})}
                 for number, point in enumerate(slide['points'], start=1)
                 for mark, key in (('h', 'label'), ('t', 'text'))]
        made = {'id': slide['id'], 'title': slide['title'], 'sources': slide['sources'],
                'brief': {'relation': 'order', 'focal': f'{stem}_t1', 'rhythm': 'anchor'},
                'canvas': {'type': 'stack', 'direction': 'column', 'children': [
                    *texts, *(placing or {}).get(slide['id'], ())]},
                'notes': slide['notes']}
        made.update({key: slide[key] for key in ('caveat', 'source') if slide[key]})
        made.update({'intent': json.loads(slide['intent'])} if 'intent' in slide else {})
        slides.append(made)
    return {'version': 1, 'title': spec['title'], 'direction': spec['direction'],
            'slides': slides}


class Slides:
    """Stands in for the slides tool's wrapper, by the docstring of `runner.slides`. It
    writes what the tool writes, small: an outline's split into sections of two slides
    with the brief the tool writes for each, a scene, a deck that begins as a PowerPoint
    file does, and a real PNG for each slide. `refuse` maps a call to the lines it says
    no with. It takes no turn of its own at previewing, so `most` says how many previews
    were ever under way at once."""
    VERSION = '0.13.1'
    runtime = Path('/opt/slides-tool/versions/0.13.1')
    READING = {'design guidance': 'Design from the claim in the title.\n',
               'composition guidance': 'A canvas holds stacks, boxes and text.\n',
               'drafting guidance': 'One claim a slide.\n',
               'gallery': 'One drawn slide for each relation.\n',
               'example order': '{"brief": {"relation": "order"}}\n',
               'example contrast': '{"brief": {"relation": "contrast"}}\n'}
    LAYOUTS = [{'name': 'Closing words', 'title': False, 'subtitles': 0, 'pictures': 0},
               {'name': 'Picture and title', 'title': True, 'subtitles': 1, 'pictures': 1},
               {'name': 'Title slide', 'title': True, 'subtitles': 1, 'pictures': 0},
               {'name': 'Section divider', 'title': True, 'subtitles': 0, 'pictures': 0},
               {'name': 'Closing with title', 'title': True, 'subtitles': 0, 'pictures': 0}]

    def __init__(self):
        self.calls, self.refuse, self.findings, self.files = [], {}, {}, []
        # What the computer has beside this tool: LibreOffice, Google access that reaches
        # Drive, and the programs that turn a render into pictures.
        self.have = {'local': False, 'drive': True, 'pictures': True}
        self.budget, self.busy, self.most, self.counting = 90, 0, 0, threading.Lock()
        self.imported, self.took = [], 0.01

    def _asked(self, name: str, *given) -> None:
        from runner import slides
        self.calls.append((name, *(str(item) for item in given)))
        if name in self.refuse:
            raise slides.Refused(list(self.refuse[name]))

    def _new(self, path) -> Path:
        from runner import slides
        if Path(path).exists():
            raise slides.Refused([f'{Path(path).name} is already there. Give a new place.'])
        return Path(path)

    @staticmethod
    def _read(path) -> dict:
        return json.loads(Path(path).read_text(encoding='utf-8'))

    def version(self) -> str:
        return self.VERSION

    def reading(self, brand=None) -> dict:
        self._asked('reading')
        return dict(self.READING)

    def outline_contract(self, brand) -> str:
        self._asked('outline_contract', brand)
        return f'An outline is one JSON object. A slide holds at most {self.budget} words.\n'

    def compose_contract(self, brand) -> str:
        self._asked('compose_contract', brand)
        return 'A section is one JSON object. Its roles are label and body.\n'

    def layouts(self, brand) -> dict:
        self._asked('layouts', brand)
        return {'default': 'canvas', 'layouts': [dict(layout) for layout in self.LAYOUTS]}

    def outline_check(self, outline, brand) -> dict:
        from runner import slides as tool
        self._asked('outline_check', outline, brand)
        given = self._read(outline)
        if not isinstance(given, dict):
            raise tool.Refused(['The outline must be a JSON object.'])
        slides, delivery = given['slides'], given.get('delivery') or 'reading'
        # As the tool does: notes only for a content slide presented live, and a run of four
        # or more dense content slides in a row.
        found = [{'slide': slide['id'], 'code': 'no-notes', 'detail': 'It has no notes.'}
                 for slide in slides if delivery == 'live' and slide.get('kind') == 'content'
                 and not slide.get('notes')]
        run = []
        for slide in [*slides, {'kind': 'end'}]:
            if slide.get('kind') == 'content' and slide.get('rhythm', 'dense') == 'dense':
                run.append(slide['id'])
                continue
            if len(run) >= 4:
                found.append({'slide': run[3], 'code': 'dense-run',
                              'detail': f'{len(run)} dense slides in a row from {run[0]}.'})
            run = []
        words = {slide['id']: sum(len(f"{point['label']} {point['text']}".split())
                                  for point in slide.get('points') or ())
                 for slide in slides}
        found += [{'slide': ident, 'code': 'over-budget',
                   'detail': f'{count} words against {self.budget}.'}
                  for ident, count in words.items() if count > self.budget]
        return {'status': 'findings' if found else 'ok', 'slides': len(slides),
                'delivery': delivery, 'wordBudget': self.budget, 'words': words,
                'findings': found}

    def outline_start(self, outline, brand, folder) -> dict:
        from runner import slides
        self._asked('outline_start', outline, brand, folder)
        whole, folder = self._read(outline), self._new(folder)
        named = {layout['name'] for layout in self.LAYOUTS}
        for slide in whole['slides']:
            wanted = (whole.get('layouts') or {}).get(slide['kind'])
            if slide['kind'] != 'content' and wanted not in named:
                raise slides.Refused([f"There is no layout for a {slide['kind']} slide."])
        if not whole.get('direction'):
            raise slides.Refused(['The outline has no direction.'])
        (folder / 'briefs').mkdir(parents=True)
        parts, run, leads = [], [], 0

        def section() -> None:
            number = sum(part.startswith('section') for part in parts) + 1
            parts.append(f'section-{number}.json')
            (folder / 'briefs' / f'section-{number}.md').write_text(
                self._brief(whole, number, list(run), brand, folder), encoding='utf-8')
            run.clear()

        for slide in whole['slides']:
            if slide['kind'] == 'content':
                run.append(slide)
                if len(run) == 2:
                    section()
                continue
            if run:
                section()
            leads += 1
            parts.append(f'lead-{leads}.json')
            lead = {key: slide[key] for key in ('id', 'title', 'subtitle', 'detail', 'notes')
                    if key in slide}
            (folder / parts[-1]).write_text(json.dumps({
                'version': 1, 'title': whole['title'], 'direction': whole['direction'],
                'slides': [{**lead, 'layout': whole['layouts'][slide['kind']],
                            'sources': ['outline'], 'brief': {'rhythm': 'anchor'}}]}))
        if run:
            section()
        (folder / 'outline.json').write_text(json.dumps(whole))
        (folder / 'parts.json').write_text(json.dumps({
            'title': whole['title'], 'direction': whole['direction'], 'parts': parts}))
        (folder / 'presentation-brief.md').write_text(f"# {whole['title']}\n")
        return {'output': str(folder), 'sections': len(parts) - leads}

    @staticmethod
    def _brief(whole: dict, number: int, slides: list, brand, folder: Path) -> str:
        """The brief the tool writes for one section, as it writes it."""
        lines = [f"# Section {number} of {whole['title']}", '',
                 'You are building one section of a deck. Other sections are being built at '
                 'the same time. Read `references/parallel-build.md`, the part headed "If '
                 'you are a worker", in the guidance for this task, and follow what it '
                 'tells you to read.', '', '## The deck', '',
                 f"{whole['title']}, delivered {whole.get('delivery')}. The user has "
                 'approved what each slide says. How each is drawn is yours to design.', '',
                 '## Paths', '', '- Runtime: `/opt/slides-tool/versions/0.13.0`',
                 f'- Brand contract: `{brand}`', f'- Work directory: `{folder}`',
                 f'- Write your section to `section-{number}.json`, and keep your builds '
                 f'and previews under `w{number}/`.', '', '## Direction, to copy unchanged',
                 '', '```json', json.dumps(whole['direction']), '```', '', '## House style',
                 '', 'None given beyond the direction.', '', '## Your slides, in order', '',
                 f'Prefix every node and edge ID you create with `s{number}_`. Slide IDs, '
                 'titles, wording and order are fixed.', '']
        for position, slide in enumerate(slides, start=1):
            lines += [f"{position}. **`{slide['id']}`: \"{slide['title']}\"**",
                      f"   - The audience must understand: {slide.get('understand')}"]
            lines += [f"   - {point['label']}: {point['text']}" for point in slide['points']]
            lines += [f"   - Sources: {json.dumps(slide['sources'])}", '']
        lines += ['## Preview', '', 'Use one Drive preview file of your own for every '
                  'preview, and say which it was.', '', '## Return', '',
                  'The section file, your final preview directory, the Drive file ID, what '
                  'you changed after looking, and what still bothers you.', '']
        return '\n'.join(lines)

    def compile(self, composition, brand, folder=None) -> dict:
        from runner import slides
        self._asked('compile', composition, brand, folder)
        made = self._read(composition)
        text = json.dumps(made)
        problems = [f"{slide.get('id')}: nothing is drawn." for slide in made.get('slides', [])
                    if 'canvas' not in slide and 'layout' not in slide]
        problems += ['A text does not fit: it needs 7 lines and has 4.'] \
            if 'TOO LONG TO FIT' in text else []
        if problems:
            raise slides.Refused(problems)
        report = {'sceneDigest': hashlib.sha256(text.encode()).hexdigest(),
                  'slides': len(made['slides']), 'room': {}}
        if folder is None:
            return {**report, 'status': 'compiles'}
        self._new(folder).mkdir(parents=True)
        structure = {'connectors': [], 'icons': [], 'layouts': [
            {'slide': slide['id'], 'layout': slide['layout']} for slide in made['slides']
            if 'layout' in slide]}
        (Path(folder) / 'scene.json').write_text(json.dumps({'title': made.get('title'), 'slides': [
            {**{key: slide.get(key) for key in ('id', 'title', 'sources', 'notes')},
             'elements': self._elements(slide, structure)} for slide in made['slides']]}))
        # What a review of the build reads beside its scene.
        (Path(folder) / 'structure.json').write_text(json.dumps(structure))
        (Path(folder) / 'brand-contract.json').write_text(Path(brand).read_text()
                                                          if Path(brand).is_file() else '{}')
        (Path(folder) / 'compose-report.json').write_text(json.dumps({'inputs': {'assets': []}}))
        return {**report, 'output': str(folder)}

    @staticmethod
    def _elements(slide: dict, structure: dict) -> list[dict]:
        """What a slide draws, as a scene lists it: its title, then every node of its canvas
        that shows words, one under the other; its icons and edges go in its structure."""
        found = [{'id': f"{slide['id']}_title", 'type': 'text', 'role': 'title',
                  'text': slide.get('title'), 'x': 0, 'y': 0, 'width': 900, 'height': 40}]

        def walk(node) -> None:
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                if node.get('type') == 'icon':
                    structure['icons'].append({'slide': slide['id'], 'id': node.get('id'),
                                               'icon': node.get('icon')})
                elif isinstance(node.get('id'), str) and isinstance(node.get('text'), str):
                    found.append({'id': node['id'], 'type': 'shape' if node.get('type') == 'box'
                                  else 'text', 'text': node['text'], 'x': 0,
                                  'y': 40 * len(found), 'width': 900, 'height': 40})
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)

        walk(slide.get('canvas'))
        structure['connectors'] += [{'slide': slide['id'], 'id': edge.get('id'),
                                     'from': edge.get('from'), 'to': edge.get('to')}
                                    for edge in slide.get('connect') or ()]
        return found

    def merge(self, parts, composition) -> dict:
        self._asked('merge', parts, composition)
        listed = self._read(parts)
        slides = [slide for part in listed['parts']
                  for slide in self._read(Path(parts).parent / part)['slides']]
        self._new(composition).write_text(json.dumps({
            'version': 1, 'title': listed['title'], 'direction': listed['direction'],
            'slides': slides}))
        return {'output': str(composition), 'slides': len(slides)}

    def preview(self, compiled, folder, renderer, file_id=None, slide=None) -> dict:
        with self.counting:
            self.busy += 1
            self.most = max(self.most, self.busy)
        try:
            time.sleep(self.took)
            folder = self._new(folder)
            folder.mkdir(parents=True)
            scene = (Path(compiled) / 'scene.json').read_bytes()
            (folder / 'deck.pptx').write_bytes(b'PK\x03\x04' + scene)
            if 'preview' in self.refuse:  # as the real tool fails: after it wrote a file
                (folder / 'deck.pptx').unlink()
            self._asked('preview', compiled, folder, renderer, file_id)
            if renderer == 'drive' and file_id is None:
                self.files.append(f'file-{len(self.files) + 1}')
            shown = []
            for number, made in enumerate(json.loads(scene)['slides'], start=1):
                image = folder / f'slide-{number:02d}.png'
                image.write_bytes(png(number))
                shown.append({'id': made['id'], 'number': number, 'title': made['title'],
                              'image': str(image),
                              'findings': list(self.findings.get(made['id'], ()))})
            mine = file_id or (self.files[-1] if renderer == 'drive' else None)
            return {'deck': str(folder / 'deck.pptx'), 'renderer': renderer, 'fileId': mine,
                    'deckSha256': hashlib.sha256((folder / 'deck.pptx').read_bytes())
                    .hexdigest(), 'contactSheet': str(folder / 'contact-sheet.png'),
                    'url': f'https://docs.example.com/presentation/d/{mine}/edit' if mine
                    else None, 'slides': shown}
        finally:
            with self.counting:
                self.busy -= 1

    def critique(self, preview_folder, assessment) -> dict:
        from runner import slides
        self._asked('critique', preview_folder, assessment)
        given, folder = self._read(assessment), Path(preview_folder)
        problems = []
        if (folder / 'critique.json').exists():
            problems.append('This render already has a critique.')
        if given.get('deckSha256') != hashlib.sha256(
                (folder / 'deck.pptx').read_bytes()).hexdigest():
            problems.append('The assessment is of another render.')
        problems += [f"{finding.get('slide')}: the note is too short."
                     for finding in given['findings'] if len(finding.get('note', '')) < 12]
        problems += [f'{key} is not something a finding has.' for finding in given['findings']
                     for key in finding if key not in ('slide', 'question', 'severity',
                                                       'note', 'fix')]
        if problems:
            raise slides.Refused(problems)
        (folder / 'critique.json').write_text(json.dumps(given))
        counts = {grade: sum(finding['severity'] == grade for finding in given['findings'])
                  for grade in ('critical', 'major', 'minor')}
        return {**counts, 'status': 'blocked' if counts['critical'] else 'clear'}

    def render(self, compiled, deck) -> dict:
        self._asked('render', compiled, deck)
        self._new(deck).write_bytes(b'PK\x03\x04 rendered again')
        return {'output': str(deck)}

    def cited(self, compiled) -> dict:
        self._asked('cited', compiled)
        found: dict[str, list] = {}
        for number, slide in enumerate(self._read(Path(compiled) / 'scene.json')['slides'],
                                       start=1):
            for source in slide.get('sources') or ():
                if source != 'outline':
                    found.setdefault(source, []).append(number)
        return found

    def drive_check(self) -> bool:
        self._asked('drive_check')
        return self.have['drive']

    def designs(self) -> bool:
        return False

    def sections(self) -> bool:
        return False

    def assets(self) -> bool:
        return False

    def reviews(self) -> bool:
        return False

    def drive_import(self, deck, name) -> dict:
        self._asked('drive_import', deck, name)
        self.imported.append(Path(deck).read_bytes())
        ident = f'slides-{len(self.imported)}'
        return {'id': ident, 'name': name,
                'url': f'https://docs.example.com/presentation/d/{ident}/edit'}


class Brand:
    """Stands in for a brand skill's wrapper, by the docstring of `runner.brand`: one
    made-up brand in two variants, an export with the guide that says how the
    organisation is named, a few icons and an audit. `revision` is what the brand's
    sources are at now: change it, and a contract exported before no longer holds."""
    name = 'Example Co brand kit'
    runtime = Path('/opt/brand-kit')
    VOICE = ('# How Example Co is named\n\nWrite Example Co, in two words. Never ExampleCo, '
             'and never the Example Company.\n')
    ICONS = [{'id': 'icon-server', 'name': 'Server', 'category': 'Hardware', 'native': True},
             {'id': 'icon-clock', 'name': 'Clock', 'category': 'Time', 'native': True},
             {'id': 'icon-server-rack', 'name': 'Server rack', 'category': 'Hardware',
              'native': True},
             {'id': 'icon-server-photo', 'name': 'Server photo', 'category': 'Pictures',
              'native': False}]

    def __init__(self):
        self.revision, self.refuse, self.exports, self.audited = 1, {}, [], []
        self.warnings = [{'code': 'SMALL_TEXT', 'slide': 2, 'says': 'Text under 18 points.'},
                         {'code': 'SMALL_TEXT', 'slide': 3, 'says': 'Text under 18 points.'},
                         {'code': 'HIGH_TEXT_DENSITY', 'slide': 3,
                          'says': 'Many words for one slide.'}]

    def _asked(self, name: str) -> None:
        from runner import brand
        if name in self.refuse:
            raise brand.Refused(list(self.refuse[name]))

    def brands(self) -> list[dict]:
        return [{'brand': 'example-co', 'name': 'Example Co', 'variants': ['light', 'dark']}]

    def export(self, folder, brand_id, variant, delivery='reading') -> dict:
        from runner import brand
        self._asked('export')
        folder = Path(folder)
        if folder.exists():
            raise brand.Refused([f'{folder.name} is already there. Give a new folder.'])
        folder.mkdir(parents=True)
        (folder / 'brand-contract.json').write_text(json.dumps({
            'brand': brand_id, 'variant': variant, 'delivery': delivery,
            'revision': self.revision}))
        (folder / 'DESIGN.md').write_text('# How Example Co looks\n')
        (folder / 'VOICE.md').write_text(self.VOICE)
        self.exports.append((folder.name, brand_id, variant, delivery))
        return {'contract': str(folder / 'brand-contract.json'),
                'design': str(folder / 'DESIGN.md'), 'voice': str(folder / 'VOICE.md')}

    def check(self, contract) -> None:
        from runner import brand
        self._asked('check')
        if json.loads(Path(contract).read_text())['revision'] != self.revision:
            raise brand.Refused(["The brand's own files have changed since this was "
                                 'exported.'])

    def icons(self, words, limit=5) -> list[dict]:
        self._asked('icons')
        return [dict(icon) for icon in self.ICONS
                if all(word in icon['name'].lower() for word in words.lower().split())][:limit]

    def audit(self, deck, brand_id, variant) -> dict:
        self._asked('audit')
        self.audited.append((Path(deck).read_bytes(), brand_id, variant))
        return {'status': 'WARN' if self.warnings else 'PASS', 'blockers': [],
                'warnings': [dict(warning) for warning in self.warnings]}

    def ready(self) -> dict:
        return {'ready': True}


def stand_in_slides():
    """The runner's Slides wrapper, with the stand-in for the harness-slides command line
    behind it."""
    from stand_ins import slides
    return slides.stand_in()


def stand_in_brand():
    """The runner's Brand wrapper, with the stand-in for a brand skill's command behind it."""
    from stand_ins import brand
    return brand.stand_in()


# --- the engine's stand-ins: scripted workers, a person and a team -------------------------

URL = 'https://docs.example.com/restarts'
QUOTE = 'Capacity holds only when more than one instance is running.'
FORM = {'route': 'scratch', 'title': 'Rolling restarts', 'audience': 'Platform teams',
        'goal': 'Show when capacity holds', 'minutes': 20, 'brand': 'example',
        'variant': 'light', 'output': 'google', 'research': False}
CLASSIFIED = {'kind': 'material', 'reason': 'Notes to build a talk from.', 'slides': None}


def fails(detail: str = 'It stopped without finishing: the model gave up.',
          reason: str = 'failed', cost: float | None = None):
    """A worker that ends without handing anything back, as an agent that failed would."""
    from runner.agents import Outcome
    return lambda tools, job: Outcome(False, reason, detail, cost=cost)


def asks(question: str):
    """A worker that asks the person a question, which ends its job."""
    def act(tools, job):
        tools.ask_person(question)
    return act


def unsettled(workers, ident):
    """A research worker that leaves `ident` open and answers every other question."""
    def act(tools, job):
        if tools.job['finding'] != ident:
            return workers.question(tools, job)
        return tools.submit_finding(ident, 'insufficient', 'No page says.',
                                    headline='No page says what starts the next batch.',
                                    limits='Only one page was found.', evidence=[])
    return act


class Workers:
    """Scripted workers for a deck. Each kind of job does the right thing unless a test
    queues something else for it with `then`. `jobs` lists every job that was started, as
    (kind, job, spec)."""

    def __init__(self):
        self.jobs, self.queued, self.cost = [], {}, None
        self.outline_said, self.classified, self.plan = OUTLINE, CLASSIFIED, PLAN
        self.found = []     # what each review in turn finds; nothing, once this runs out

    def then(self, kind: str, *acts) -> None:
        """Queue what the next jobs of one kind do: `classification`, `research-plan`,
        `question`, `outline`, `section`, `review`, `patch`."""
        self.queued.setdefault(kind, []).extend(acts)

    def of(self, kind: str) -> list:
        return [job for seen, job, spec in self.jobs if seen.partition(':')[0] == kind]

    def __call__(self, tools, job):
        from runner.agents import Outcome
        spec = tools.job
        kind = (f"question:{spec['finding']}" if spec.get('finding') else
                'review' if spec.get('review') else next(iter(spec['artifacts'])))
        self.jobs.append((kind, job, spec))
        queued = self.queued.get(kind) or self.queued.get(kind.partition(':')[0])
        act = queued.pop(0) if queued else getattr(
            self, kind.partition(':')[0].replace('-', '_'))
        returned = act(tools, job)
        if isinstance(returned, Outcome) or self.cost is None:
            return returned
        return Outcome(True, text=returned or '', cost=self.cost,
                       tokens={'input': 1000, 'cached': 800, 'output': 200}, seconds=1.5)

    @staticmethod
    def _ok(outcome):
        assert outcome[0], outcome[1]

    def classification(self, tools, job):
        self._ok(tools.submit_artifact('classification', json.dumps(self.classified)))
        tools.submit_review('It reads as notes, not as slides.')

    def research_plan(self, tools, job):
        self._ok(tools.submit_artifact('research-plan', json.dumps(self.plan)))
        tools.submit_review('Two questions.')

    def question(self, tools, job):
        # The page is saved under the next free ID: s1, unless the person's own documents
        # were saved first.
        said = tools.save_source(URL)[1]
        saved = said.split(' as ', 1)[1].split(':', 1)[0]
        ident = tools.job['finding']
        self._ok(tools.submit_finding(ident, 'supported', f'What the page says about {ident}.',
                                      headline=f'The page answers {ident}.',
                                      evidence=[{'source_id': saved, 'quote': QUOTE}]))

    def outline(self, tools, job):
        said = json.dumps(self.outline_said)
        checked = tools.check_outline(said)
        assert checked[1].startswith('Nothing to put right'), checked[1]
        self._ok(tools.submit_outline(said))
        tools.submit_review('Six slides. The check slide is the one I am least sure of.')

    def section(self, tools, job):
        from stand_ins.slides import sketch
        spec = tools.job['artifacts']['section']
        by_id = {slide['id']: slide for slide in self.outline_said['slides']}
        made = json.dumps({'version': 1, 'title': spec['title'], 'direction': spec['direction'],
                           'slides': [sketch(by_id[slide['id']], spec['prefix'])
                                      for slide in spec['slides']]})
        self._ok(tools.preview_section(made))
        self._ok(tools.submit_section(made, 'Nothing: it read well at once.'))

    def review(self, tools, job):
        listed = tools.job['review']['slides']
        for slide in listed:
            self._ok(tools.look_at_slide(slide['number']))
        found = self.found.pop(0)(listed) if self.found else []
        self._ok(tools.submit_assessment(json.dumps(found), '[]'))


class StudioCase(unittest.TestCase):
    """A person with a data folder and a git identity of their own, a workspace, scripted
    workers, a pretend web and the stand-ins for the slides tool, a brand skill and
    harness-research. Nothing real is started and nothing leaves this computer."""

    BACKGROUND = False

    def setUp(self):
        from dataclasses import replace
        from unittest import mock
        from runner import engine as engines, gitstate, settings
        from runner.agents import Scripted
        from stand_ins import research as research_stand_in
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        (self.base / 'no-templates').mkdir()
        helpers.gitconfig(
            self.base / 'gitconfig',
            '[user]\n\tname = Alex\n\temail = alex@example.com\n[init]\n\tdefaultBranch = '
            f"main\n\ttemplateDir = {self.base / 'no-templates'}\n")
        self.web = Web()
        self.web.page(URL, PAGE)
        self.notifier = Notifier()
        self.slides, self.brand = stand_in_slides(), stand_in_brand()
        self.real = (engines.slides_tool.Slides, engines.brand_skill.Brand)
        patches = [
            mock.patch.dict(os.environ, {'PRESENTATION_STUDIO_DATA': str(self.base / 'data'),
                                         'STUDIOS_CONFIG': str(self.base /
                                                               'studios-config.json'),
                                         'GIT_CONFIG_GLOBAL': str(self.base / 'gitconfig'),
                                         'GIT_CONFIG_NOSYSTEM': '1'}),
            mock.patch.object(worker_tools, 'fetch_once', self.web.opener),
            mock.patch.object(worker_tools, 'resolve', self.web.resolver),
            # The engine and a worker's tools both find the slides tool and a brand skill
            # through these two, so no test can reach a real one.
            mock.patch.object(engines.slides_tool, 'Slides', self.the_slides),
            mock.patch.object(engines.brand_skill, 'Brand', self.the_brand),
            # The tests' data folders are temporary; the check of that is tested on its own.
            mock.patch.object(engines.agents, 'shared_temporary', lambda: []),
            mock.patch.object(engines.team, 'Notifier', lambda *given, **named: self.notifier),
            mock.patch.object(engines.brand_skill, 'found',
                              lambda *asked, **named: [] if self.brand is None
                              else [{'name': self.brand.name,
                                     'version': getattr(self.brand, 'version', None),
                                     'runtime': str(self.brand.runtime),
                                     'brands': self.brand.brands()}]),
            mock.patch.object(engines.slides_tool, 'ready', lambda slides=None, which=None,
                              drive=True, look=engines.slides_tool.ready: look(
                                  slides, which=self.which, drive=drive))]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
            os.environ.pop(name, None)
        settings.save(replace(settings.load(), previews='local'))
        self.engines, self.gitstate, self.settings = engines, gitstate, settings
        self.research = research_stand_in.stand_in()
        self.workers = Workers()
        self.adapters = {'claude': Scripted(self.workers), 'codex': Scripted(self.workers)}
        self.space = self.set_up()
        self.engine = self.make()

    @staticmethod
    def which(program: str) -> str | None:
        return f'/usr/bin/{Path(program).name}'

    def the_slides(self, runtime=None, run=None, read=None):
        return self.slides

    def the_brand(self, runtime=None, run=None):
        """The stand-in brand skill, or, once a test sets `self.brand` to None, the refusal
        the real one gives when none is installed."""
        if self.brand is None:
            from workspace import WorkspaceError
            named = os.environ.get('BRAND_SKILL_RUNTIME')
            if named:
                raise WorkspaceError(f'BRAND_SKILL_RUNTIME names {named}, which does not hold '
                                     'a brand skill. Point it at an installed one, or unset '
                                     'it.')
            raise WorkspaceError('No brand skill was found on this computer, so a deck '
                                 'cannot be made. Install one, or name its folder in '
                                 'BRAND_SKILL_RUNTIME, then try again.')
        return self.brand

    def set_up(self):
        """The workspace: a folder with no remote, unless a test wants another."""
        return self.gitstate.local(self.base / 'team-work')

    def make(self, **options):
        options = {'adapters': self.adapters, 'research': lambda: self.research,
                   'background': self.BACKGROUND, **options}
        engine = self.engines.Engine(**options)
        self.addCleanup(engine.close)
        return engine

    def start(self, uploads=None, engine=None, **changes) -> Path:
        return Path((engine or self.engine).start({**FORM, **changes}, uploads)['path'])

    def view(self, root: Path) -> dict:
        return self.engine.view(root)

    def state(self, root: Path) -> str:
        return self.view(root)['state']

    def waiting(self, root: Path) -> str | None:
        gate = self.view(root)['gate']
        return gate and gate['name']

    def decide(self, root: Path, gate: str | None = None, decision: str = 'approve',
               note: str | None = None, extra: dict | None = None, engine=None) -> dict:
        engine = engine or self.engine
        gate = gate or engine.view(root)['gate']['name']
        return engine.decide(root, gate, decision, note, extra)

    def to_gate(self, root: Path, gate: str) -> None:
        """Approve what is waiting until `gate` is the one waiting."""
        for _ in range(20):
            waiting = self.waiting(root)
            self.assertIsNotNone(waiting, self.view(root)['sentence'])
            if waiting == gate:
                return
            self.decide(root, waiting)
        self.fail(f'{gate} never came up')

    def to_end(self, root: Path) -> list[str]:
        """Approve everything put to the person until nothing is, and say what that was."""
        approved = []
        for _ in range(20):
            waiting = self.waiting(root)
            if waiting is None:
                return approved
            self.decide(root, waiting)
            approved.append(waiting)
        self.fail('The deck never stopped asking')

    def git(self, *args: str, repo: Path | None = None) -> str:
        import subprocess
        done = subprocess.run(['git', *args], cwd=repo or self.space.repo,
                              capture_output=True, text=True, check=True)
        return done.stdout.strip()

    def log(self) -> list[str]:
        """What each commit says happened, oldest first."""
        return self.git('log', '--reverse', '--format=%s').splitlines()

    def record(self, root: Path) -> dict:
        return json.loads((root / 'run.json').read_text())


class Notifier:
    """Stands in for the computer's own notifications: `sent` lists each title told."""

    def __init__(self):
        self.sent, self.way = [], None

    def can(self) -> tuple:
        return (self.way is None, self.way)

    def send(self, title: str) -> bool:
        if self.way is not None:
            return False
        self.sent.append(title)
        return True


class Person:
    """One of two people who share a workspace: a data folder, a studios config, a git
    identity, a clone of the workspace and an engine of their own."""

    def __init__(self, name: str, env: dict):
        self.name, self.env = name, env
        self.space = self.engine = None


class TeamCase(StudioCase):
    """Two people on one computer, standing in for two: each has a data folder, a studios
    config and a git identity, and both have joined one bare repository. `self.engine` is
    Alex's. Anything done as one of them is done inside `with self.be(person):`."""

    def set_up(self):
        self.remote = self.base / 'team-repo.git'
        self.remote.mkdir()
        self.git('init', '--quiet', '--bare', repo=self.remote)
        self.git('symbolic-ref', 'HEAD', 'refs/heads/main', repo=self.remote)
        return self.gitstate.join(str(self.remote))

    def setUp(self):
        super().setUp()
        self.alex = Person('Alex', {name: os.environ[name] for name in (
            'PRESENTATION_STUDIO_DATA', 'STUDIOS_CONFIG', 'GIT_CONFIG_GLOBAL')})
        self.alex.space, self.alex.engine = self.space, self.engine
        with self.be(self.alex):
            self.engine.share()     # the workspace's own files, so a teammate finds them
        self.blake = self.person('Blake')

    def person(self, name: str) -> Person:
        """Someone else, who joins the same repository from a computer of their own."""
        from dataclasses import replace
        from unittest import mock
        folder = self.base / name.lower()
        folder.mkdir()
        helpers.gitconfig(
            folder / 'gitconfig',
            f'[user]\n\tname = {name}\n\temail = {name.lower()}@example.com\n[init]\n\t'
            f"defaultBranch = main\n\ttemplateDir = {self.base / 'no-templates'}\n")
        made = Person(name, {'PRESENTATION_STUDIO_DATA': str(folder / 'data'),
                             'STUDIOS_CONFIG': str(folder / 'studios-config.json'),
                             'GIT_CONFIG_GLOBAL': str(folder / 'gitconfig')})
        with mock.patch.dict(os.environ, made.env):
            self.settings.save(replace(self.settings.load(), previews='local'))
            made.space = self.gitstate.join(str(self.remote))
            made.engine = self.make()
        return made

    def be(self, person: Person):
        """Act as one of them: their data folder, their studios config and their git
        identity."""
        from unittest import mock
        return mock.patch.dict(os.environ, person.env)

    def as_(self, person: Person, action, *args, **named):
        with self.be(person):
            return action(*args, **named)

    def theirs(self, person: Person, root: Path) -> Path:
        """The same deck in someone else's copy of the workspace."""
        return person.space.deck(Path(root).name)

    def shared(self) -> list[str]:
        """What the team's repository has been sent, newest first."""
        if not self.git('for-each-ref', 'refs/heads/main', repo=self.remote):
            return []
        return self.git('log', '--format=%s', 'main', repo=self.remote).splitlines()

    def tags(self) -> list[str]:
        return self.git('tag', '--list', repo=self.remote).splitlines()


# --- the page over the stand-ins, for `studio serve --fake` -------------------------------

class Fake:
    """What `studio serve --fake` serves: `engine()` makes the engine, `keeper(after=...)`
    what looks after the skills, both over a temporary folder of their own."""

    def __init__(self, base: Path, engine, keeper):
        self.base, self.engine, self.keeper = base, engine, keeper


def fake_studio() -> Fake:
    """The engine of StudioCase, made for a process rather than a test: a person called Alex
    with a data folder, a git identity and a workspace on this computer, in a temporary
    folder; the stand-ins for the slides tool, a brand skill and harness-research; a pretend
    web; workers that do as Workers says; a look at this computer that runs nothing; and
    upkeep that looks in an empty home and never online. The stand-ins stay in place for
    the life of the process. For tests and the page's visual check only (see studio.py)."""
    from dataclasses import replace
    from unittest import mock
    import computer
    from runner import engine as engines, gitstate, settings, upkeep
    from runner.agents import Scripted
    from stand_ins import research as research_stand_in
    base = Path(tempfile.mkdtemp(prefix='presentation-studio-fake-')).resolve()
    (base / 'no-templates').mkdir()
    (base / 'home').mkdir()
    helpers.gitconfig(
        base / 'gitconfig',
        '[user]\n\tname = Alex\n\temail = alex@example.com\n[init]\n\tdefaultBranch = '
        f"main\n\ttemplateDir = {base / 'no-templates'}\n")
    os.environ.update({'PRESENTATION_STUDIO_DATA': str(base / 'data'),
                       'STUDIOS_CONFIG': str(base / 'studios-config.json'),
                       'GIT_CONFIG_GLOBAL': str(base / 'gitconfig'),
                       'GIT_CONFIG_NOSYSTEM': '1'})
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'BRAND_SKILL_RUNTIME',
                 'HARNESS_SLIDES_RUNTIME', 'HARNESS_RESEARCH_RUNTIME'):
        os.environ.pop(name, None)
    web = Web()
    web.page(URL, PAGE)
    slides, brand = stand_in_slides(), stand_in_brand()
    looked = {'checked_at': '2026-10-14T09:00:00Z', 'ready': True,
              'assistants': ['Claude Code'], 'wrong': [], 'items': []}
    for patch in (
            mock.patch.object(worker_tools, 'fetch_once', web.opener),
            mock.patch.object(worker_tools, 'resolve', web.resolver),
            mock.patch.object(engines.slides_tool, 'Slides', lambda *a, **k: slides),
            mock.patch.object(engines.brand_skill, 'Brand', lambda *a, **k: brand),
            mock.patch.object(engines.agents, 'shared_temporary', lambda: []),
            mock.patch.object(engines.team, 'Notifier', lambda *a, **k: Notifier()),
            mock.patch.object(engines.brand_skill, 'found',
                              lambda *asked, **named: [{'name': brand.name,
                                                        'version': None,
                                                        'runtime': str(brand.runtime),
                                                        'brands': brand.brands()}]),
            mock.patch.object(engines.slides_tool, 'ready', lambda slides=None, which=None,
                              drive=True, look=engines.slides_tool.ready: look(
                                  slides, which=StudioCase.which, drive=drive)),
            mock.patch.object(computer, 'check', lambda *a, **k: dict(looked))):
        patch.start()
    settings.save(replace(settings.load(), previews='local', look_for_updates=False,
                          brand='example', variant='light'))
    gitstate.local(base / 'team-work')
    research, workers = research_stand_in.stand_in(), Workers()
    adapters = {'claude': Scripted(workers), 'codex': Scripted(workers)}
    return Fake(base,
                lambda: engines.Engine(adapters=adapters, research=lambda: research),
                lambda after=None: upkeep.Upkeep(home_dir=base / 'home',
                                                 root=base / 'data', after=after))
