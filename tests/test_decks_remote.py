import helpers  # noqa: F401
import hub
from test_runner_gitstate import WorkspaceCase, git
from runner import decks, gitstate

BRANDS = [{'brand': 'tanzu', 'variants': ['light']}]
FORM = {'route': 'scratch', 'title': 'Spring AI', 'brand': 'tanzu', 'variant': 'light',
        'output': 'google'}


class RemoteIdTests(WorkspaceCase):
    def test_id_taken_on_remote_only(self):
        self.be('blake')
        mine = self.join()
        self.be('alex')
        theirs = self.join()
        decks.create(theirs, decks.check_form(FORM, BRANDS))
        gitstate.sync(theirs)
        self.be('blake')
        hub.run(mine.repo, 'fetch', '--quiet')       # tracking ref ahead; nothing merged
        self.assertFalse(mine.deck('spring-ai').exists())
        self.assertEqual(decks.deck_id(mine, 'Spring AI'), 'spring-ai-2')
        self.assertEqual(decks.create(mine, decks.check_form(FORM, BRANDS)).name,
                         'spring-ai-2')
