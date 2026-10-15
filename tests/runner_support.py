"""Shared setup for the runner's tests: its import path, a job folder, a pretend web,
processes a test started, and small stand-ins for the slides tool and a brand skill behind
their wrappers. Later tasks add the engine's stand-ins here as the runner grows."""
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
        slides = given['slides']
        found = [{'slide': slide['id'], 'code': 'no-notes', 'detail': 'It has no notes.'}
                 for slide in slides if not slide.get('notes')]
        words = {slide['id']: sum(len(f"{point['label']} {point['text']}".split())
                                  for point in slide.get('points') or ())
                 for slide in slides}
        found += [{'slide': ident, 'code': 'over-budget',
                   'detail': f'{count} words against {self.budget}.'}
                  for ident, count in words.items() if count > self.budget]
        return {'status': 'findings' if found else 'ok', 'slides': len(slides),
                'delivery': 'reading', 'wordBudget': self.budget, 'words': words,
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
