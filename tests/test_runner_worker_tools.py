"""The worker tools: every refusal, where a quote sits, and the rules for fetching a page.

Nothing here touches the network: pages come from a pretend web.
"""
import functools
import gzip
import io
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401
import runner_support
from runner_support import OUTLINE, PAGE, PLAN, PUBLIC, Brand, JobCase, Slides, drawn, png

from runner import brand as brand_skill
from runner import slides as slides_tool
from runner import worker_tools
from runner.steps import build
from workspace import WorkspaceError

DOCS = 'https://docs.example.com/restarts'
PLANS = {'research-plan': {'kind': 'research-plan', 'scope': 'public-web'}}
QUOTE = 'Capacity holds only when more than one instance is running.'
MAJOR = {'slide': 'what-it-does', 'question': 3, 'severity': 'major',
         'note': 'One of two equal labels is set larger than the other.',
         'fix': 'Set both labels alike.'}
SAID = {'slide': 'the-objection', 'question': 4, 'severity': 'major', 'about': 'content',
        'note': 'The caveat pulls away from what the title claims.'}


class PrepareTests(JobCase):
    def test_a_prepared_folder_says_what_the_job_may_read_and_must_hand_back(self):
        worker_tools.prepare(self.job, inputs={'intake': 'For platform leads.\n'},
                             artifacts=PLANS, fetch=False)
        job = json.loads((self.job / 'job.json').read_text())
        self.assertEqual(job['inputs'], [{'name': 'intake', 'file': 'inputs/1.txt',
                                          'chars': 20}])
        self.assertEqual((job['finding'], job['fetch'], job['ask']), (None, False, True))
        self.assertEqual((self.job / 'inputs' / '1.txt').read_text(), 'For platform leads.\n')

    def test_a_folder_is_prepared_once(self):
        worker_tools.prepare(self.job)
        with self.assertRaisesRegex(WorkspaceError, 'already holds a job'):
            worker_tools.prepare(self.job)

    def test_a_draft_needs_a_kind_that_can_be_checked(self):
        with self.assertRaisesRegex(WorkspaceError, 'one of research-plan, outline, section'):
            worker_tools.prepare(self.job, artifacts={'poem': {'kind': 'poem'}})
        with self.assertRaisesRegex(WorkspaceError, 'scope is one of'):
            worker_tools.prepare(self.job, artifacts={'p': {'kind': 'research-plan',
                                                            'scope': 'anything'}})
        for training in ('blueprint', 'document', 'brief', 'scenario', 'yoodli'):
            self.assertNotIn(training, worker_tools.VALIDATORS)

    def test_a_finding_needs_a_question_id(self):
        with self.assertRaisesRegex(WorkspaceError, 'not a research question ID'):
            worker_tools.prepare(self.job, finding='Instance Min')

    def test_an_offered_source_needs_its_details(self):
        with self.assertRaisesRegex(WorkspaceError, 'needs: origin, file'):
            worker_tools.prepare(self.job, sources=[{'title': 'Handbook', 'text': 'Words.'}])

    def test_tools_need_a_prepared_folder(self):
        with self.assertRaisesRegex(WorkspaceError, 'not a job folder'):
            worker_tools.WorkerTools(self.job)
        with self.assertRaisesRegex(WorkspaceError, 'not a job folder'):
            worker_tools.collect(self.job)

    def test_the_command_starts_this_server_for_that_folder(self):
        command = worker_tools.command(self.job)
        self.assertEqual(command[1], '-I')
        self.assertTrue(command[2].endswith('worker_tools.py'))
        self.assertEqual(command[3:], ['--job', str(self.job)])


class InputTests(JobCase):
    def test_inputs_are_listed_by_name_with_their_size(self):
        tools = self.tools(inputs={'intake': 'Short.\n', 'findings': 'x' * 50_000})
        listed = self.ok(tools.list_inputs())
        self.assertIn('- intake: 7 characters', listed)
        self.assertIn('- findings: 50,000 characters, in 3 parts', listed)

    def test_a_job_with_no_inputs_says_so(self):
        self.assertIn('no inputs', self.ok(self.tools().list_inputs()))

    def test_saved_sources_are_listed_too(self):
        tools = self.tools(finding='instance-min', sources=[
            {'title': 'Operations handbook', 'origin': 'Supplied by the team',
             'text': 'Restart one batch at a time.', 'file': 'sources/handbook.txt'}])
        listed = self.ok(tools.list_inputs())
        self.assertIn('- s1: "Operations handbook", 29 characters', listed)
        self.assertNotIn('read_input', listed)

    def test_a_short_input_is_read_whole(self):
        tools = self.tools(inputs={'intake': 'For platform leads.\n'})
        self.assertEqual(self.ok(tools.read_input('intake')), 'For platform leads.\n')

    def test_a_long_input_is_read_in_parts_that_end_at_line_ends(self):
        text = ''.join(f'Line {number} of the findings.\n' for number in range(2500))
        tools = self.tools(inputs={'findings': text})
        pieces = worker_tools.parts(text)
        self.assertGreater(len(pieces), 2)
        self.assertEqual(''.join(pieces), text)
        self.assertTrue(all(len(piece) <= worker_tools.PART and piece.endswith('\n')
                            for piece in pieces))
        first = self.ok(tools.read_input('findings'))
        self.assertTrue(first.startswith(f'[findings: part 1 of {len(pieces)}; ask for part '
                                         '2 for more]\n\nLine 0 of'))
        last = self.ok(tools.read_input('findings', str(len(pieces))))
        self.assertIn('this is the last part', last)
        self.assertTrue(last.endswith(pieces[-1]))

    def test_text_with_no_line_ends_is_still_cut(self):
        self.assertEqual([len(piece) for piece in worker_tools.parts('x' * 25, size=10)],
                         [10, 10, 5])

    def test_an_unknown_input_is_refused_with_the_names_there_are(self):
        tools = self.tools(inputs={'intake': 'Text.'})
        self.assertIn('This job\'s inputs: intake', self.refused(tools.read_input('notes')))

    def test_a_part_that_does_not_exist_is_refused(self):
        tools = self.tools(inputs={'intake': 'Text.'})
        self.assertIn('there is no part 2', self.refused(tools.read_input('intake', 2)))
        self.assertIn('must be a whole number', self.refused(tools.read_input('intake', 'two')))

    def test_wrong_arguments_are_refused_with_the_ones_it_takes(self):
        tools = self.tools(inputs={'intake': 'Text.'})
        said = self.refused(tools.call('read_input', {'title': 'intake'}))
        self.assertEqual(said, 'Wrong arguments for read_input: it takes name, part.')

    def test_a_tool_that_does_not_exist_is_refused(self):
        self.assertEqual(self.refused(self.tools().call('run_command', {'command': 'ls'})),
                         'There is no tool called run_command.')

    def test_every_call_is_logged(self):
        tools = self.tools(inputs={'intake': 'Text.'})
        tools.read_input('intake')
        tools.read_input('notes')
        tools.call('run_command', {})
        tools.call('read_input', {'title': 'x'})
        log = [json.loads(line) for line in (self.job / 'tools.log').read_text().splitlines()]
        self.assertEqual([(entry['tool'], entry['ok']) for entry in log],
                         [('read_input', True), ('read_input', False), ('run_command', False),
                          ('read_input', False)])
        self.assertEqual(log[0]['given'], {'name': 'intake'})
        self.assertEqual(log[0]['answer'], 'Text.')

    def test_a_tool_that_breaks_is_reported_and_logged(self):
        tools = self.tools(inputs={'intake': 'Text.'})
        with mock.patch.object(worker_tools, 'parts', side_effect=RuntimeError('boom')):
            said = self.refused(tools.call('read_input', {'name': 'intake'}))
        self.assertIn('The tool failed and nothing was kept (RuntimeError: boom)', said)
        self.assertEqual(self.ok(tools.read_input('intake')), 'Text.')


class PlanTests(JobCase):
    def submit(self, plan, **spec):
        tools = self.tools() if (self.job / 'job.json').exists() else self.tools(
            artifacts={'research-plan': {'kind': 'research-plan', 'scope': 'public-web',
                                         **spec}})
        text = plan if isinstance(plan, str) else json.dumps(plan)
        return tools.submit_artifact('research-plan', text)

    def test_an_accepted_plan_is_kept_whole(self):
        self.assertEqual(self.ok(self.submit(PLAN)), 'Accepted: research-plan.')
        kept = worker_tools.collect(self.job)['artifacts']['research-plan']
        plan = json.loads(kept['text'])
        self.assertEqual(kept['kind'], 'research-plan')
        self.assertEqual(kept['path'], self.job / 'accepted' / 'research-plan.json')
        self.assertEqual((plan['topic'], plan['purpose'], plan['scope'], plan['sources']),
                         ('Rolling restarts', 'planning', 'public-web', []))
        self.assertEqual(plan['items'][0], {
            'id': 'instance-min', 'claim': None,
            'question': 'How many instances keep capacity during a restart?',
            'public_query': 'rolling restart minimum instances'})
        self.assertEqual(worker_tools.check_research_plan(plan)['status'], 'passed')
        self.assertEqual(kept['checks'][0]['status'], 'passed')

    def test_the_runner_sets_the_scope_the_sources_and_the_purpose(self):
        chosen = [{'id': 'handbook', 'title': 'Handbook', 'origin': 'Supplied',
                   'file': 'sources/handbook.txt'}]
        written = {**PLAN, 'scope': 'public-web', 'purpose': 'fact-check',
                   'sources': [{'id': 'made-up'}], 'input_files': ['intake.md']}
        self.ok(self.submit(written, scope='supplied-only', sources=chosen))
        plan = json.loads(worker_tools.collect(self.job)['artifacts']['research-plan']['text'])
        self.assertEqual((plan['purpose'], plan['scope'], plan['sources']),
                         ('planning', 'supplied-only', chosen))
        self.assertNotIn('input_files', plan)
        self.assertEqual([item['public_query'] for item in plan['items']], [None, None])

    def test_text_that_is_not_json_is_refused(self):
        self.assertIn('not valid JSON', self.refused(self.submit('Here are my questions:')))
        self.assertIn('must be a JSON object', self.refused(self.submit('["instance-min"]')))

    def test_the_cores_own_check_decides(self):
        twice = {**PLAN, 'items': [PLAN['items'][0], PLAN['items'][0]]}
        self.assertIn('Question ID instance-min is used more than once.',
                      self.refused(self.submit(twice)))
        self.assertIn('"items" must hold 1 to 30 questions.',
                      self.refused(self.submit({'topic': 'Rolling restarts', 'items': []})))
        self.assertIn('Question 1 has no question text.',
                      self.refused(self.submit({**PLAN, 'items': ['instance-min']})))

    def test_a_plan_needs_a_topic(self):
        self.assertIn('"topic" must say what the deck is about',
                      self.refused(self.submit({'items': PLAN['items']})))

    def test_a_public_query_is_search_words_only(self):
        for query in ('https://example.com/restarts', 'restarts/rolling', 'ask someone@x', ''):
            with self.subTest(query):
                asked = {**PLAN, 'items': [{**PLAN['items'][0], 'public_query': query}]}
                self.assertIn('instance-min: "public_query" is a few public search words',
                              self.refused(self.submit(asked)))

    def test_a_question_asks_one_thing(self):
        rambling = {**PLAN, 'items': [{**PLAN['items'][0], 'question': 'Why? ' * 900}]}
        self.assertIn('instance-min: the question is too long; ask one thing.',
                      self.refused(self.submit(rambling)))

    def test_a_refused_plan_keeps_nothing_and_says_why_afterwards(self):
        self.refused(self.submit('nonsense'))
        found = worker_tools.collect(self.job)
        self.assertEqual(found['artifacts'], {})
        self.assertIn('not valid JSON', found['problems']['research-plan'][0])


class DraftTests(JobCase):
    def test_a_job_with_no_draft_refuses_one(self):
        said = self.refused(self.tools().submit_artifact('research-plan', json.dumps(PLAN)))
        self.assertEqual(said, 'This job has no draft to hand back.')

    def test_a_draft_under_another_name_is_refused(self):
        said = self.refused(self.tools(artifacts=PLANS).submit_artifact('outline', 'x'))
        self.assertEqual(said, 'This job hands back research-plan, not "outline". Use that '
                         'name.')

    def test_an_empty_draft_is_refused(self):
        tools = self.tools(artifacts=PLANS)
        self.assertIn('The text is empty',
                      self.refused(tools.submit_artifact('research-plan', ' ')))
        self.assertIn('The text is empty',
                      self.refused(tools.call('submit_artifact', {'name': 'research-plan',
                                                                  'text': None})))

    def test_a_draft_can_be_handed_back_only_so_many_times(self):
        tools = self.tools(artifacts=PLANS)
        for attempt in range(1, worker_tools.SUBMISSIONS + 1):
            said = self.refused(tools.submit_artifact('research-plan', f'# Attempt {attempt}\n'))
            left = worker_tools.SUBMISSIONS - attempt
            if left > 2:
                self.assertNotIn('more time', said)
            elif left:
                self.assertIn(f'It can be handed back {left} more time(s).', said)
            else:
                self.assertIn('it cannot be handed back again', said)
                self.assertIn('Stop now', said)
        said = self.refused(tools.submit_artifact('research-plan', json.dumps(PLAN)))
        self.assertIn(f'has been handed back {worker_tools.SUBMISSIONS} times', said)
        found = worker_tools.collect(self.job)
        self.assertEqual(found['artifacts'], {})
        self.assertIn('not valid JSON', found['problems']['research-plan'][0])


class ReviewTests(JobCase):
    def test_notes_are_kept_once_the_draft_is_accepted(self):
        tools = self.tools(artifacts=PLANS)
        said = self.refused(tools.submit_review('It is fine.'))
        self.assertIn('Hand the draft back first', said)
        tools.submit_artifact('research-plan', json.dumps(PLAN))
        self.ok(tools.submit_review('  The second question is the weakest.  '))
        self.assertEqual(worker_tools.collect(self.job)['review'],
                         'The second question is the weakest.\n')

    def test_notes_that_cannot_be_written_are_refused_not_lost_silently(self):
        tools = self.tools(artifacts=PLANS)
        tools.submit_artifact('research-plan', json.dumps(PLAN))
        with mock.patch.object(worker_tools, '_write', side_effect=OSError('No space left')):
            self.assertEqual(self.refused(tools.submit_review('Notes.')), 'No space left')
        self.assertIsNone(worker_tools.collect(self.job)['review'])

    def test_a_job_with_no_draft_has_nothing_to_review(self):
        self.assertIn('nothing to write notes on',
                      self.refused(self.tools(finding='instance-min').submit_review('Notes.')))

    def test_empty_and_overlong_notes_are_refused(self):
        tools = self.tools(artifacts=PLANS)
        tools.submit_artifact('research-plan', json.dumps(PLAN))
        self.assertEqual(self.refused(tools.submit_review('  ')), 'Your notes are empty.')
        self.assertIn('Keep them under 4,000',
                      self.refused(tools.submit_review('x' * 4001)))
        self.assertIsNone(worker_tools.collect(self.job)['review'])


class FetchRuleTests(JobCase):
    def research(self, **extra):
        return self.tools(finding='instance-min', fetch=True, ask=False, **extra)

    def test_a_job_that_may_not_fetch_refuses(self):
        self.web.page(DOCS, PAGE)
        said = self.refused(self.tools(finding='instance-min').save_source(DOCS))
        self.assertIn('This job cannot fetch pages', said)
        self.assertEqual(self.web.asked, [])

    def test_only_http_and_https_addresses_are_fetched(self):
        tools = self.research()
        for address in ('ftp://docs.example.com/file', 'file:///etc/hosts', 'docs.example.com',
                        'https:///restarts', 'javascript:alert(1)'):
            with self.subTest(address):
                self.assertEqual(self.refused(tools.save_source(address)),
                                 'Only http and https addresses can be saved.')
        self.assertEqual(self.refused(tools.save_source('http://[::1/admin')),
                         'That is not a web address.')
        self.assertIn('longer than 2,000 characters',
                      self.refused(tools.save_source('https://docs.example.com/' + 'x' * 2000)))
        self.assertEqual(self.web.asked, [])

    def test_an_address_with_a_password_is_refused(self):
        self.web.page('https://docs.example.com/x', PAGE)
        said = self.refused(self.research().save_source('https://me:secret@docs.example.com/x'))
        self.assertIn('carries a name or password', said)
        self.assertEqual(self.web.asked, [])

    def test_private_loopback_and_link_local_addresses_are_refused(self):
        tools = self.research()
        for number, address in enumerate((
                '127.0.0.1', '10.0.0.5', '172.16.4.1', '192.168.1.10', '169.254.169.254',
                '100.64.0.1', '0.0.0.0', '::1', 'fe80::1', 'fc00::1', '::ffff:127.0.0.1',
                '::ffff:10.0.0.5', 'fe80::1%en0', 'not-an-address')):
            with self.subTest(address):
                url = self.web.page(f'http://host{number}.example.com/', PAGE,
                                    addresses=[address])
                self.assertEqual(self.refused(tools.save_source(url)),
                                 'That address is not on the public internet, so it was not '
                                 'fetched.')
        self.assertEqual(self.web.asked, [])
        self.assertEqual(worker_tools.collect(self.job)['sources'], [])

    def test_a_name_with_one_private_address_among_public_ones_is_refused(self):
        url = self.web.page('https://mixed.example.com/', PAGE, addresses=[PUBLIC, '10.0.0.5'])
        self.assertIn('not on the public internet', self.refused(self.research().save_source(url)))
        self.assertEqual(self.web.asked, [])

    def test_a_literal_private_address_is_refused_by_the_real_lookup(self):
        tools = worker_tools.WorkerTools(
            worker_tools.prepare(self.job, finding='instance-min', fetch=True),
            opener=self.web.opener)
        for url in ('http://127.0.0.1:8080/admin', 'http://169.254.169.254/latest/'):
            with self.subTest(url):
                self.assertIn('not on the public internet', self.refused(tools.save_source(url)))
        self.refused(tools.save_source('http://[::1]/'))
        self.assertEqual(self.web.asked, [])

    def test_public_addresses_are_told_from_the_rest(self):
        self.assertTrue(worker_tools.public(PUBLIC))
        self.assertTrue(worker_tools.public('2606:2800:220:1:248:1893:25c8:1946'))
        self.assertFalse(worker_tools.public('192.168.0.1'))
        self.assertFalse(worker_tools.public('::ffff:192.168.0.1'))

    def test_a_name_that_cannot_be_looked_up_is_refused(self):
        said = self.refused(self.research().save_source('https://nowhere.example.com/'))
        self.assertIn('Could not look up nowhere.example.com', said)

    def test_a_redirect_to_a_private_address_is_refused(self):
        self.web.page('http://internal.example.com/admin', 'secret', addresses=['10.0.0.5'])
        url = self.web.page('https://docs.example.com/go', '', status=302,
                            headers={'location': 'http://internal.example.com/admin'})
        said = self.refused(self.research().save_source(url))
        self.assertIn('not on the public internet', said)
        self.assertEqual(self.web.asked, [(url, PUBLIC)])
        self.assertEqual(worker_tools.collect(self.job)['sources'], [])

    def test_a_redirect_to_a_public_page_is_followed_and_the_final_address_kept(self):
        self.web.page('https://docs.example.com/restarts/', PAGE)
        url = self.web.page('https://docs.example.com/old', '', status=301,
                            headers={'location': '/restarts/'})
        tools = self.research()
        self.assertTrue(self.ok(tools.save_source(url)).startswith('Saved as s1'))
        source = worker_tools.collect(self.job)['sources'][0]
        self.assertEqual((source['url'], source['asked']),
                         ('https://docs.example.com/restarts/', url))
        self.assertTrue(self.ok(tools.save_source(url)).startswith('Already saved as s1'))

    def test_endless_redirects_are_given_up_on(self):
        url = self.web.page('https://docs.example.com/loop', '', status=302,
                            headers={'location': '/loop'})
        self.assertIn('redirected too many times', self.refused(self.research().save_source(url)))
        self.assertEqual(len(self.web.asked), worker_tools.MAX_HOPS + 1)

    def test_a_site_that_says_no_is_reported_as_it_answered(self):
        url = self.web.page('https://docs.example.com/private', 'Go away', status=403)
        self.assertEqual(self.refused(self.research().save_source(url)),
                         'The site answered 403 Forbidden. The page was not saved.')

    def test_a_page_over_the_size_limit_is_refused(self):
        url = self.web.page(DOCS, PAGE)
        with mock.patch.object(worker_tools, 'MAX_BYTES', 100):
            said = self.refused(self.research().save_source(url))
        self.assertIn('so it was not saved', said)
        self.assertEqual(worker_tools.collect(self.job)['sources'], [])

    def test_something_that_is_not_a_page_or_a_pdf_is_refused(self):
        url = self.web.page('https://docs.example.com/logo.png', b'\x89PNG\r\n', 'image/png')
        self.assertEqual(self.refused(self.research().save_source(url)),
                         'That address holds image/png, not a page or a PDF. It was not saved.')

    def test_a_page_with_no_readable_text_is_refused_and_nothing_is_kept(self):
        url = self.web.page(DOCS, '<html><body><script>render()</script></body></html>')
        said = self.refused(self.research().save_source(url))
        self.assertIn('has no readable text; it may need a browser', said)
        self.assertEqual([path.name for path in (self.job / 'sources').iterdir()],
                         ['index.json'])

    def test_a_connection_that_fails_tries_the_next_address_then_gives_up(self):
        url = self.web.page(DOCS, PAGE, addresses=[PUBLIC, '93.184.216.35'])
        tried = []

        def opener(asked, address, limit):
            tried.append(address)
            if address == PUBLIC:
                raise OSError('connection refused')
            return self.web.opener(asked, address, limit)

        tools = self.research()
        tools.opener = opener
        self.ok(tools.save_source(url))
        self.assertEqual(tried, [PUBLIC, '93.184.216.35'])
        self.web.pages['https://docs.example.com/down'] = OSError('timed out')
        said = self.refused(tools.save_source('https://docs.example.com/down'))
        self.assertEqual(said, 'Could not fetch the page (timed out). It was not saved.')

    def test_only_so_many_sources_are_saved(self):
        tools = self.research()
        with mock.patch.object(worker_tools, 'MAX_SOURCES', 2):
            for number in range(2):
                self.ok(tools.save_source(self.web.page(f'{DOCS}/{number}', PAGE + str(number))))
            said = self.refused(tools.save_source(self.web.page(f'{DOCS}/2', PAGE)))
        self.assertIn('has saved 2 sources, which is the most it may', said)

    def test_a_compressed_body_is_unpacked_and_a_garbled_one_refused(self):
        tools = self.research()
        url = self.web.page(DOCS, gzip.compress(PAGE.encode()),
                            headers={'content-encoding': 'gzip'})
        self.assertIn('Capacity holds only when', self.ok(tools.save_source(url)))
        bad = self.web.page(f'{DOCS}/bad', b'not gzip', headers={'content-encoding': 'br'})
        self.assertIn('could not be read', self.refused(tools.save_source(bad)))

    def test_requests_look_like_a_browsers(self):
        self.assertTrue(worker_tools.HEADERS['User-Agent'].startswith('Mozilla/5.0 '))
        self.assertIn('text/html', worker_tools.HEADERS['Accept'])
        self.assertIn('Accept-Language', worker_tools.HEADERS)


class SourceTests(JobCase):
    def saved(self, body=PAGE, **page):
        tools = self.tools(finding='instance-min', fetch=True)
        said = self.ok(tools.save_source(self.web.page(DOCS, body, **page)))
        return tools, said, worker_tools.collect(self.job)['sources'][0]

    def test_a_page_is_kept_with_its_text_its_original_and_its_hash(self):
        import hashlib
        tools, said, source = self.saved()
        digest = hashlib.sha256(PAGE.encode()).hexdigest()
        self.assertEqual((source['id'], source['title'], source['url'], source['sha256']),
                         ('s1', 'Rolling restarts', DOCS, digest))
        self.assertEqual(source['file'], f'sources/docs-example-com-{digest[:12]}.txt')
        self.assertEqual(source['original'], f'sources/docs-example-com-{digest[:12]}.html')
        self.assertEqual(source['path'], self.job / source['file'])
        self.assertEqual(source['original_path'].read_bytes(), PAGE.encode())
        text = source['path'].read_text(encoding='utf-8')
        self.assertTrue(text.startswith('Rolling restarts\n\nA rolling restart replaces'))
        self.assertNotIn('hidden', text)
        self.assertNotIn('color', text)
        self.assertEqual(source['chars'], len(text))
        self.assertTrue(said.startswith(f'Saved as s1: "Rolling restarts", {len(text)} '
                                        'characters.\n\nRolling restarts'))
        self.assertEqual(self.web.asked, [(DOCS, PUBLIC)])

    def test_the_same_content_is_named_the_same_whichever_job_saved_it(self):
        _, _, first = self.saved()
        other = self.base / 'another-job'
        worker_tools.prepare(other, finding='health-checks', fetch=True)
        tools = worker_tools.WorkerTools(other, opener=self.web.opener,
                                         resolver=self.web.resolver)
        tools.save_source(DOCS)
        self.assertEqual(worker_tools.collect(other)['sources'][0]['file'], first['file'])

    def test_a_long_page_says_how_to_read_the_rest(self):
        body = '<p>' + 'word ' * 4000 + '</p>'
        _, said, source = self.saved(body)
        self.assertIn(f"[{source['chars'] - worker_tools.WINDOW:,} more characters. Use "
                      'search_source', said)

    def test_a_page_is_read_in_the_encoding_it_declares(self):
        _, said, _ = self.saved('<p>Café capacity</p>'.encode('latin-1'),
                                kind='text/html; charset=ISO-8859-1')
        self.assertIn('Café capacity', said)
        self.job.joinpath('job.json').unlink()
        body = b'<meta charset="windows-1252"><p>Caf\xe9 again</p>'
        self.assertIn('Café again', self.saved(body, kind='text/html')[1])

    def test_characters_that_would_shift_a_quote_are_dropped(self):
        _, _, source = self.saved('﻿<p>Batch\x00 size is two.</p>')
        self.assertEqual(source['path'].read_text(encoding='utf-8'), 'Batch size is two.\n')

    def test_an_endless_title_is_cut_short(self):
        _, _, source = self.saved(f"<title>{'Restarts ' * 100}</title><p>Body text.</p>")
        self.assertEqual(len(source['title']), 301)

    def test_plain_text_is_kept_as_it_is(self):
        _, said, source = self.saved('Line one.\n<not a tag>\n', kind='text/plain')
        self.assertIn('Line one.\n<not a tag>', said)
        self.assertTrue(source['original'].endswith('.raw'))
        self.assertEqual(source['title'], 'docs.example.com')

    def test_a_pdf_is_read_with_the_pdf_reader(self):
        tools = self.tools(finding='instance-min', fetch=True)
        url = self.web.page('https://docs.example.com/files/Restart%20guide.pdf',
                            b'%PDF-1.7 ...', 'application/octet-stream')
        self.assertIn('Text of the PDF.', self.ok(tools.save_source(url)))
        source = worker_tools.collect(self.job)['sources'][0]
        self.assertEqual(source['title'], 'Restart guide.pdf')
        self.assertTrue(source['original'].endswith('.pdf'))
        self.assertEqual(source['original_path'].read_bytes(), b'%PDF-1.7 ...')

    def test_a_pdf_is_refused_when_this_computer_cannot_read_one(self):
        tools = self.tools(finding='instance-min', fetch=True)
        tools.pdf = worker_tools.pdf_text
        url = self.web.page('https://docs.example.com/guide.pdf', b'%PDF-1.7 ...',
                            'application/pdf')
        with mock.patch.object(worker_tools.shutil, 'which', return_value=None):
            said = self.refused(tools.save_source(url))
        self.assertIn('this computer has no PDF reader (pdftotext)', said)
        self.assertEqual([path.name for path in (self.job / 'sources').iterdir()],
                         ['index.json'])

    def test_a_pdf_that_cannot_be_read_is_refused(self):
        done = subprocess.CompletedProcess([], 1, b'', b'Syntax Error')
        with mock.patch.object(worker_tools.shutil, 'which', return_value='/bin/pdftotext'), \
                mock.patch.object(worker_tools.subprocess, 'run', return_value=done):
            with self.assertRaisesRegex(worker_tools.Refusal, 'could not be read'):
                worker_tools.pdf_text(self.job / 'x.pdf')

    def test_a_source_is_read_from_an_offset(self):
        tools, _, source = self.saved()
        text = source['path'].read_text(encoding='utf-8')
        said = self.ok(tools.read_source('s1', '18', 30))
        self.assertEqual(said, f'[s1: characters 18 to 48 of {len(text)}]\n\n{text[18:48]}')
        whole = self.ok(tools.read_source('s1', 0, 10 ** 9))
        self.assertTrue(whole.endswith(text))

    def test_reading_past_the_end_or_an_unknown_source_is_refused(self):
        tools, _, source = self.saved()
        self.assertIn(f"s1 has {source['chars']} characters; there is nothing at 5,000",
                      self.refused(tools.read_source('s1', 5000)))
        self.assertEqual(self.refused(tools.read_source('s9')),
                         'There is no source s9. Saved sources: s1.')
        self.assertIn('offset must be a whole number',
                      self.refused(tools.read_source('s1', 'start')))

    def test_a_source_is_searched_without_regard_to_case(self):
        tools, _, source = self.saved()
        text = source['path'].read_text(encoding='utf-8')
        said = self.ok(tools.search_source('s1', 'CAPACITY  holds'))
        self.assertTrue(said.startswith(f"[offset {text.index('Capacity holds')}] …"))
        self.assertIn('more than one instance', said)
        self.assertEqual(self.ok(tools.search_source('s1', 'rollback')),
                         'No match in s1. Try fewer or different words.')
        self.assertEqual(self.refused(tools.search_source('s1', '  ')), 'Say what to look for.')
        self.assertIn('There is no source s2', self.refused(tools.search_source('s2', 'x')))

    def test_a_source_with_nothing_saved_says_so(self):
        tools = self.tools(finding='instance-min', fetch=True)
        self.assertEqual(self.refused(tools.read_source('s1')),
                         'There is no source s1. Saved sources: none yet.')


class PinnedFetchTests(unittest.TestCase):
    """The real request, over a socket pair in place of the network."""

    def fetch(self, url: str, answer: bytes):
        ours, theirs = socket.socketpair()
        seen = {}

        def serve():
            seen['request'] = theirs.recv(65536).decode('latin-1')
            theirs.sendall(answer)
            theirs.close()

        def connect(address, *args, **kwargs):
            seen['address'] = address
            return ours

        thread = threading.Thread(target=serve)
        thread.start()
        with mock.patch.object(socket, 'create_connection', side_effect=connect), \
                mock.patch.object(worker_tools.urllib.request, 'getproxies', return_value={}):
            found = worker_tools.fetch_once(url, PUBLIC, 1000)
        thread.join()
        return found, seen

    def test_it_connects_to_the_checked_address_and_asks_as_a_browser_would(self):
        answer = b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 5\r\n\r\nhello'
        (status, headers, body), seen = self.fetch('http://docs.example.com/restarts', answer)
        self.assertEqual((status, headers['content-type'], body), (200, 'text/html', b'hello'))
        self.assertEqual(seen['address'], (PUBLIC, 80))
        self.assertIn('GET /restarts HTTP/1.1', seen['request'])
        self.assertIn('Host: docs.example.com', seen['request'])
        self.assertIn('User-Agent: Mozilla/5.0', seen['request'])

    def test_an_https_request_goes_to_the_checked_address_under_the_hosts_own_name(self):
        ours, theirs = socket.socketpair()
        plain, context, seen = object(), mock.Mock(), {}
        context.wrap_socket.return_value = ours

        def serve():
            seen['request'] = theirs.recv(65536).decode('latin-1')
            theirs.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok')
            theirs.close()

        def connect(address, *args, **kwargs):
            seen['address'] = address
            return plain

        thread = threading.Thread(target=serve)
        thread.start()
        with mock.patch.object(socket, 'create_connection', side_effect=connect), \
                mock.patch.object(worker_tools.ssl, 'create_default_context',
                                  return_value=context), \
                mock.patch.object(worker_tools.urllib.request, 'getproxies', return_value={}):
            status, _, body = worker_tools.fetch_once('https://docs.example.com:8443/restarts',
                                                      PUBLIC, 1000)
        thread.join()
        self.assertEqual((status, body, seen['address']), (200, b'ok', (PUBLIC, 8443)))
        context.wrap_socket.assert_called_once_with(plain, server_hostname='docs.example.com')
        self.assertIn('Host: docs.example.com:8443', seen['request'])

    def test_a_redirect_comes_back_as_an_answer_and_is_not_followed(self):
        answer = (b'HTTP/1.1 302 Found\r\nLocation: http://169.254.169.254/\r\n'
                  b'Content-Length: 0\r\n\r\n')
        (status, headers, body), seen = self.fetch('http://docs.example.com/go', answer)
        self.assertEqual((status, headers['location'], body),
                         (302, 'http://169.254.169.254/', b''))
        self.assertEqual(seen['address'], (PUBLIC, 80))

    def test_an_error_answer_is_returned_not_raised(self):
        answer = b'HTTP/1.1 404 Not Found\r\nContent-Length: 4\r\n\r\ngone'
        (status, _, body), _ = self.fetch('http://docs.example.com/missing', answer)
        self.assertEqual((status, body), (404, b'gone'))

    def test_no_more_than_the_limit_and_one_byte_is_read(self):
        answer = b'HTTP/1.1 200 OK\r\nContent-Length: 5000\r\n\r\n' + b'x' * 5000
        (_, _, body), _ = self.fetch('http://docs.example.com/big', answer)
        self.assertEqual(len(body), 1001)


class FindingTests(JobCase):
    def research(self, **extra):
        tools = self.tools(finding='instance-min', fetch=True, ask=False, **extra)
        self.ok(tools.save_source(self.web.page(DOCS, PAGE)))
        self.text = worker_tools.collect(self.job)['sources'][-1]['path'].read_text('utf-8')
        return tools

    def submit(self, tools, quote=QUOTE, **changes):
        given = {'item': 'instance-min', 'status': 'supported',
                 'summary': 'An app keeps capacity when it runs more than one instance.',
                 'limits': 'One page from the platform\'s own documentation.',
                 'evidence': [{'source_id': 's1', 'quote': quote}], **changes}
        return tools.submit_finding(**given)

    def test_an_accepted_finding_has_each_quote_placed(self):
        tools = self.research()
        self.assertEqual(self.ok(self.submit(tools)),
                         'Accepted: the finding for instance-min, with 1 quoted passage(s).')
        finding = worker_tools.collect(self.job)['finding']
        self.assertEqual((finding['item'], finding['status']), ('instance-min', 'supported'))
        passage, source = finding['evidence'][0], worker_tools.collect(self.job)['sources'][0]
        start = self.text.index(QUOTE)
        self.assertEqual(passage, {
            'file': source['file'], 'title': 'Rolling restarts', 'origin': DOCS, 'quote': QUOTE,
            'start': start, 'locator': f'characters {start} to {start + len(QUOTE)}'})
        self.assertEqual(self.text[start:start + len(QUOTE)], QUOTE)

    def test_a_quote_that_is_not_there_is_refused(self):
        tools = self.research()
        said = self.refused(self.submit(tools, 'Capacity always holds during a restart.'))
        self.assertIn('Passage 1: the quote is not in s1 as written.', said)
        self.assertIsNone(worker_tools.collect(self.job)['finding'])
        self.assertIn('Passage 1', worker_tools.collect(self.job)['problems']['finding'][0])

    def test_a_quote_with_words_left_out_is_refused(self):
        tools = self.research()
        said = self.refused(self.submit(tools, 'A rolling restart replaces instances ... so '
                                        'the app keeps serving traffic'))
        self.assertIn('no "..." in it', said)

    def test_a_quote_across_a_line_break_is_found_and_kept_in_the_sources_wording(self):
        tools = self.research()
        typed = 'so the app keeps   serving traffic while it restarts.'
        self.assertNotIn(typed, self.text)
        self.ok(self.submit(tools, typed))
        passage = worker_tools.collect(self.job)['finding']['evidence'][0]
        self.assertEqual(passage['quote'], 'so the app keeps serving\ntraffic while it restarts.')
        self.assertEqual(self.text[passage['start']:passage['start'] + len(passage['quote'])],
                         passage['quote'])

    def test_a_quote_with_plain_marks_matches_the_sources_curly_ones(self):
        tools = self.research()
        self.ok(self.submit(tools, "The platform's health check decides when the next batch "
                                   'starts.'))
        passage = worker_tools.collect(self.job)['finding']['evidence'][0]
        self.assertIn('platform’s health\ncheck', passage['quote'])

    def test_where_a_quote_sits_is_counted_in_characters_not_bytes(self):
        text = 'Café \U0001f600 capacity holds with two instances.\n'
        self.assertEqual(worker_tools.place(text, 'capacity holds with two instances.'),
                         (7, 'capacity holds with two instances.'))
        self.assertEqual(worker_tools.place(text, 'two — instances'), None)
        self.assertEqual(worker_tools.place('up - or down', 'up – or down'),
                         (0, 'up - or down'))
        self.assertIsNone(worker_tools.place(text, ''))
        self.assertIsNone(worker_tools.place(text, '   '))

    def test_a_quote_must_be_a_passage_not_a_fragment_or_a_page(self):
        tools = self.research()
        self.assertIn('Passage 1: the quote is 14 characters. Quote the whole sentence',
                      self.refused(self.submit(tools, 'Capacity holds')))
        with mock.patch.object(worker_tools, 'QUOTE', (20, 40)):
            self.assertIn('between 20 and 40 characters', self.refused(self.submit(tools)))

    def test_a_passage_from_a_source_that_was_not_saved_is_refused(self):
        tools = self.research()
        said = self.refused(self.submit(tools, evidence=[{'source_id': 's4', 'quote': QUOTE}]))
        self.assertIn('Passage 1: There is no source s4. Saved sources: s1.', said)
        said = self.refused(self.submit(tools, evidence=['s1']))
        self.assertIn('Passage 1 needs a source_id and a quote.', said)

    def test_a_verdict_that_claims_something_needs_a_quote(self):
        tools = self.research()
        for status in ('supported', 'contradicted'):
            said = self.refused(self.submit(tools, status=status, evidence=[]))
            self.assertIn(f'A {status} finding needs at least one quoted passage.', said)
        self.ok(self.submit(tools, status='insufficient', evidence=None, limits=''))
        finding = worker_tools.collect(self.job)['finding']
        self.assertEqual((finding['evidence'], finding['limits']), ([], 'none'))

    def test_the_verdict_summary_limits_and_number_of_passages_are_checked(self):
        tools = self.research()
        self.assertIn('status must be one of: supported, contradicted, insufficient, '
                      'unavailable.', self.refused(self.submit(tools, status='proven')))
        self.assertIn('The summary is empty.', self.refused(self.submit(tools, summary=' ')))
        self.assertIn('The summary is 1,501 characters',
                      self.refused(self.submit(tools, summary='x' * 1501)))
        self.assertIn('The limits are too long',
                      self.refused(self.submit(tools, limits='x' * 4001)))
        many = [{'source_id': 's1', 'quote': QUOTE}] * 21
        with mock.patch.object(worker_tools, 'SUBMISSIONS', 99):
            self.assertIn('Give at most 20 passages',
                          self.refused(self.submit(tools, evidence=many)))

    def test_evidence_may_arrive_as_json_text_but_must_be_a_list(self):
        tools = self.research()
        self.assertIn('evidence must be a list of passages',
                      self.refused(self.submit(tools, evidence='s1 says so')))
        self.assertIn('evidence must be a list of passages',
                      self.refused(self.submit(tools, evidence={'source_id': 's1'})))
        self.ok(self.submit(tools, evidence=json.dumps([{'source_id': 's1', 'quote': QUOTE}])))

    def test_a_job_answers_its_own_question_and_no_other(self):
        tools = self.research()
        self.assertEqual(self.refused(self.submit(tools, item='health-checks')),
                         'This job answers instance-min, not "health-checks".')
        writer = worker_tools.WorkerTools(worker_tools.prepare(self.base / 'w',
                                                               artifacts=PLANS))
        self.assertEqual(self.refused(self.submit(writer)),
                         'This job does not answer a research question.')

    def test_a_finding_can_be_handed_back_only_so_many_times(self):
        tools = self.research()
        for _ in range(worker_tools.SUBMISSIONS):
            self.refused(self.submit(tools, 'This sentence is not in the page at all.'))
        self.assertIn('This finding has been handed back', self.refused(self.submit(tools)))

    def test_a_supplied_document_is_quoted_under_its_own_id_and_path(self):
        tools = self.tools(finding='instance-min', ask=False, sources=[{
            'title': 'Operations handbook', 'origin': 'Supplied by the team',
            'text': 'Restart   one batch at a time.\nKeep two instances running throughout.',
            'file': 'sources/handbook.txt', 'supplied': 'handbook'}])
        self.assertIn('This job cannot fetch pages', self.refused(tools.save_source(DOCS)))
        self.ok(tools.submit_finding('instance-min', 'supported', 'Two instances are kept.',
                                     evidence=[{'source_id': 's1', 'quote': 'Keep two '
                                                'instances running throughout.'}]))
        passage = worker_tools.collect(self.job)['finding']['evidence'][0]
        self.assertEqual((passage['file'], passage['source_id'], passage['origin'],
                          passage['start']),
                         ('sources/handbook.txt', 'handbook', 'Supplied by the team', 29))
        source = worker_tools.collect(self.job)['sources'][0]
        self.assertTrue(source['offered'])
        self.assertEqual(source['path'].read_text(),
                         'Restart one batch at a time.\nKeep two instances running throughout.\n')


class QuestionTests(JobCase):
    def test_a_question_ends_the_job(self):
        tools = self.tools(inputs={'intake': 'Text.'}, artifacts=PLANS)
        said = self.ok(tools.ask_person('  Which of the two products is this about?  '))
        self.assertIn('this job is over. Stop now', said)
        self.assertEqual(worker_tools.collect(self.job)['question'],
                         'Which of the two products is this about?')
        for outcome in (tools.read_input('intake'), tools.list_inputs(),
                        tools.submit_artifact('research-plan', json.dumps(PLAN)),
                        tools.ask_person('And another thing?'),
                        tools.call('submit_review', {'text': 'Notes.'})):
            self.assertEqual(self.refused(outcome), worker_tools.ENDED)
        self.assertEqual(worker_tools.collect(self.job)['artifacts'], {})
        again = worker_tools.WorkerTools(self.job)
        self.assertEqual(self.refused(again.list_inputs()), worker_tools.ENDED)

    def test_a_job_that_nobody_can_answer_refuses_questions(self):
        said = self.refused(self.tools(finding='instance-min', ask=False).ask_person('Why?'))
        self.assertIn('Nobody can answer questions in this job', said)
        self.assertIsNone(worker_tools.collect(self.job)['question'])

    def test_an_empty_or_rambling_question_is_refused(self):
        tools = self.tools()
        self.assertEqual(self.refused(tools.ask_person(' ')), 'The question is empty.')
        self.assertIn('Ask one thing, in under 1,000', self.refused(tools.ask_person('x' * 1001)))
        self.assertEqual(self.ok(tools.list_inputs())[:8], 'This job')


class ServerTests(JobCase):
    def names(self, tools) -> list[str]:
        return [entry['name'] for entry in tools.offered()]

    def test_a_job_is_offered_only_the_tools_it_has_a_use_for(self):
        self.assertEqual(self.names(self.tools(artifacts=PLANS)),
                         ['list_inputs', 'read_input', 'submit_artifact', 'submit_review',
                          'ask_person'])
        (self.job / 'job.json').unlink()
        self.assertEqual(self.names(self.tools(finding='instance-min', fetch=True, ask=False)),
                         ['list_inputs', 'read_input', 'save_source', 'read_source',
                          'search_source', 'submit_finding'])
        (self.job / 'job.json').unlink()
        supplied = self.tools(finding='instance-min', ask=False, sources=[
            {'title': 'Handbook', 'origin': 'Supplied', 'text': 'Words.', 'file': 'sources/h'}])
        self.assertEqual(self.names(supplied), ['list_inputs', 'read_input', 'read_source',
                                                'search_source', 'submit_finding'])

    def test_every_tool_is_described_and_is_a_method(self):
        tools = self.tools()
        for entry in worker_tools.TOOLS:
            self.assertTrue(getattr(getattr(tools, entry['name']), 'is_tool', False))
            self.assertTrue(entry['description'])
            self.assertLessEqual(set(entry['inputSchema']['required']),
                                 set(entry['inputSchema']['properties']))
        self.assertEqual(len(worker_tools.NAMES), 17)

    def answer(self, tools, method, params=None, ident=1):
        message = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if ident is not None:
            message['id'] = ident
        return worker_tools.answer(tools, message)

    def test_the_server_speaks_the_protocol_an_agent_expects(self):
        tools = self.tools(inputs={'intake': 'Text.'}, artifacts=PLANS)
        hello = self.answer(tools, 'initialize', {'protocolVersion': '2025-06-18'})
        self.assertEqual(hello['result']['protocolVersion'], '2025-06-18')
        self.assertEqual(hello['result']['serverInfo']['name'], 'runner')
        self.assertEqual(hello['result']['capabilities'], {'tools': {}})
        self.assertIsNone(self.answer(tools, 'notifications/initialized', ident=None))
        listed = self.answer(tools, 'tools/list', ident='a')
        self.assertEqual(listed['id'], 'a')
        self.assertEqual([entry['name'] for entry in listed['result']['tools']],
                         self.names(tools))
        self.assertEqual(self.answer(tools, 'ping')['result'], {})
        self.assertEqual(self.answer(tools, 'resources/list')['result'], {'resources': []})
        self.assertEqual(self.answer(tools, 'sampling/createMessage')['error']['code'], -32601)
        self.assertIsNone(worker_tools.answer(tools, ['not', 'a', 'message']))

    def test_a_call_answers_with_text_and_says_when_it_was_refused(self):
        tools = self.tools(inputs={'intake': 'Text.'})
        read = self.answer(tools, 'tools/call', {'name': 'read_input',
                                                 'arguments': {'name': 'intake'}})
        self.assertEqual(read['result'], {'content': [{'type': 'text', 'text': 'Text.'}],
                                          'isError': False})
        missing = self.answer(tools, 'tools/call', {'name': 'read_input',
                                                    'arguments': {'name': 'notes'}})
        self.assertTrue(missing['result']['isError'])
        bare = self.answer(tools, 'tools/call', {'name': 'list_inputs'})
        self.assertFalse(bare['result']['isError'])

    def test_the_loop_skips_what_it_cannot_read_and_answers_the_rest(self):
        tools = self.tools()
        lines = ['not json\n', '\n', json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}),
                 json.dumps({'jsonrpc': '2.0', 'method': 'notifications/cancelled'}),
                 json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})]
        out = io.StringIO()
        worker_tools.serve(tools, lines, out)
        replies = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([reply['id'] for reply in replies], [1, 2])

    def test_the_command_really_starts_a_server_that_answers(self):
        worker_tools.prepare(self.job, inputs={'intake': 'Café owners.\n'})
        asked = '\n'.join(json.dumps(message) for message in (
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
             'params': {'name': 'read_input', 'arguments': {'name': 'intake'}}})) + '\n'
        done = subprocess.run(worker_tools.command(self.job), input=asked.encode('utf-8'),
                              capture_output=True, cwd=self.base, timeout=60,
                              env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
        self.assertEqual((done.returncode, done.stderr), (0, b''))
        replies = [json.loads(line) for line in done.stdout.decode('utf-8').splitlines()]
        self.assertEqual([reply['id'] for reply in replies], [1, 2])
        self.assertEqual(replies[1]['result']['content'][0]['text'], 'Café owners.\n')

    def test_the_server_will_not_start_for_a_folder_that_is_not_a_job(self):
        done = subprocess.run(worker_tools.command(self.job), input=b'', capture_output=True,
                              timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertIn(b'not a job folder', done.stderr)



# --- kinds a later part of the runner adds ------------------------------------------------

def check_note(text: str, spec: dict):
    """A kind of draft for these tests: a note that must name the word the spec gives."""
    problems = [] if spec.get('word', 'deck') in text else ['Say "deck" somewhere.']
    ran = [worker_tools.result('note.word', problems)]
    return problems, ran, [], worker_tools.as_kept(text)


def no_word(outline: dict, word: str = 'faster') -> list[str]:
    """An outline rule for these tests: no slide's title holds `word`."""
    return [f"{slide['id']}: the title says {word}." for slide in build.slides_of(outline)
            if word in str(slide.get('title'))]


class RegisterTests(JobCase):
    def setUp(self):
        super().setUp()
        for kept in (worker_tools.VALIDATORS, worker_tools.EXTENSIONS, worker_tools.REGISTERED):
            patcher = mock.patch.dict(kept)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_only_the_runners_own_kinds_are_there_until_one_is_registered(self):
        self.assertEqual(list(worker_tools.VALIDATORS), ['research-plan', 'outline', 'section'])
        worker_tools.register('note', check_note)
        self.assertIn('note', worker_tools.VALIDATORS)
        for wrong in (('', check_note), ('outline', check_note), ('look', 'not callable')):
            with self.assertRaisesRegex(WorkspaceError, 'cannot be registered'):
                worker_tools.register(*wrong)

    def test_a_registered_kind_is_handed_back_with_submit_artifact_and_checked_by_its_check(self):
        worker_tools.register('note', check_note, '.md')
        tools = self.tools(artifacts={'note': {'kind': 'note', 'word': 'deck'}})
        self.assertEqual(self.names(tools), ['list_inputs', 'read_input', 'submit_artifact',
                                             'submit_review', 'ask_person'])
        self.assertIn('Say "deck" somewhere.',
                      self.refused(tools.submit_artifact('note', 'Nothing here.')))
        self.assertEqual(self.ok(tools.submit_artifact('note', 'A deck note.')),
                         'Accepted: note.')
        kept = worker_tools.collect(self.job)['artifacts']['note']
        self.assertEqual((kept['kind'], kept['text'], kept['path'].name,
                          kept['checks'][0]['check']), ('note', 'A deck note.\n', 'note.md',
                                                        'note.word'))
        job = json.loads((self.job / 'job.json').read_text())
        self.assertEqual(job['checks'], {'note': __name__})

    def names(self, tools) -> list[str]:
        return [entry['name'] for entry in tools.offered()]

    def test_a_process_that_has_not_registered_the_kind_imports_the_module_that_does(self):
        """As the server does: it runs apart, and finds the check by the module job.json
        names."""
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'registers_a_note.py').write_text(
                'from runner import worker_tools\n'
                'def check(text, spec):\n'
                '    found = [] if "deck" in text else ["Say deck."]\n'
                '    return found, [worker_tools.result("note", found)], [], text\n'
                'worker_tools.register("note", check)\n')
            sys.path.insert(0, folder)
            self.addCleanup(sys.path.remove, folder)
            self.addCleanup(sys.modules.pop, 'registers_a_note', None)
            __import__('registers_a_note')
            worker_tools.prepare(self.job, artifacts={'note': {'kind': 'note'}})
            del worker_tools.VALIDATORS['note']
            sys.modules.pop('registers_a_note')
            tools = worker_tools.WorkerTools(self.job)
            self.assertEqual(self.ok(tools.submit_artifact('note', 'A deck.')), 'Accepted: note.')
            self.assertIn('note', worker_tools.VALIDATORS)


# --- a deck's tools ------------------------------------------------------------------------

class ToolCase(JobCase):
    """One job of a deck, with the two stand-ins behind its tools."""

    def setUp(self):
        super().setUp()
        self.slides, self.brand = Slides(), Brand()
        self.contract = self.brand.export(self.base / 'brand', 'example-co', 'light')['contract']
        whole = {**OUTLINE, 'direction': dict(build.DIRECTION)}
        self.spec = {'kind': 'section', 'brand': self.contract,
                     **build.fixed(whole, ['what-it-does', 'when-capacity-holds'], 1),
                     'previews': 4, 'renderer': 'drive', 'lock': str(self.base / 'render.lock'),
                     'kept': str(self.base / 'preview-file.json'),
                     'named': {'name': 'Preview: Rolling restarts'}}

    def tools(self, **prepared) -> worker_tools.WorkerTools:
        if prepared or not (self.job / 'job.json').exists():
            worker_tools.prepare(self.job, **prepared)
        return worker_tools.WorkerTools(self.job, slides=self.slides, brand=self.brand)

    def composer(self) -> worker_tools.WorkerTools:
        return self.tools(inputs={'brief': 'Your slides.'}, artifacts={'section': self.spec},
                          ask=False)

    def offered(self, tools) -> list[str]:
        return [entry['name'] for entry in tools.offered()]


class OutlineToolTests(ToolCase):
    def writer(self, rules=()) -> worker_tools.WorkerTools:
        return self.tools(artifacts={'outline': {'kind': 'outline', 'brand': self.contract,
                                                 'rules': list(rules)}})

    def test_an_outline_job_has_its_own_tools_and_no_others(self):
        self.assertEqual(self.offered(self.writer()), [
            'list_inputs', 'read_input', 'submit_review', 'check_outline', 'submit_outline',
            'ask_person'])
        with self.assertRaisesRegex(WorkspaceError, 'needs the brand it is checked against'):
            worker_tools.prepare(self.base / 'other', artifacts={'outline': {'kind': 'outline'}})

    def test_an_outline_is_checked_by_the_tool_and_by_the_rules_it_is_given(self):
        tools = self.writer([no_word, functools.partial(no_word, word='never')])
        self.assertEqual(self.ok(tools.check_outline(json.dumps(OUTLINE))),
                         'Nothing to put right. Hand it in with submit_outline.')
        slides = [dict(slide) for slide in OUTLINE['slides']]
        slides[2].pop('notes')
        slides[3]['title'] = 'Rolling is never faster'
        bad = {**OUTLINE, 'slides': slides}
        said = self.ok(tools.check_outline(bad))
        self.assertIn('- when-capacity-holds: It has no notes.', said)
        self.assertIn('- the-objection: the title says faster.', said)
        self.assertIn('- the-objection: the title says never.', said)
        self.assertEqual(tools._state()['submissions'], {}, 'a check is never counted')
        self.assertIn('Not accepted', self.refused(tools.submit_outline(json.dumps(bad))))
        self.assertEqual(self.ok(tools.submit_outline(json.dumps(OUTLINE))),
                         'Accepted: outline.')
        handed = worker_tools.collect(self.job)['artifacts']['outline']
        self.assertEqual((handed['kind'], json.loads(handed['text']), handed['path'].suffix),
                         ('outline', OUTLINE, '.json'))
        self.assertEqual([(outcome['check'], outcome['status']) for outcome in handed['checks']],
                         [('outline.tool', 'passed'), ('outline.rules', 'passed')])

    def test_rules_are_kept_by_name_and_found_again(self):
        self.writer([no_word, functools.partial(no_word, word='always')])
        kept = json.loads((self.job / 'job.json').read_text())['artifacts']['outline']['rules']
        self.assertEqual(kept, [{'call': f'{__name__}:no_word', 'args': [], 'kwargs': {}},
                                {'call': f'{__name__}:no_word', 'args': [],
                                 'kwargs': {'word': 'always'}}])
        found = worker_tools.rules_of({'rules': kept})
        self.assertEqual(found[1]({'slides': [{'id': 'a', 'title': 'always'}]}),
                         ['a: the title says always.'])
        for wrong in (lambda outline: [], functools.partial(no_word, word=object())):
            with self.assertRaises(WorkspaceError):
                worker_tools.prepare(self.base / 'other', artifacts={'outline': {
                    'kind': 'outline', 'brand': self.contract, 'rules': [wrong]}})

    def test_an_outline_that_is_not_an_object_breaks_every_rule(self):
        said = self.ok(self.writer([no_word]).check_outline('["a list"]'))
        self.assertIn('- The outline is one JSON object with its slides under "slides".', said)
        self.assertIn('- The outline must be a JSON object.', said)

    def test_what_the_tool_refuses_is_given_to_the_worker_without_a_folders_name(self):
        tools = self.writer()
        self.slides.refuse['outline_check'] = [
            f"{self.job / 'drafts' / 'outline-1.json'}: a title is too long.",
            f'{Path.home()}/tool: 2 problems to fix.']
        said = self.ok(tools.check_outline(json.dumps(OUTLINE)))
        self.assertIn('- outline-1.json: a title is too long.', said)
        self.assertIn('- ~/tool: 2 problems to fix.', said)
        self.assertNotIn(str(self.base), said)
        self.assertIn('is not valid JSON', self.refused(tools.check_outline('{not json')))

    def test_without_the_slides_tool_the_job_says_so_and_keeps_nothing(self):
        tools = self.writer()
        tools._slides = None
        missing = 'The slides tool is not on this computer.'
        with mock.patch.object(slides_tool, 'Slides', side_effect=WorkspaceError(missing)):
            self.assertEqual(self.refused(tools.submit_outline(json.dumps(OUTLINE))), missing)
        self.assertEqual(worker_tools.collect(self.job)['artifacts'], {})


class SectionToolTests(ToolCase):
    def test_a_composer_has_its_own_tools_and_no_others(self):
        self.assertEqual(self.offered(self.composer()), [
            'list_inputs', 'read_input', 'check_section', 'preview_section', 'search_icons',
            'submit_section'])

    def test_a_check_compiles_and_holds_the_section_to_what_was_fixed(self):
        tools, good = self.composer(), drawn(self.spec)
        self.assertEqual(self.ok(tools.check_section(json.dumps(good))), 'Nothing to put '
                         'right. Preview it with preview_section before you hand it in.')
        long = drawn(self.spec)
        long['slides'][0]['canvas']['children'].append(
            {'type': 'text', 'id': 's1_more', 'text': 'TOO LONG TO FIT'})
        long['slides'][1]['title'] = 'Another title'
        said = self.ok(tools.check_section(long))
        self.assertIn('- when-capacity-holds: the title is fixed', said)
        self.assertIn('- A text does not fit: it needs 7 lines and has 4.', said)
        self.assertEqual(self.slides.most, 0, 'a check renders nothing')

    def test_a_section_keeps_what_was_fixed_and_every_approved_word(self):
        spec, good = self.spec, drawn(self.spec)
        self.assertEqual(build.kept(good, spec), [])
        for change, expect in (
                (lambda made: made['slides'][0].update(title='Batches'), 'the title is fixed'),
                (lambda made: made['slides'][0].update(sources=[]), '`sources` is fixed'),
                (lambda made: made['slides'][0].update(notes='Shorter.'),
                 '`notes` stays exactly as it was approved.'),
                (lambda made: made['slides'][1].pop('caveat'),
                 '`caveat` stays exactly as it was approved: "A single-instance'),
                (lambda made: made['slides'][0].update(caveat='New.'),
                 '`caveat` stays exactly as it was approved: the slide has none.'),
                (lambda made: made['slides'][0].update(layout='Title slide'),
                 'names no template layout'),
                (lambda made: made.update(direction={'focal': 'accent'}),
                 '`direction` is copied unchanged'),
                (lambda made: made['slides'][0]['canvas']['children'][0].update(id='mine'),
                 'every node and edge ID starts with s1_. These do not: mine.'),
                (lambda made: made['slides'].reverse(),
                 'The slides are exactly these, in this order')):
            made = json.loads(json.dumps(good))
            change(made)
            self.assertIn(expect, ' '.join(build.kept(made, spec)))
        reworded = drawn(spec, lambda text: text.replace('one batch', 'a batch'))
        self.assertEqual(build.kept(reworded, spec), [
            'what-it-does: these approved words are missing or changed: "Instances are '
            'replaced one batch at a time."'])

    def test_a_preview_returns_a_picture_of_every_slide_with_what_the_renderer_found(self):
        tools, good = self.composer(), drawn(self.spec)
        self.slides.findings['when-capacity-holds'] = [
            {'severity': 'warn', 'code': 'density', 'detail': '95 words to read.'}]
        shown = tools.preview_section(json.dumps(good))
        self.assertIsInstance(shown, worker_tools.Shown)
        self.assertEqual(shown[1].splitlines()[:3], [
            'Preview 1 of 4.', '- Slide 1, `what-it-does`. The renderer found: nothing',
            '- Slide 2, `when-capacity-holds`. The renderer found: warn density: 95 words '
            'to read.'])
        self.assertEqual([path.read_bytes() for path in shown.pictures], [png(1), png(2)])
        self.assertEqual(sorted(path.name for path in (self.job / 'shown').iterdir()),
                         ['1.png', '2.png'])
        self.assertFalse(any((self.job / 'builds').iterdir())
                         or any((self.job / 'previews').iterdir()),
                         'a build and a render hold megabytes, and are not kept')
        self.assertEqual(json.loads((self.base / 'preview-file.json').read_text()), {
            'id': 'file-1', 'name': 'Preview: Rolling restarts',
            'url': 'https://docs.example.com/presentation/d/file-1/edit'})
        self.ok(tools.preview_section(json.dumps(good)))
        self.assertEqual(self.slides.files, ['file-1'], 'one preview file, written again')
        self.assertEqual(self.slides.calls[-1][-1], 'file-1')

    def test_a_composer_has_four_previews(self):
        tools, good = self.composer(), json.dumps(drawn(self.spec))
        for _ in range(4):
            self.ok(tools.preview_section(good))
        self.assertEqual(self.refused(tools.preview_section(good)), 'You have used all 4 '
                         'previews. Hand in the version you last previewed, with '
                         'submit_section.')
        self.ok(tools.submit_section(good))

    def test_a_draft_that_cannot_be_drawn_or_rendered_uses_up_no_preview(self):
        tools, good = self.composer(), drawn(self.spec)
        bad = drawn(self.spec, lambda text: text.replace('Traffic', 'Load'))
        said = self.refused(tools.preview_section(json.dumps(bad)))
        self.assertIn('Nothing was rendered, and this did not use up a preview.', said)
        self.slides.refuse['preview'] = ['The render has 8 pages for 2 slides.']
        said = self.refused(tools.preview_section(json.dumps(good)))
        self.assertEqual(said, 'The slides compile but could not be rendered, and this did '
                         'not use up a preview:\n- The render has 8 pages for 2 slides.')
        self.assertEqual(tools._state().get('previews', 0), 0)
        self.assertFalse((self.job / 'shown').exists() and any((self.job / 'shown').iterdir()))
        self.assertFalse((self.base / 'render.lock').exists(), 'the turn is given back')

    def test_what_is_handed_in_must_be_what_was_last_previewed(self):
        tools, good = self.composer(), drawn(self.spec)
        self.assertEqual(self.refused(tools.submit_section(json.dumps(good))), 'Preview the '
                         'section first: what you hand in is what you last looked at.')
        self.ok(tools.preview_section(json.dumps(good)))
        other = drawn(self.spec)
        other['slides'][0]['brief']['rhythm'] = 'dense'
        said = self.refused(tools.submit_section(json.dumps(other)))
        self.assertEqual(said, 'This is not the version you last previewed, and it was not '
                         'counted as a hand-in. Hand in exactly that version, or preview '
                         'this one first: you have 3 previews left.')
        self.assertEqual(tools._state()['submissions'], {})
        self.assertIn('Hand a section in with submit_section',
                      self.refused(tools.submit_artifact('section', json.dumps(good))))
        spaced = json.dumps(good, indent=4)
        self.assertEqual(self.ok(tools.submit_section(spaced, 'I evened the rows.',
                                                      'Slide 2 is crowded.')),
                         'Accepted: section.')
        handed = worker_tools.collect(self.job)
        self.assertEqual(json.loads(handed['artifacts']['section']['text']), good)
        self.assertEqual(handed['review'], 'What I changed after looking: I evened the rows.\n'
                         'What still bothers me: Slide 2 is crowded.\n')
        self.assertEqual((handed['shown']['previews'],
                          [slide['path'].read_bytes() for slide in handed['shown']['slides']]),
                         (1, [png(1), png(2)]))

    def test_a_hand_in_that_changed_an_approved_word_is_never_kept(self):
        tools = self.composer()
        changed = drawn(self.spec)
        changed['slides'][1]['caveat'] = 'A single-instance app may drop requests.'
        self.assertIn('`caveat` stays exactly as it was approved',
                      self.refused(tools.preview_section(json.dumps(changed))))
        tools._slides = mock.Mock(wraps=self.slides)
        home_state = {**tools._state(), 'previewed': tools._digest(changed), 'previews': 1}
        (self.job / 'state.json').write_text(json.dumps(home_state))
        said = self.refused(tools.submit_section(json.dumps(changed)))
        self.assertIn('Not accepted', said)
        self.assertIn('`caveat` stays exactly as it was approved', said)
        self.assertEqual(worker_tools.collect(self.job)['artifacts'], {})

    def test_icons_are_searched_in_the_brands_own_library(self):
        tools = self.composer()
        self.assertEqual(self.ok(tools.search_icons('server')), 'Icons for "server". Use an '
                         'ID as the icon of an icon node:\n- icon-server: Server '
                         '(Hardware)\n- icon-server-rack: Server rack (Hardware)',
                         'one that is a picture cannot be placed, and is not offered')
        self.assertIn('No icon matches "photo"', self.ok(tools.search_icons('photo')))
        self.assertIn('No icon matches "database failover"',
                      self.ok(tools.search_icons('database  failover')))
        self.assertIn('one or two plain words', self.refused(tools.search_icons('')))
        self.brand.refuse['icons'] = ['The icon library could not be read.']
        self.assertIn('The icon library could not be read',
                      self.refused(tools.search_icons('clock')))

    def test_a_jobs_tools_use_the_slides_tool_and_the_brand_skill_the_job_names(self):
        named = {'slides': '/opt/slides-tool/versions/0.13.1', 'brand': '/opt/brand-kit'}
        with mock.patch.object(slides_tool, 'Slides', return_value=self.slides) as tool, \
                mock.patch.object(brand_skill, 'Brand', return_value=self.brand) as skill:
            worker_tools.prepare(self.job, artifacts={'section': self.spec}, runtimes=named)
            tools = worker_tools.WorkerTools(self.job)
            self.ok(tools.check_section(json.dumps(drawn(self.spec))))
            self.ok(tools.search_icons('clock'))
            self.assertEqual((tool.call_args_list, skill.call_args_list),
                             ([mock.call(runtime=named['slides'])],
                              [mock.call(runtime=named['brand'])]))
            other = self.base / 'other'
            worker_tools.prepare(other, artifacts={'section': self.spec})
            tools = worker_tools.WorkerTools(other)
            self.ok(tools.check_section(json.dumps(drawn(self.spec))))
            self.ok(tools.search_icons('clock'))
            self.assertEqual((tool.call_args, skill.call_args), (mock.call(), mock.call()))

    def test_previews_wait_for_their_turn_at_the_renderer(self):
        self.slides.took, tools, good = 0.05, self.composer(), json.dumps(drawn(self.spec))
        folders = []
        for number in (2, 3):
            folder = self.base / f'job-{number}'
            worker_tools.prepare(folder, artifacts={'section': self.spec})
            folders.append(worker_tools.WorkerTools(folder, slides=self.slides))
        threads = [threading.Thread(target=each.preview_section, args=(good,))
                   for each in (tools, *folders)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual((self.slides.most, len(self.slides.files)), (1, 1))

    def test_a_preview_file_made_by_a_render_that_failed_is_still_remembered(self):
        refusal = slides_tool.Refused([
            'The render has 8 pages for 2 slides; check the deck for an import problem The '
            'preview deck is in Drive (https://docs.example.com/presentation/d/file-9/edit); '
            'retry with --file-id file-9.'])
        tools = self.composer()
        with mock.patch.object(self.slides, 'preview', side_effect=refusal) as asked:
            self.refused(tools.preview_section(json.dumps(drawn(self.spec))))
            self.assertEqual(json.loads((self.base / 'preview-file.json').read_text()), {
                'name': 'Preview: Rolling restarts', 'id': 'file-9',
                'url': 'https://docs.example.com/presentation/d/file-9/edit'})
            self.refused(tools.preview_section(json.dumps(drawn(self.spec))))
            self.assertEqual(asked.call_args.kwargs['file_id'], 'file-9',
                             'the next preview writes that file again')

    def test_a_turn_left_by_a_process_that_ended_is_taken(self):
        lock = self.base / 'render.lock'
        lock.write_text('999999999')
        with worker_tools.one_at_a_time(lock):
            self.assertTrue(lock.is_file())
        self.assertFalse(lock.exists())


class ReviewToolTests(ToolCase):
    def reviewer(self, **more) -> worker_tools.WorkerTools:
        whole = self.base / 'whole'
        whole.mkdir(exist_ok=True)
        (whole / 'composition.json').write_text(json.dumps({
            'title': 'Rolling restarts', 'slides': [
                {'id': slide['id'], 'title': slide['title'], 'layout': 'x',
                 'sources': slide.get('sources')} for slide in OUTLINE['slides']]}))
        if not (whole / 'compiled').exists():
            self.slides.compile(whole / 'composition.json', self.contract, whole / 'compiled')
            self.shown = self.slides.preview(whole / 'compiled', whole / 'preview', 'local')
        slides = [{key: slide[key] for key in ('number', 'id', 'title', 'image')}
                  for slide in self.shown['slides']]
        return self.tools(inputs={'the review': 'Eight questions.'}, ask=False, review={
            'preview': str(whole / 'preview'), 'deck': self.shown['deckSha256'],
            'slides': slides, 'recorded': str(whole / 'assessment.json')}, **more)

    def test_a_reviewer_looks_at_every_slide_at_full_size_before_handing_in(self):
        tools = self.reviewer()
        self.assertEqual(self.offered(tools), ['list_inputs', 'read_input', 'look_at_slide',
                                               'submit_assessment'])
        self.assertEqual(self.refused(tools.submit_assessment([])), 'Look at every slide '
                         'first. Not looked at yet: 1, 2, 3, 4, 5, 6.')
        looked = tools.look_at_slide(2)
        self.assertEqual((looked[1], [path.read_bytes() for path in looked.pictures]), (
            'Slide 2, `what-it-does`: "A rolling restart replaces instances one batch at a '
            'time".', [png(2)]))
        self.assertIn('numbered 1, 2, 3, 4, 5, 6', self.refused(tools.look_at_slide(9)))

    def looked(self, **more) -> worker_tools.WorkerTools:
        tools = self.reviewer(**more)
        for number in range(1, 7):
            self.ok(tools.look_at_slide(number))
        return tools

    def test_an_assessment_is_recorded_against_the_render_with_what_each_finding_is_about(self):
        tools = self.looked()
        said = self.refused(tools.submit_assessment([{**MAJOR, 'note': 'Bad.'}], ['nowhere']))
        self.assertIn('what-it-does: `note` is one sentence', said)
        self.assertIn('weakest names up to three slides', said)
        self.assertEqual(self.ok(tools.submit_assessment(json.dumps([MAJOR, SAID]),
                                                         ['what-it-does'])),
                         'Recorded: 2 findings.')
        sent = json.loads((self.base / 'whole' / 'preview' / 'critique.json').read_text())
        self.assertEqual((sent['deckSha256'], sent['reviewer'], sent['findings'][1]), (
            self.shown['deckSha256'], 'independent',
            {key: SAID[key] for key in ('slide', 'question', 'severity', 'note')}))
        kept = worker_tools.collect(self.job)['assessment']
        self.assertEqual([(finding['number'], finding['about']) for finding in kept['findings']],
                         [(2, 'drawing'), (4, 'content')])

    def test_every_way_a_finding_can_be_wrong_is_said(self):
        slides = [{'id': slide['id'], 'number': number}
                  for number, slide in enumerate(OUTLINE['slides'], start=1)]
        for wrong, why in (({**MAJOR, 'slide': 'x'}, 'is not a slide of this deck'),
                           ({**MAJOR, 'question': 9}, '`question` is a number from 1 to 8'),
                           ({**MAJOR, 'severity': 'bad'}, '`severity` is one of'),
                           ({**MAJOR, 'note': 'Bad.'}, '`note` is one sentence'),
                           ({**MAJOR, 'about': 'taste'}, '`about` is one of: drawing')):
            self.assertIn(why, build.checked(wrong, slides)[1])

    def test_what_the_tool_refuses_in_an_assessment_goes_back_to_the_reviewer(self):
        tools = self.looked()
        self.slides.refuse['critique'] = ['Question 3 was answered twice for one slide.']
        self.assertIn('- Question 3 was answered twice for one slide.',
                      self.refused(tools.submit_assessment([MAJOR])))
        self.assertIsNone(worker_tools.collect(self.job)['assessment'])

    def test_a_render_takes_one_assessment_so_an_earlier_one_stands(self):
        self.ok(self.looked().submit_assessment([MAJOR]))
        self.job = self.base / 'second-try'
        again = self.looked()
        self.assertIn('An assessment was already recorded for this render, and a render takes '
                      'only one, so that one stands.', self.ok(again.submit_assessment([])))
        self.assertEqual(worker_tools.collect(self.job)['assessment']['findings'][0]['slide'],
                         'what-it-does')
        self.assertEqual([call[0] for call in self.slides.calls].count('critique'), 1)

    def test_a_picture_reaches_an_agent_as_an_image_after_the_text(self):
        tools = self.reviewer()
        reply = worker_tools.answer(tools, {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                                            'params': {'name': 'look_at_slide',
                                                       'arguments': {'number': 3}}})['result']
        self.assertEqual((reply['isError'], [part['type'] for part in reply['content']]),
                         (False, ['text', 'image']))
        image = reply['content'][1]
        self.assertEqual((image['mimeType'], worker_tools.base64.b64decode(image['data'])),
                         ('image/png', png(3)))
        log = [json.loads(line) for line in (self.job / 'tools.log').read_text().splitlines()]
        self.assertEqual((log[-1]['tool'], log[-1]['pictures']), ('look_at_slide', 1))

    def test_only_a_real_picture_is_ever_shown(self):
        tools = self.reviewer()
        Path(self.shown['slides'][0]['image']).write_text('not a picture')
        self.assertEqual(self.refused(tools.look_at_slide(1)), 'That picture cannot be shown.')
        with self.assertRaisesRegex(WorkspaceError, 'outside its own folder'):
            worker_tools.pictures({'slides': [{'number': 1, 'id': 'a',
                                               'image': str(self.base / 'elsewhere.png')}]},
                                  self.base / 'whole' / 'preview', self.base / 'kept')

if __name__ == '__main__':
    unittest.main()
