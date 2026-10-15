"""The Studio Runner: a program that takes a deck from a form to its delivery, stopping
at every gate for a decision on the page.

This package holds the parts every later part stands on; the rest is added as the runner
grows. Each module's own docstring says what a caller needs to know.

    settings       what this computer remembers: the default agent and the limits
    companion      finding a companion skill, and running any command so that Stop and a
                   time limit end everything it started
    agents         starting the person's own agent as a confined worker for one job
    worker_tools   the only tools a worker has, and the server that offers them
    slides         the harness-slides command line
    brand          a brand skill, such as tanzu-brand
    research       the harness-research command line
    documents      documents and pasted text a person supplies for a deck
    steps          the steps a deck goes through, one module per family of stages

The core's modules sit beside this package, in skills/presentation-studio/scripts:

    workspace      the refusal a person reads (WorkspaceError) and safe writes
    home           what belongs to this computer: the data folder, JSON files, the decks
                   it remembers
    hub            a team hub: a git repository of published decks, joined and synced
    sync_guidance  fetching, pinning and verifying the guidance a deck follows
    computer       whether this computer has what a deck needs
    gdrive         Google Drive through gcloud: a Google Doc read as text

Refusals meant for a person are raised as the core's WorkspaceError, with a sentence to
show as it is.

Importing this package puts the core on the import path, so `import workspace` and
`import home` work anywhere in the runner. The core is found in either layout: in a
checkout of the repository it is skills/presentation-studio/scripts, and in an installed
version it is the scripts folder beside this package.
"""
import sys
from pathlib import Path

_ABOVE = Path(__file__).resolve().parent.parent
CORE = next((place for place in (_ABOVE / 'skills' / 'presentation-studio' / 'scripts',
                                 _ABOVE / 'scripts')
             if (place / 'workspace.py').is_file()), _ABOVE / 'scripts')
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))
