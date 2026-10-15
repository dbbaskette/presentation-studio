"""The page's script, read as text: what it asks the server, where it may send a person,
how it places what the server says, and the words it uses.

Nothing is run here; tests/test_desk.py runs the page in a document with no parser.
"""
import re
import unittest

import helpers
import server
from runner import page

PAGE = helpers.SCRIPTS / 'desk'
FORBIDDEN_WORDS = re.compile(r'\b(artifacts?|stale|lineage)\b', re.IGNORECASE)
TRAINING_WORDS = re.compile(r'\btrainings?\b', re.IGNORECASE)
SVG = 'http://www.w3.org/2000/svg'


def read(name: str) -> str:
    return (PAGE / name).read_text(encoding='utf-8')


class ApiTests(unittest.TestCase):
    """Every address the page asks for is one the server answers, in the way it answers it."""

    def setUp(self):
        self.script = read('app.js')
        self.reads = set(page.RunnerPage.reads)
        self.writes = set(page.RunnerPage.writes)

    def test_every_address_read_is_one_the_server_reads(self):
        asked = set(re.findall(r"\bask\('([\w/-]+)'", self.script))
        # A slide's picture and the deck itself are bytes, fetched with the key in a header.
        asked |= set(re.findall(r"\breach\('([\w/-]+)\?", self.script))
        self.assertTrue({'decks', 'run', 'setup', 'slide', 'download'} <= asked, asked)
        for name in asked:
            with self.subTest(name):
                self.assertIn('/api/' + name, self.reads)

    def test_every_change_sent_is_one_the_server_takes(self):
        sent = set(re.findall(r"\bsend\('([\w/-]+)'", self.script))
        self.assertTrue({'decks', 'decide', 'run', 'answer', 'setup', 'setup/check'} <= sent,
                        sent)
        for name in sent:
            with self.subTest(name):
                self.assertIn('/api/' + name, self.writes)

    def test_nothing_is_asked_by_an_address_built_some_other_way(self):
        # Every request goes through one fetch, to the page's own server.
        self.assertEqual(re.findall(r"fetch\(\s*([^,)]+)", self.script), ["'/api/' + endpoint"])
        for elsewhere in ('XMLHttpRequest', 'WebSocket', 'EventSource', 'sendBeacon', 'import(',
                          'localStorage', 'sessionStorage', 'document.cookie'):
            self.assertNotIn(elsewhere, self.script)

    def test_an_upload_is_read_with_filereader_and_sent_in_base64(self):
        self.assertIn('new FileReader()', self.script)
        self.assertIn('readAsDataURL', self.script)
        self.assertRegex(self.script, r"send\('decks', \{ form[^}]*uploads")


class LinkTests(unittest.TestCase):
    """The page loads nothing from anywhere else, and links out only where the server said."""

    def test_no_address_outside_this_computer_is_written_into_the_page(self):
        for name in ('app.js', 'index.html', 'deck.css'):
            with self.subTest(name):
                text = read(name).replace(f"'{SVG}'", "''")
                self.assertNotRegex(text, r'(?i)\b(?:https?|wss?|ftp|data|blob):')
        self.assertEqual(read('app.js').count(SVG), 1)

    def test_a_link_out_is_only_a_web_address_the_server_returned(self):
        script = read('app.js')
        # Two places set where a link goes: a link the server sent, once it is a web address,
        # and the deck downloaded into memory.
        targets = re.findall(r'\.href = ([^;]+);', script)
        self.assertEqual(sorted(targets), ['address', 'held'])
        out = script[script.index('function outLink('):]
        out = out[:out.index('\n}\n')]
        self.assertIn("WEB_LINK.test(String(address || ''))", out)
        self.assertIn("node.rel = 'noopener noreferrer'", out)
        self.assertIn("node.target = '_blank'", out)

    def test_the_shell_loads_only_its_own_files(self):
        shell = read('index.html')
        self.assertEqual(sorted(re.findall(r'(?:src|href)="([^"]*)"', shell)),
                         ['#main', 'app.js', 'deck.css', 'markdown.js', 'style.css'])
        for name in ('/deck.css', '/style.css', '/app.js', '/markdown.js'):
            self.assertIn(name, server.PAGE)
        styles = read('deck.css')
        for loads in ('url(', '@import', '@font-face'):
            self.assertNotIn(loads, styles)


class MarkupTests(unittest.TestCase):
    def test_no_value_is_ever_treated_as_markup(self):
        for name in ('app.js', 'markdown.js'):
            script = read(name)
            for risky in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write',
                          'createContextualFragment', 'DOMParser', 'srcdoc', 'eval(',
                          'Function(', "setAttribute('style'", "setAttribute('href'",
                          "setAttribute('src'", 'cssText'):
                with self.subTest(name=name, risky=risky):
                    self.assertNotIn(risky, script)
            self.assertIn('textContent', script)

    def test_a_document_is_drawn_by_the_vendored_markdown_only(self):
        script = read('app.js')
        self.assertIn('window.TrainingStudioMarkdown.render(', script)
        self.assertEqual(script.count('.render('), 1)


class WordTests(unittest.TestCase):
    def test_no_word_a_person_should_not_read(self):
        for name in ('app.js', 'index.html', 'deck.css'):
            with self.subTest(name):
                self.assertNotRegex(read(name), FORBIDDEN_WORDS)

    def test_a_deck_is_called_a_deck(self):
        for name in ('app.js', 'index.html'):
            with self.subTest(name):
                text = read(name).replace('TrainingStudioMarkdown', '')
                self.assertNotRegex(text, TRAINING_WORDS)
                self.assertNotIn('Training Studio', text)
        self.assertIn('<title>Presentation Studio</title>', read('index.html'))

    def test_shared_values_are_never_sent_for_all_studios_by_a_switch(self):
        script = read('app.js')
        self.assertNotIn('for_all_studios', script)
        self.assertIn('shared by every studio on this computer', script)

    def test_no_brand_is_named(self):
        # Any brand: the brands offered are only those the brand skill on this computer has.
        for name in ('app.js', 'index.html', 'deck.css'):
            with self.subTest(name):
                self.assertNotRegex(read(name), r'(?i)tanzu|vmware|broadcom')

    def test_rehearsing_with_yoodli_is_coming_later(self):
        script = read('app.js')
        self.assertIn('Rehearse with Yoodli', script)
        self.assertIn('Coming later', script)


if __name__ == '__main__':
    unittest.main()
