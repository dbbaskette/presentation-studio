"""The page, run for real: its shell and its files, markdown.js, and app.js driven screen by
screen in a document with no HTML parser (page_harness.js), against the server's own answers.

Every answer the scripted screens read is what the runner's page gives for a real deck run
over the tests' stand-ins (runner_support), so a gate the engine shows is a gate the page
draws. Nothing starts an agent, looks at the real computer or touches the network.
"""
import base64
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import helpers
import runner_support
from test_runner_page import PageCase

import server
from runner.steps import build

PAGE = helpers.SCRIPTS / 'desk'
HARNESS = Path(__file__).resolve().parent / 'page_harness.js'
NODE = shutil.which('node')
FORBIDDEN_WORDS = re.compile(r'\b(artifacts?|stale|lineage|trainings?)\b', re.IGNORECASE)
MARKUP = '<script>alert(1)</script>\n<img src=x onerror=alert(2)>\n'
PICTURE = {'status': 200, 'picture': base64.b64encode(runner_support.png()).decode('ascii')}
DECK = b'PK\x03\x04' + b'stand-in deck'
ADDRESS = 'https://github.com/acme/acme-brand.git'
MODELS = {'GET /api/models': [{'status': 200, 'body': {
    'agent': 'claude', 'source': 'Claude Code model list', 'problem': None, 'levels': [],
    'models': [{'name': 'opus', 'label': 'Opus', 'family': None, 'about': None,
                'default_level': None, 'levels': ['low', 'high']}]}}]}


def ok(body) -> dict:
    return {'status': 200, 'body': body}


class PageFileTests(unittest.TestCase):
    """What can be said about the page without a browser."""

    def read(self, name: str) -> str:
        return (PAGE / name).read_text(encoding='utf-8')

    def test_the_vendored_files_are_as_they_were_taken(self):
        vendor = json.loads((helpers.REPO / 'vendor.json').read_text(encoding='utf-8'))
        taken = {entry['path']: entry for entry in vendor['files']}
        for name in ('style.css', 'markdown.js', 'index.html', 'app.js'):
            with self.subTest(name):
                entry = taken[f'skills/presentation-studio/scripts/desk/{name}']
                self.assertEqual(entry['from'], f'skills/training-studio/scripts/desk/{name}')
                self.assertTrue(entry['revision'].startswith('b19c743'))
        self.assertIn('tests/page_harness.js', taken)

    def test_the_page_and_its_stylesheets_are_served_and_nothing_else(self):
        self.assertEqual(set(server.PAGE), {'/', '/index.html', '/app.js', '/markdown.js',
                                            '/style.css', '/deck.css'})

    def test_the_page_has_nothing_its_own_policy_would_block(self):
        page = self.read('index.html')
        self.assertNotRegex(page, r'<style\b')
        self.assertNotRegex(page, r'\sstyle\s*=')
        self.assertNotRegex(page, r'\son[a-z]+\s*=')
        self.assertNotRegex(page, r'<svg\b')
        self.assertEqual(re.findall(r'<script\b[^>]*>(.*?)</script>', page, re.DOTALL),
                         ['', ''])

    def test_the_shell_names_its_controls_and_its_regions(self):
        page = self.read('index.html')
        self.assertIn('<html lang="en">', page)
        for label in ('Home', 'Decks', 'Status', 'Settings'):
            self.assertRegex(page, rf'<button type="button" id="go-\w+" class="nav-item"[^>]*>'
                                   rf'<span class="nav-label">{label}</span>')
        self.assertIn('<nav id="sidebar" class="sidebar glass" aria-label="Screens">', page)
        self.assertIn('id="notice" class="notice" role="alert"', page)
        self.assertIn('id="toasts" class="toasts" role="status" aria-live="polite"', page)
        self.assertIn('id="sheet" class="sheet glass" role="dialog" aria-modal="true" '
                      'aria-labelledby="sheet-title"', page)
        self.assertEqual(len(re.findall(r'<h1\b', page)), 1)
        self.assertNotRegex(page, r'tabindex="[1-9]')
        self.assertNotRegex(self.read('app.js'), r'tabIndex = [1-9]')

    def test_every_state_has_a_shape_of_its_own(self):
        script = self.read('app.js')
        drawn = dict(re.findall(r"(\w+): '(\w+)'", re.search(
            r'const BEAD_ICONS = \{(.*?)\};', script, re.DOTALL)[1]))
        self.assertEqual(drawn, {'done': 'check', 'review': 'eye', 'late': 'warn',
                                 'out': 'minus', 'off': 'slash'})
        for icon in drawn.values():
            self.assertRegex(script, rf'\n  {icon}: \[')

    def test_only_the_shell_and_a_toast_are_glass_and_motion_can_be_calmed(self):
        script, page = self.read('app.js'), self.read('index.html')
        self.assertEqual(len(re.findall(r'class="[^"]*\bglass\b', page)), 3)
        self.assertEqual(re.findall(r"'([\w -]*\bglass\b[\w -]*)'", script), ['toast glass'])
        self.assertIn('if (document.startViewTransition && !calm())', script)
        self.assertRegex(script, r'function followPointer\(\) \{\n  if \(calm\(\)\) return;')

    def test_the_deck_stylesheet_uses_only_the_vendored_colours(self):
        styles = self.read('deck.css')
        self.assertNotRegex(styles, r'#[0-9a-fA-F]{3,6}\b|rgb\(')
        self.assertNotIn('backdrop-filter', styles)


def tags(tree, found=None) -> list:
    found = [] if found is None else found
    if isinstance(tree, dict):
        found.append(tree['tag'])
        for child in tree.get('children', []):
            tags(child, found)
    return found


def text_of(tree) -> str:
    if isinstance(tree, str):
        return tree
    return ''.join(text_of(child) for child in tree.get('children', []))


@unittest.skipUnless(NODE, 'Node is needed to run the page scripts without a browser')
class MarkdownTests(unittest.TestCase):
    """markdown.js, run for real against a document that has no HTML parser."""

    def render(self, text: str) -> dict:
        done = subprocess.run([NODE, str(HARNESS), 'markdown'], input=text, text=True,
                              capture_output=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_an_outline_is_drawn_as_a_document(self):
        tree = self.render('# Rolling restarts\n\n## 1. What it does\n\n- **Batch**: one at a '
                           'time\n\nNotes: 6 min.\n')
        self.assertEqual(tags(tree)[:2], ['div', 'h2'])
        self.assertIn('strong', tags(tree))
        self.assertIn('Notes: 6 min.', text_of(tree))

    def test_markup_in_a_document_is_shown_as_the_text_it_is(self):
        tree = self.render(MARKUP + '\n[a link](javascript:alert(3)) [ok](https://example.com)\n')
        self.assertLessEqual(set(tags(tree)), {'div', 'p', 'br', 'a'})
        for kept in ('<script>alert(1)</script>', '<img src=x onerror=alert(2)>',
                     '[a link](javascript:alert(3))'):
            self.assertIn(kept, text_of(tree))


class ScriptedPage:
    """Runs app.js in the harness, and checks what every screen it shows must hold."""

    def run_page(self, answers: dict, steps: list, **plan) -> dict:
        file = self.base / 'plan.json'
        file.write_text(json.dumps({'answers': answers, 'steps': steps, **plan}),
                        encoding='utf-8')
        done = subprocess.run([NODE, str(HARNESS), 'app', str(file)], text=True,
                              capture_output=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['strayListeners'], [],
                         'only a real control may answer a click, so the keyboard reaches it')
        for name, shot in result['snapshots'].items():
            with self.subTest(screen=name):
                self.assertEqual(shot['unnamed'], [], 'every control has a name')
                self.assertEqual(shot['foreign'], 0, 'nothing from a file became an element')
                self.assertEqual(shot['bareBeads'], 0, 'every bead has words beside it')
                self.assertLessEqual(len(shot['filled']), 1, 'one filled button on a screen')
                self.assertNotRegex(shot['text'] + shot['sheet'], FORBIDDEN_WORDS)
        return result

    def posts(self, result: dict) -> list:
        made = [request for request in result['requests'] if request['method'] == 'POST']
        for post in made:
            self.assertEqual(post['headers'], {server.TOKEN_HEADER: 'the-test-key',
                                               'Content-Type': 'application/json'})
        return [(post['address'], post['body']) for post in made]


@unittest.skipUnless(NODE, 'Node is needed to run the page scripts without a browser')
class ScreenTests(ScriptedPage, PageCase):
    """Each screen, drawn from what the runner's page answers for real decks."""

    def answers(self, **more) -> dict:
        return {'GET /api/setup': [ok(self.get('setup'))],
                'GET /api/decks': [ok(self.get('decks'))],
                'GET /api/computer': [ok(self.get('computer'))],
                'GET /api/agents': [ok(self.get('agents'))],
                'GET /api/slide': [PICTURE], **MODELS, **more}

    def test_set_up_comes_first_offers_what_the_studios_share_and_saves_the_defaults(self):
        described = self.get('setup')
        fresh = {**described, 'configured': False, 'workspace': None,
                 'suggested': {'repository': 'git@example.com:team/decks.git',
                               'branch': 'decks', 'share_when': 'when-asked'}}
        check = {'ok': True, 'found': {'name': 'decks', 'folder': 'presentations',
                                       'branch': 'decks', 'existing': False},
                 'checks': [{'what': 'the repository can be reached', 'ok': True, 'fix': None}]}
        answers = self.answers(**{'GET /api/setup': [ok(fresh), ok(described)],
                                  'POST /api/setup/check': [ok(check)],
                                  'POST /api/setup': [ok(described)]})
        result = self.run_page(answers, [
            {'snapshot': 'first'},
            {'fill': 'Your name', 'value': 'Alex Doe'},
            {'click': 'Check this computer'},
            {'click': 'Save and go on'}, {'snapshot': 'saved'}])
        first = result['snapshots']['first']
        self.assertEqual((first['heading'], first['sidebar']),
                         ('Set up Presentation Studio', False))
        self.assertEqual(first['filled'], ['Save and go on'])
        for shown in ('Check this computer', 'Workspace: where your decks are kept', 'Defaults',
                      'This is ready to use.', 'Delivered as',
                      'shared by every studio on this computer'):
            self.assertIn(shown, first['text'])
        self.assertEqual(first['fields']['The repository’s address'],
                         'git@example.com:team/decks.git')
        self.assertEqual(first['fields']['The branch'], 'decks')
        self.assertIn('Only when I ask', first['pressed'])
        sent = dict(self.posts(result))
        self.assertEqual(sent['/api/computer'], {})
        saved = sent['/api/setup']
        # Only a brand the brand skill on this computer has is offered, and so sent.
        brand = {'brand': described['brand']['brands'][0]['brand'],
                 'variant': described['brand']['brands'][0]['variants'][0]}
        self.assertEqual({key: saved[key] for key in ('repository', 'branch', 'folder', 'name',
                                                      'share_when', 'person', 'brand',
                                                      'variant', 'output')},
                         {'repository': 'git@example.com:team/decks.git', 'branch': 'decks',
                          'folder': 'presentations', 'name': 'decks',
                          'share_when': 'when-asked', 'person': 'Alex Doe',
                          'brand': brand['brand'], 'variant': brand['variant'],
                          'output': 'google'})
        # Shared values go to the studios config by the server's own rule, never by a switch.
        self.assertNotIn('for_all_studios', saved)
        # What the form was shown goes with it, so that a value another studio changes
        # meanwhile is never written over.
        self.assertEqual(saved['shared_seen'], fresh['shared'])
        self.assertIn('deck_dollars', saved['limits'])
        self.assertEqual(result['snapshots']['saved']['heading'], 'Home')

    def test_home_puts_each_deck_where_it_stands_and_a_finished_one_with_its_link(self):
        waiting = self.started(title='Waiting deck')
        done = self.started(title='Finished deck')
        for _ in range(20):
            gate = self.run_of(done)['gate']
            if gate is None:
                break
            self.decided(done)
        result = self.run_page(self.answers(), [{'see': 'Every slide of'},
                                                {'snapshot': 'home'}])
        home = result['snapshots']['home']
        self.assertEqual(home['heading'], 'Home')
        self.assertEqual(home['filled'], ['Review Waiting deck'])
        text = home['text']
        self.assertIn('Needs you\nWaiting deck', text)
        self.assertIn('Finished\nFinished deck', text)
        self.assertEqual(home['badge'], '1 thing needs you')
        links = [link for link in home['links'] if link['name'].startswith('Open Finished')]
        self.assertEqual(len(links), 1)
        self.assertTrue(links[0]['href'].startswith('https://'))
        self.assertEqual((links[0]['rel'], links[0]['target']), ('noopener noreferrer', '_blank'))
        self.assertIn('contact-sheet', ' '.join(picture['of'] for picture in home['pictures']))
        self.assertIn(waiting, json.dumps(self.get('decks')['needs']))

    def test_a_new_existing_deck_is_a_route_card_a_level_card_and_an_upload(self):
        answers = self.answers(**{'POST /api/decks': [ok({'path': '/nowhere', 'id': 'x'})],
                                  'GET /api/run': [{'status': 404,
                                                    'body': {'error': 'There is no deck there.'}}]})
        result = self.run_page(answers, [
            {'click': 'New deck'}, {'snapshot': 'routes'},
            {'click': 'Redesign an existing deck'}, {'click': 'Continue'},
            {'snapshot': 'missing'},
            {'attach': 'The deck, as a .pptx',
             'files': [{'name': 'old.pptx', 'bytes': DECK.decode('latin-1')}]},
            {'click': 'Selected changes'}, {'click': 'Polish'}, {'snapshot': 'levels'},
            {'click': 'Continue'},
            {'fill': 'A short title', 'value': 'Old deck'}, {'click': 'Continue'},
            {'snapshot': 'last'}, {'click': 'Start the deck'}])
        shots = result['snapshots']
        for route in ('Start from scratch', 'Start from a document', 'Redesign an existing deck'):
            self.assertTrue(any(name.startswith(route) for name in shots['routes']['buttons']))
        self.assertIn('Choose the file first.', shots['missing']['text'])
        self.assertIn('Choose how much changes.', shots['missing']['text'])
        self.assertEqual(shots['missing']['posts'], 0)
        for level in ('Brand only', 'Polish', 'Redesign, keep content', 'Full rework',
                      'Selected changes'):
            self.assertIn(level, shots['levels']['text'])
        self.assertIn('Chosen: old.pptx', shots['levels']['text'])
        self.assertIn('the deck itself', shots['last']['text'])
        (address, body), = self.posts(result)
        self.assertEqual(address, '/api/decks')
        self.assertEqual(set(body), {'form', 'uploads'})
        form = body['form']
        self.assertEqual((form['route'], form['level'], form['source'], form['title']),
                         ('existing', 'polish', {'kind': 'upload', 'name': 'old.pptx'},
                          'Old deck'))
        self.assertEqual(base64.b64decode(body['uploads']['old.pptx']), DECK)
        # What the page sends is what the server takes.
        made = self.post('decks', body)
        self.assertEqual(self.run_of(made['path'])['gate']['name'], 'gate:classify')

    def deck_screen(self, path: str, steps: list, **more) -> dict:
        """The deck screen, opened from home, with the deck as the runner shows it now."""
        title = self.run_of(path)['title']
        needs = any(brief['path'] == path for brief in self.get('decks')['needs'])
        answers = self.answers(**{'GET /api/run': [ok(self.run_of(path))], **more})
        return self.run_page(answers, [{'click': ('Review ' if needs else 'Open ') + title},
                                       *steps])

    def test_every_gate_of_a_deck_from_scratch_is_drawn_and_decided(self):
        path = self.started(research=True)
        seen = []
        for _ in range(12):
            gate = self.run_of(path)['gate']
            if gate is None:
                break
            name = gate['name']
            seen.append(name)
            steps = [{'see': 'Slide'}, {'see': 'The cover'}, {'snapshot': 'gate'}]
            if name == 'gate:look':
                steps += [{'click': 'Choose another brand'}, {'snapshot': 'rebrand'},
                          {'click': 'Use this brand'}, {'snapshot': 'same'},
                          {'click': 'Cancel'}]
            if name == 'gate:outline':
                steps += [{'fill': 'Title of slide 2', 'value': 'Batches, one at a time'}]
            if name == 'gate:build':
                steps += [{'click': 'Next slide'}, {'click': 'Ask for changes to this slide'},
                          {'click': 'Ask for changes'}, {'type': 'Make it shorter.'},
                          {'click': 'Send for changes'}]
            # One click approves: no second question.
            steps += [{'click': 'Approve'}, {'snapshot': 'approved'}]
            answer = ok(self.run_of(path))
            result = self.deck_screen(path, steps, **{'POST /api/decide': [answer]})
            shot = result['snapshots']['gate']
            with self.subTest(gate=name):
                self.assertEqual(shot['heading'], 'Rolling restarts')
                self.assertIn('Where it is', shot['text'])
                self.assertIn('Rehearse with Yoodli', shot['text'])
                self.assertIn('Coming later', shot['text'])
                self.assertEqual(shot['filled'], ['Approve'])
                self.assertIn('Choose another brand' if name == 'gate:look'
                              else 'Ask for changes', shot['buttons'])
                self.assertIn(gate['label'] + '.', shot['text'])
                self.assertIn('Approve, and ', shot['text'])
                approved = result['snapshots']['approved']
                self.assertEqual(approved['sheet'], '')
                self.assertTrue(any(said.startswith('Approved. It carries on by itself.')
                                    for said in approved['toasts']), approved['toasts'])
                decided = [body for address, body in self.posts(result)
                           if address == '/api/decide']
                approval = decided[-1]
                self.assertEqual((approval['gate'], approval['decision']), (name, 'approve'))
                self.assertEqual(len([body for body in decided
                                      if body['decision'] == 'approve']), 1)
            if name in ('gate:research-plan', 'gate:research'):
                self.assertIn('research', shot['text'].lower())
            if name == 'gate:look':
                self.assertIn('Made in example (light).', shot['text'])
                self.assertIn('each slide is designed on its own', shot['text'])
                self.assertTrue(any('kind=look&name=sample' in picture['of']
                                    for picture in shot['pictures']), shot['pictures'])
                asked = result['snapshots']['rebrand']['sheet']
                for said in ('Choose another brand', 'The brand’s variant', 'Use this brand'):
                    self.assertIn(said, asked)
                self.assertIn('It is made in example (light) already.',
                              result['snapshots']['same']['sheet'])
                self.assertNotIn('extra', approval)
                self.assertEqual(len(decided), 1, 'the same brand is never sent')
            if name == 'gate:outline':
                edited = approval['extra']['edited']
                self.assertEqual(edited[1]['title'], 'Batches, one at a time')
                self.assertEqual([one['id'] for one in edited],
                                 [one['id'] for one in gate['slides']])
                # The scripted workers draw the outline they are given, as it now stands.
                self.workers.outline_said = {**self.workers.outline_said, 'slides': edited}
            if name == 'gate:build':
                changes = decided[0]
                self.assertEqual((changes['decision'], changes['note'], changes['extra']),
                                 ('changes', 'Make it shorter.', {'slides': [2]}))
                self.assertTrue(shot['pictures'])
                self.assertIn('Slide 1 of', shot['text'])
            # What the page sent is what moves the deck on, for real.
            self.post('decide', approval)
        self.assertEqual(seen, ['gate:research-plan', 'gate:research', 'gate:outline',
                                'gate:look', 'gate:build'])
        view = self.run_of(path)
        self.assertEqual(view['state'], 'finished')
        result = self.deck_screen(path, [{'snapshot': 'delivered'}, {'click': 'Download .pptx'},
                                         {'snapshot': 'downloaded'}],
                                  **{'GET /api/download': [PICTURE]})
        shot = result['snapshots']['delivered']
        self.assertIn('Delivered', shot['text'])
        self.assertIn('Revision 1.', shot['text'])
        self.assertTrue(any(link['name'] == 'Open Rolling restarts in Google Slides, in a new tab'
                            and link['href'].startswith('https://') for link in shot['links']))
        self.assertIn('Publish', shot['buttons'])
        self.assertIn('The deck is downloaded.', result['snapshots']['downloaded']['toasts'])
        self.assertIn('/api/download?path=', ' '.join(
            request['address'] for request in result['requests']))

    def test_a_slide_added_and_moved_on_the_page_is_an_outline_the_slides_tool_takes(self):
        path = self.started()
        drafted = self.run_of(path)['gate']['slides']
        title = 'Watch each batch of the restart closely'
        result = self.deck_screen(path, [
            {'fill': 'A new slide’s title', 'value': title}, {'click': 'Add the slide'},
            {'click': f'Move “{title}” up'}, {'click': 'Approve'}],
            **{'POST /api/decide': [ok(self.run_of(path))]})
        approval = [body for address, body in self.posts(result)
                    if address == '/api/decide'][-1]
        edited = approval['extra']['edited']
        added = edited[-2]
        self.assertEqual([one['id'] for one in edited[:-2]],
                         [one['id'] for one in drafted[:-1]])
        self.assertEqual(edited[-1]['id'], drafted[-1]['id'])
        self.assertEqual((added['kind'], added['title']), ('content', title))
        self.assertRegex(added['id'], r'^[a-zA-Z_][a-zA-Z0-9_-]{4,40}$')
        # The scripted workers draw the outline they are given, as it now stands.
        self.workers.outline_said = {**self.workers.outline_said, 'slides': edited}
        # What the page sent is checked by the slides tool and kept, for real.
        self.post('decide', approval)
        self.assertEqual(self.run_of(path)['gate']['name'], 'gate:look')
        kept = json.loads((Path(path) / 'outline.json').read_text())
        self.assertEqual([one['id'] for one in kept['slides']], [one['id'] for one in edited])

    def test_a_slide_added_to_a_deck_presented_live_carries_its_notes(self):
        title = 'Watch each batch of the restart closely'
        said = 'Say why each batch is watched.'
        with mock.patch.object(build, 'DELIVERY', 'live'):
            self.workers.outline_said = {**self.workers.outline_said, 'delivery': 'live'}
            path = self.started()
            self.assertEqual(self.run_of(path)['gate']['delivery'], 'live')
            result = self.deck_screen(path, [
                {'fill': 'A new slide’s title', 'value': title}, {'click': 'Add the slide'},
                {'snapshot': 'unnoted'},
                {'fill': 'What the presenter says on it', 'value': said},
                {'click': 'Add the slide'}, {'snapshot': 'added'},
                {'click': 'Approve'}],
                **{'POST /api/decide': [ok(self.run_of(path))]})
            self.assertIn('A deck presented live needs what the presenter says on each slide.',
                          result['snapshots']['unnoted']['text'])
            self.assertIn('Notes: ' + said, result['snapshots']['added']['text'])
            approval = [body for address, body in self.posts(result)
                        if address == '/api/decide'][-1]
            added = approval['extra']['edited'][-1]
            self.assertEqual((added['title'], added['notes'], added['rhythm']),
                             (title, said, 'breathing'))
            self.workers.outline_said = {**self.workers.outline_said,
                                         'slides': approval['extra']['edited']}
            # What the page sent is checked by the slides tool and kept, for real.
            self.post('decide', approval)
            self.assertEqual(self.run_of(path)['gate']['name'], 'gate:look')
            kept = json.loads((Path(path) / 'outline.json').read_text())
            self.assertEqual(kept['slides'][-1]['notes'], said)

    def test_a_deck_made_as_powerpoint_is_sent_to_google_slides_from_its_screen(self):
        path = self.started()
        self.slides.run.drive = False
        for gate in ('gate:outline', 'gate:look', 'gate:build'):
            self.decided(path, gate)
        before = self.run_of(path)
        self.slides.run.drive = True
        sent = self.post('deliver', {'path': path})
        result = self.deck_screen(path, [
            {'snapshot': 'fallback'}, {'click': 'Deliver to Google Slides'},
            {'snapshot': 'sent'}], **{'GET /api/run': [ok(before), ok(sent)],
                                      'POST /api/deliver': [ok(sent)]})
        fallback = result['snapshots']['fallback']
        self.assertIn("Google isn't connected, so this deck was made as a PowerPoint file.",
                      fallback['text'])
        self.assertIn('Deliver to Google Slides', fallback['buttons'])
        self.assertEqual([body for address, body in self.posts(result)],
                         [{'path': path}])
        self.assertIn('The deck is in Google Slides now.', result['snapshots']['sent']['toasts'])
        self.assertNotIn('Deliver to Google Slides', result['snapshots']['sent']['buttons'])
        self.assertIn('Revision 2.', result['snapshots']['sent']['text'])

    def test_an_existing_deck_shows_its_slides_at_classify(self):
        path = self.started(route='existing', level='polish',
                            source={'kind': 'upload', 'name': 'old.pptx'},
                            uploads={'old.pptx': DECK})
        result = self.deck_screen(path, [{'snapshot': 'classify'}])
        shot = result['snapshots']['classify']
        self.assertIn('Your deck has 3 slides.', shot['text'])
        self.assertIn('Slide 1 of 3', shot['text'])
        self.assertTrue(shot['pictures'])
        for picture in shot['pictures']:
            self.assertIn('kind=original&number=1', picture['of'])

    def test_the_build_gate_shows_a_slide_s_note(self):
        path = self.started()
        self.to_gate(Path(path), 'gate:build')
        view = self.run_of(path)
        said = ("This slide is drawn with a title because its picture can't be carried onto "
                'a layout without one.')
        view['gate']['slides'][0]['note'] = said
        answers = self.answers(**{'GET /api/run': [ok(view)]})
        result = self.run_page(answers, [{'click': 'Review Rolling restarts'},
                                         {'see': said}, {'snapshot': 'build'}])
        self.assertIn(said, result['snapshots']['build']['text'])

    def test_a_deck_built_from_an_existing_one_shows_each_slide_before_and_after(self):
        # The stand-in workers cannot rebuild the stand-in deck, so the build gate of a deck
        # from scratch is given the before and after an existing deck's gate has.
        path = self.started()
        self.to_gate(Path(path), 'gate:build')
        view = self.run_of(path)
        view['gate']['pairs'] = [{'number': 1, 'before': {'kind': 'original', 'ref': 1},
                                  'after': {'kind': 'build', 'ref': 1}}]
        view['gate']['changed'] = [1]
        answers = self.answers(**{'GET /api/run': [ok(view)]})
        result = self.run_page(answers, [{'click': 'Review Rolling restarts'},
                                         {'see': 'Slide 1 before'}, {'snapshot': 'build'}])
        shot = result['snapshots']['build']
        for shown in ('Before', 'After', 'Changed', 'Built again after your changes: slide 1.'):
            self.assertIn(shown, shot['text'])
        kinds = {picture['of'].split('kind=')[1].split('&')[0] for picture in shot['pictures']}
        self.assertEqual(kinds, {'original', 'build'})

    def test_another_brand_chosen_on_the_page_has_its_cover_drawn_again(self):
        path = self.started()
        self.decided(path, 'gate:outline')
        self.assertEqual(self.run_of(path)['gate']['name'], 'gate:look')
        result = self.deck_screen(path, [
            {'click': 'Choose another brand'}, {'fill': 'The brand’s variant', 'value': 'dark'},
            {'click': 'Use this brand'}, {'snapshot': 'sent'}],
            **{'POST /api/decide': [ok(self.run_of(path))]})
        (address, body), = self.posts(result)
        self.assertEqual((address, body['gate'], body['decision'], body['extra']),
                         ('/api/decide', 'gate:look', 'changes',
                          {'brand': 'example', 'variant': 'dark'}))
        self.assertNotIn('note', body)
        self.assertEqual(result['snapshots']['sent']['sheet'], '')
        # What the page sent is what the runner takes: the cover comes back in the new brand.
        self.post('decide', body)
        gate = self.run_of(path)['gate']
        self.assertEqual((gate['name'], gate['made_in'], gate['round']),
                         ('gate:look', 'example (dark)', 2))

    def test_an_approval_that_is_refused_is_said_on_the_deck_s_screen(self):
        path = self.started()
        refused = {'status': 409, 'body': {'error': 'The outline is not waiting for a '
                                                    'decision.'}}
        result = self.deck_screen(path, [{'click': 'Approve'}, {'snapshot': 'refused'}],
                                  **{'POST /api/decide': [refused]})
        shot = result['snapshots']['refused']
        self.assertEqual(shot['sheet'], '')
        self.assertIn('The outline is not waiting for a decision. Nothing was decided.',
                      shot['text'])
        self.assertIn('Approve', shot['buttons'])

    def test_a_document_said_to_be_wrong_is_corrected_with_the_approval(self):
        path = self.started(route='document', research=False,
                            source={'kind': 'paste', 'text': 'Notes to build a talk from.'})
        gate = self.run_of(path)['gate']
        self.assertEqual((gate['name'], gate['verdict']), ('gate:classify', 'material'))
        result = self.deck_screen(path, [{'snapshot': 'gate'}, {'click': 'That’s wrong'},
                                         {'snapshot': 'wrong'}, {'click': 'Approve'}],
                                  **{'POST /api/decide': [ok(self.run_of(path))]})
        self.assertIn('It reads as material to build from.',
                      result['snapshots']['gate']['text'])
        self.assertIn('It will be taken as a finished script for the slides instead.',
                      result['snapshots']['wrong']['text'])
        (_, body), = self.posts(result)
        self.assertEqual(body['extra'], {'kind': 'spec'})
        self.post('decide', body)
        self.assertEqual(self.record(Path(path))['classified'], 'spec')

    def test_decks_status_settings_and_published_are_drawn_from_the_runners_answers(self):
        self.started(title='Rolling restarts')
        self.started(title='Capacity planning')
        answers = self.answers(**{'GET /api/status': [ok(self.get('status'))],
                                  'GET /api/published': [ok(self.get('published'))]})
        result = self.run_page(answers, [
            {'click': 'Decks'}, {'snapshot': 'decks'},
            {'fill': 'Find a deck', 'value': 'capacity', 'stay': True}, {'snapshot': 'found'},
            {'click': 'Published'}, {'snapshot': 'published'},
            {'click': 'Status'}, {'snapshot': 'status'},
            {'click': 'Settings'}, {'snapshot': 'settings'}])
        shots = result['snapshots']
        self.assertIn('2 decks.', shots['decks']['text'])
        self.assertIn('1 of 2 decks match.', shots['found']['text'])
        self.assertNotIn('Open Rolling restarts', shots['found']['buttons'])
        self.assertIn('Open Capacity planning', shots['found']['buttons'])
        self.assertIn('Nothing is published yet', shots['published']['text'])
        for shown in ('Running on this computer', 'Rolling restarts', 'Cost so far',
                      'This computer'):
            self.assertIn(shown, shots['status']['text'])
        for shown in ('Workspace', 'What a new deck starts with', 'When this page is closed',
                      'Updates'):
            self.assertIn(shown, shots['settings']['text'])
        self.assertEqual(self.posts(result), [])

    def test_status_says_what_the_shared_file_says_and_offers_to_join_its_team(self):
        described = self.get('setup')
        other = 'git@example.com:team/other-decks.git'
        moved = {**described, 'shared_problem': None,
                 'team_moved': {'repository': other, 'branch': 'main',
                                'says': 'The team repository your studios share is now '
                                        f'{other}.'},
                 'shared_notice': 'Presentation Studio now keeps the values every studio '
                                  'shares only in one file.'}
        seen = {**moved, 'shared_notice': None}
        answers = self.answers(**{'GET /api/setup': [ok(moved)],
                                  'GET /api/status': [ok(self.get('status'))],
                                  'POST /api/shared': [ok(seen)]})
        result = self.run_page(answers, [
            {'click': 'Status'}, {'snapshot': 'status'}, {'click': 'Got it'},
            {'snapshot': 'seen'}, {'click': 'Join it'}, {'snapshot': 'joining'}])
        shots = result['snapshots']
        for shown in ('Your other studios', moved['team_moved']['says'],
                      moved['shared_notice']):
            self.assertIn(shown, shots['status']['text'])
        self.assertNotIn(moved['shared_notice'], shots['seen']['text'])
        self.assertEqual(shots['joining']['fields']['The repository’s address'], other)
        self.assertEqual(self.posts(result)[0], ('/api/shared', {'seen': True}))
        # Joining is checked first, as any set-up is: nothing moves until it is saved.
        self.assertEqual([address for address, _ in self.posts(result)[1:]],
                         ['/api/setup/check'])

    def test_a_deck_is_paused_and_a_refusal_changes_nothing(self):
        path = self.started()
        refused = {'status': 409, 'body': {'error': 'Only a deck that is working can be '
                                                    'paused. This one is waiting for you.'}}
        result = self.deck_screen(path, [{'snapshot': 'waiting'}, {'click': 'Stop'},
                                         {'snapshot': 'stopped'}],
                                  **{'POST /api/run': [refused]})
        self.assertIn('Undo the last step', result['snapshots']['waiting']['buttons'])
        self.assertIn('Nothing was changed.', result['snapshots']['stopped']['text'])
        self.assertEqual(self.posts(result), [('/api/run', {'path': path, 'action': 'stop'})])


    def brand_upkeep(self) -> dict:
        """What the runner's own upkeep reports with a brand skill's repository named and no
        brand skill installed: the brand skill offered from its repository."""
        from dataclasses import replace
        from runner import settings, upkeep
        settings.save(replace(settings.load(), brand_repository=ADDRESS))
        keep = upkeep.Upkeep(home_dir=self.base / 'home', root=self.base / 'root',
                             installer=self.base / 'no-installer' / 'install.py')
        keep.remember_brand(ADDRESS, {
            'v2026.6.0': {'tag': 'v2026.6.0', 'version': '2026.6.0', 'commit': 'b' * 40},
            'v0.13.1': {'tag': 'v0.13.1', 'version': '0.13.1',
                        'commit': 'c3405eee0aad' + 'a' * 28}})
        installed, self.brand = self.brand, None
        try:
            keep.check(repair=False)
        finally:
            self.brand = installed
        return keep.report()

    def test_home_offers_the_brand_skill_and_asks_before_it_is_installed(self):
        self.started()
        found = self.brand_upkeep()
        offer = found['versions']['brand']
        self.assertEqual((offer['offered'], offer['action'], offer['release']),
                         (True, 'Install', 'v0.13.1'))
        running = f'Fetching v0.13.1 from {ADDRESS} and running its own installer. This can ' \
                  'take a few minutes.'
        busy = {**found, 'versions': {**found['versions'], 'brand': {
            **offer, 'offered': False, 'state': 'running', 'since': '2026-10-14T09:05:00Z',
            'says': running}}}
        down = ('A deck on this computer is working now, and a step in hand keeps using the '
                'brand skill it started with. Pause it, or wait until it stops for you, then '
                'install.')
        answers = self.answers(**{
            'GET /api/setup': [ok({**self.get('setup'), 'upkeep': found})],
            'POST /api/brand/install': [{'status': 409, 'body': {'error': down}},
                                        ok({'upkeep': busy})]})
        result = self.run_page(answers, [
            {'snapshot': 'home'},
            {'click': 'Install the brand skill'}, {'snapshot': 'asked'},
            {'click': 'Cancel'}, {'snapshot': 'cancelled'},
            {'click': 'Install the brand skill'}, {'click': 'Install it now'},
            {'snapshot': 'refused'},
            {'click': 'Install it now'}, {'snapshot': 'installing'}])
        shots = result['snapshots']
        for said in ('Newer versions are ready for this computer:',
                     'brand skill 0.13.1, which is missing',
                     'No brand skill is installed, so a deck stops where it first needs '
                     'your brand.'):
            self.assertIn(said, shots['home']['text'])
        asked = shots['asked']['sheet']
        for said in ('Install the brand skill 0.13.1?', 'What is installed',
                     'Release v0.13.1, at revision c3405eee0aad.', f'From {ADDRESS}.',
                     'Its own installer is run, and told to leave harness-research alone.',
                     'Where it would put in its own harness-slides in place of the one '
                     'Presentation Studio uses, nothing is run, and you are told.',
                     'Install only from a repository you trust.'):
            self.assertIn(said, asked)
        self.assertIn(down + ' Nothing was changed.', shots['refused']['sheet'])
        done = shots['installing']
        self.assertEqual(done['sheet'], '')
        self.assertIn('Installing the brand skill. Home and the Status screen say how it goes.',
                      done['toasts'])
        self.assertIn(running, done['text'])
        self.assertNotIn('Install the brand skill', done['buttons'], 'one install at a time')
        self.assertEqual(self.posts(result), [('/api/brand/install', {'release': 'v0.13.1'})]
                         * 2, 'nothing before the yes')

    def test_the_brand_skills_repository_is_checked_and_saved_in_settings(self):
        described = self.get('setup')
        saved = {**described, 'brand': {**described['brand'], 'repository': ADDRESS,
                                         'release': 'v0.13.1'}}
        cannot = ("The brand skill's repository could not be read. git could not sign in to "
                  "it without asking (could not read Username for 'https://github.com': "
                  'terminal prompts disabled). Sign git in with an account that may read it, '
                  'through its credential helper for an https address or an ssh key for an '
                  'ssh one, then try again.')
        answers = self.answers(**{
            'GET /api/setup': [ok(described)] * 3 + [ok(saved)],
            'POST /api/brand': [{'status': 400, 'body': {'error': cannot}}, ok(saved)]})
        result = self.run_page(answers, [
            {'click': 'Settings'}, {'snapshot': 'empty'},
            {'fill': 'Its repository', 'value': ADDRESS},
            {'fill': 'Which release', 'value': 'v0.13.1'},
            {'click': 'Check and save'}, {'snapshot': 'refused'},
            {'click': 'Check and save'}, {'snapshot': 'saved'}])
        shots = result['snapshots']
        for said in ('Brand skill', 'Your brand skill is released from a repository of its '
                     'own.', 'A brand skill you installed yourself is still found and used.',
                     'Empty for the newest'):
            self.assertIn(said, shots['empty']['text'])
        self.assertIn(cannot + ' Nothing was changed.', shots['refused']['text'])
        self.assertIn(f'Installed from {ADDRESS}, release v0.13.1.', shots['saved']['text'])
        self.assertIn('Saved. The Status screen shows which release can be installed.',
                      shots['saved']['toasts'])
        self.assertEqual(self.posts(result), [('/api/brand', {
            'repository': ADDRESS, 'release': 'v0.13.1',
            'shared_seen': described['shared']})] * 2)

    def test_the_brand_skills_repository_is_one_every_studio_shares(self):
        described = self.get('setup')
        shared = {'brand': {'repository': ADDRESS}}
        stale = ("The brand skill's repository was changed in another studio while this was "
                 'open, so nothing was saved. Look again, then save.')
        now = {**described, 'shared': shared, 'shared_problem': None,
               'brand': {**described['brand'], 'repository': ADDRESS, 'release': None}}
        later = {**now, 'shared': {'brand': {'repository': ADDRESS, 'release': 'v1.0.0'}}}
        answers = self.answers(**{'GET /api/setup': [ok(now), ok(later)],
                                  'POST /api/brand': [{'status': 400, 'body': {'error': stale}},
                                                      ok(later)]})
        result = self.run_page(answers, [
            {'click': 'Settings'}, {'snapshot': 'settings'},
            {'fill': 'Which release', 'value': 'v0.13.1'},
            {'click': 'Check and save'}, {'snapshot': 'refused'},
            {'poll': True}, {'click': 'Check and save'}])
        shots = result['snapshots']
        self.assertIn('Every studio on this computer shares the repository and release named '
                      'here, so saving changes them for all of them.', shots['settings']['text'])
        self.assertIn(stale + ' Nothing was changed.', shots['refused']['text'])
        # What it was shown goes with it, and after a refusal, what it has been shown since.
        self.assertEqual(self.posts(result), [
            ('/api/brand', {'repository': ADDRESS, 'release': 'v0.13.1',
                            'shared_seen': shared}),
            ('/api/brand', {'repository': ADDRESS, 'release': 'v0.13.1',
                            'shared_seen': later['shared']})])

    def test_without_a_brand_skill_a_new_deck_can_still_be_started(self):
        self.brand = None
        self.engine.deck_needs(fresh=True)
        described = self.get('setup')
        self.assertEqual(described['brand']['default'], {'brand': None, 'variant': None})
        answers = self.answers(**{'POST /api/decks': [ok({'path': '/nowhere', 'id': 'x'})],
                                  'GET /api/run': [{'status': 404,
                                                    'body': {'error': 'There is no deck there.'}}]})
        result = self.run_page(answers, [
            {'click': 'New deck'}, {'click': 'Start from scratch'}, {'click': 'Continue'},
            {'fill': 'A short title', 'value': 'Rolling restarts'}, {'click': 'Continue'},
            {'snapshot': 'last'}, {'click': 'Start the deck'}])
        self.assertIn('A deck can still be started: it is made up to the point it needs your '
                      'brand, and waits there.', result['snapshots']['last']['text'])
        (address, body), = self.posts(result)
        self.assertEqual((address, body['form']['brand'], body['form']['variant']),
                         ('/api/decks', '', None))
        # What the page sends is what the server takes, and the deck stops at its brand.
        made = self.post('decks', body)
        self.assertEqual(self.run_of(made['path'])['state'], 'stopped')

if __name__ == '__main__':
    unittest.main()
