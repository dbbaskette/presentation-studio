"""The team hub: a git repository of published decks.

A hub is cloned under the per-user data folder and everything here works on that copy. Only
`join` and `sync` talk to the remote, with the user's own git identity and credentials.
Nothing is force-pushed, and nothing already in a hub is replaced.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import home
import workspace
from workspace import WorkspaceError

SCHEMA = 1
IDENT = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
REVISION = re.compile(r'^[1-9][0-9]*$')
RECORD = re.compile(r'^decks/([^/]+)/([1-9][0-9]*)/record\.json$')
# A password after a colon, or on a web address a name too long to be a username: a token.
ADDRESS_WITH_SECRET = re.compile(r'^[a-z][a-z0-9+.-]*://[^/@]*:[^/@]*@|^https?://[^/@]{20,}@',
                                 re.IGNORECASE)
NEVER = ('sources', 'work', workspace.STATE_DIR, '.harness-research', '.harness-slides')
REBUILT = ('README.md', 'hub.json')
INHERITED = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
             'GIT_COMMON_DIR')
COPY_AS_IS = ('-c', 'core.autocrlf=false', '-c', 'core.symlinks=false')
REMOTE = ('clone', 'fetch', 'push', 'ls-remote')   # the commands that reach a remote
BATCH_SSH = 'ssh -o BatchMode=yes'
ATTEMPTS = 3
TIMEOUT = 120


# --- git ----------------------------------------------------------------------

class GitError(WorkspaceError):
    """git failed; the message is the line of its output that says why."""


def subcommand(args: tuple[str, ...]) -> str | None:
    """The git command in a list of arguments, after any `-c name=value` before it."""
    at = 0
    while at < len(args) and args[at] == '-c':
        at += 2
    return args[at] if at < len(args) else None


def run(repo: Path, *args: str, input: str | None = None,
        timeout: float = TIMEOUT) -> subprocess.CompletedProcess:
    """Run git in `repo` without prompting, and without reaching a repository above it.

    git has no terminal to ask on: it runs in a session of its own, and ssh is told not
    to ask for a passphrase or about a host key, unless the user chose their own ssh
    command. `input` is what git reads, when it reads anything. A command that cannot
    start or does not finish in `timeout` seconds comes back as a failed one, so a slow
    remote is handled like an unreachable one.
    """
    env = {key: value for key, value in os.environ.items() if key not in INHERITED}
    env.update(GIT_TERMINAL_PROMPT='0', GIT_EDITOR='true',
               GIT_CEILING_DIRECTORIES=str(repo.parent))
    if subcommand(args) in REMOTE and not own_ssh(repo, env):
        env['GIT_SSH_COMMAND'] = BATCH_SSH
    try:
        return subprocess.run(['git', *args], cwd=repo, env=env, capture_output=True,
                              stdin=subprocess.DEVNULL if input is None else None,
                              input=input, encoding='utf-8', errors='replace',
                              timeout=timeout, start_new_session=True)
    except subprocess.TimeoutExpired:
        problem = f'git {subcommand(args)} did not finish in {timeout:g} seconds'
    except OSError as failure:
        if shutil.which('git') is None:
            raise WorkspaceError('A hub needs git, which is not installed. Install it and '
                                 'try again.')
        problem = str(failure)
    return subprocess.CompletedProcess(args, 124, '', f'fatal: {problem}')


def own_ssh(repo: Path, env: dict) -> bool:
    """True when the user chose how git runs ssh, which is then left as they chose."""
    if env.get('GIT_SSH_COMMAND') or env.get('GIT_SSH'):
        return True
    return bool(run(repo, 'config', '--get', 'core.sshCommand').stdout.strip())


def reason(done: subprocess.CompletedProcess) -> str:
    """Why git failed, in its own words and the remote's: one line, with no full stop."""
    lines = [line.strip() for line in done.stderr.splitlines() if line.strip()]
    said = ' '.join(line[8:] for line in lines if line.startswith('remote: '))
    for prefix in ('fatal: ', '! ', 'error: ', ''):
        for line in lines:
            if line.startswith(prefix) and not line.startswith('remote: '):
                return (line[len(prefix):] + (f': {said}' if said else '')).rstrip('.')
    return said.rstrip('.') or 'git failed'


def git(repo: Path, *args: str) -> str:
    done = run(repo, *args)
    if done.returncode != 0:
        raise GitError(reason(done))
    return done.stdout.strip()


def passes(repo: Path, *args: str) -> bool:
    return run(repo, *args).returncode == 0


def names(output: str) -> list[str]:
    """Paths from git output that was asked for with -z."""
    return [path for path in output.split('\0') if path]


def identity(repo: Path) -> str:
    """The name git will put on a commit. Refuses when git has none."""
    done = run(repo, 'var', 'GIT_AUTHOR_IDENT')
    name = done.stdout.rpartition(' <')[0].strip() if done.returncode == 0 else ''
    if not name:
        raise WorkspaceError(
            'git does not know who you are, so nothing can be recorded in a hub. Set your '
            'name and email with git config --global user.name and git config --global '
            'user.email, then try again.')
    return name


def commit(repo: Path, message: str, changed: bool | None = None) -> bool:
    """Commit everything that changed in a local copy. False when nothing did."""
    if not (git(repo, 'status', '--porcelain') if changed is None else changed):
        return False
    git(repo, 'add', '-A')
    done = run(repo, 'commit', '--quiet', '-m', message)
    if done.returncode != 0:
        identity(repo)
        raise GitError(reason(done))
    return True


def upstream(repo: Path) -> tuple[str, str]:
    """The branch a local copy is on, and the remote-tracking ref it follows."""
    head = (repo / '.git' / 'HEAD').read_text(encoding='utf-8').strip()
    if not head.startswith('ref: refs/heads/'):
        raise WorkspaceError(f'The local copy of this hub in {repo} is not on a branch. Check '
                             'its branch out there with git, then try again.')
    branch = head.removeprefix('ref: refs/heads/')
    return branch, f'refs/remotes/origin/{branch}'


def apart(repo: Path, tracking: str) -> tuple[int, int] | None:
    """Commits only the local copy has and commits only the remote has, as of the last
    fetch. None while the remote has no such branch."""
    done = run(repo, 'rev-list', '--left-right', '--count', f'HEAD...{tracking}')
    return tuple(map(int, done.stdout.split())) if done.returncode == 0 else None


def ahead(repo: Path, tracking: str) -> int:
    """How many local commits the remote did not have when it was last reached."""
    counts = apart(repo, tracking)
    if counts is None:
        done = run(repo, 'rev-list', '--count', 'HEAD')
        return int(done.stdout) if done.returncode == 0 else 0
    return counts[0]


# --- the hubs joined on this computer ---------------------------------------------

def check_ident(value: str, label: str) -> str:
    if not IDENT.match(value):
        raise WorkspaceError(f'{label} is lowercase letters, digits and hyphens, at most 64, '
                             f'starting with a letter or digit; "{value}" is not.')
    return value


def folder() -> Path:
    """Where local copies of hubs are kept."""
    return home.data_root() / 'hubs'


def clone_of(name: str) -> Path:
    return folder() / name


def joined() -> dict[str, dict]:
    registry = home.read_json(home.data_root() / 'hubs.json', {})
    hubs = registry.get('hubs') if isinstance(registry, dict) else None
    return hubs if isinstance(hubs, dict) else {}


def remember(name: str, **changes) -> None:
    hubs = joined()
    hubs[name] = {**hubs.get(name, {}), **changes}
    home.write_json(home.data_root() / 'hubs.json', {'schema': SCHEMA, 'hubs': hubs})


@contextmanager
def locked(name: str):
    """One command at a time on a hub's local copy."""
    path = folder() / f'.{name}.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            text = path.read_text(encoding='utf-8').strip() if path.is_file() else ''
            if text.isdigit() and home.alive(int(text)):
                raise WorkspaceError('Another Presentation Studio command is working on this '
                                     f'hub (process {text}). Try again when it finishes.')
            path.unlink(missing_ok=True)
            continue
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        break
    else:
        raise WorkspaceError('Could not take the hub lock.')
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def check_layout(described) -> dict:
    if not isinstance(described, dict) or not isinstance(described.get('name'), str):
        raise WorkspaceError('The hub.json in that repository cannot be read, so it cannot '
                             'be used as a hub.')
    if described.get('schema') != SCHEMA:
        raise WorkspaceError(f"That hub uses layout {described.get('schema')!r}, which this "
                             'version of Presentation Studio does not understand. Update the '
                             'skill to use it.')
    return described


def chosen(root: Path) -> str | None:
    """The hub a deck publishes to, if it has chosen one."""
    found = home.read_json(root / workspace.STATE_DIR / 'hub.json', None)
    return found.get('hub') if isinstance(found, dict) else None


def choose(root: Path, name: str) -> None:
    if chosen(root) != name:
        home.write_json(root / workspace.STATE_DIR / 'hub.json', {'schema': SCHEMA, 'hub': name})


def resolve(root: Path, name: str | None = None) -> str:
    """The hub a command works on: the one named, this deck's, or the only one joined."""
    hubs = joined()
    wanted = name or chosen(root)
    if wanted is None:
        if not hubs:
            raise WorkspaceError('No hub is joined on this computer. Join one with '
                                 'hub join URL.')
        if len(hubs) > 1:
            raise WorkspaceError('Several hubs are joined: ' + ', '.join(sorted(hubs))
                                 + '. Choose one for this deck with hub use NAME, or name '
                                 'one with --hub NAME on sync.')
        wanted = next(iter(hubs))
    if wanted not in hubs or not (clone_of(wanted) / '.git').exists():
        raise WorkspaceError(f'No hub called "{wanted}" is joined on this computer. hub list '
                             'shows the ones that are; hub join URL adds one.')
    check_layout(load(clone_of(wanted), 'hub.json'))
    return wanted


def name_from(url: str) -> str:
    stem = re.split(r'[/:]', url.rstrip('/'))[-1].removesuffix('.git')
    slug = re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-')[:64].strip('-')
    return slug or 'hub'


def join(url: str, name: str | None = None, init: bool = False) -> dict:
    """Clone a hub and remember it. `init` lays a new hub out in an empty repository."""
    if ADDRESS_WITH_SECRET.match(url):
        raise WorkspaceError('That address carries a password or token. Give the address '
                             'without it; git signs in with your own credentials.')
    taken = ('A hub called "{}" is already joined on this computer. Bring it up to date '
             'with hub sync, or join under another name with --name.')
    if name is not None and clone_of(check_ident(name, 'A hub name')).exists():
        raise WorkspaceError(taken.format(name))
    folder().mkdir(parents=True, exist_ok=True)
    pending = folder() / f'.joining-{secrets.token_hex(4)}'
    try:
        cloned = run(folder(), 'clone', '--quiet', *COPY_AS_IS, '--', url, str(pending))
        if cloned.returncode != 0:
            raise WorkspaceError(f'Could not clone {url}: {reason(cloned)}. Check the address, '
                                 'and that git can sign in to it without asking.')
        described = load(pending, 'hub.json')
        fresh = described is None
        if fresh:
            empty = not passes(pending, 'rev-parse', '--verify', '--quiet', 'HEAD')
            if not empty:
                raise WorkspaceError(
                    'That repository is not a hub: it has no hub.json. '
                    + ('--init sets up an empty repository, and this one already has files. '
                       'Make a new, empty repository for the hub.' if init
                       else 'Check the address.'))
            if not init:
                raise WorkspaceError('That repository is empty: it has no hub.json yet. If it '
                                     'is meant to be a new hub, join it with --init.')
            name = name or name_from(url)
            home.write_json(pending / 'hub.json', {'schema': SCHEMA, 'name': name})
            reindex(pending)
            commit(pending, 'Set up the hub', True)
        else:
            label = check_layout(described)['name']
            name = name or (label if IDENT.match(label) else name_from(url))
        if clone_of(name).exists():
            raise WorkspaceError(taken.format(name))
        pending.replace(clone_of(name))
    finally:
        shutil.rmtree(pending, ignore_errors=True)
    remember(name, url=url, joined_at=home.now(), synced_at=None if fresh else home.now())
    with locked(name):
        outcome = _sync(name) if fresh else {'pushed': True, 'notice': None}
    repo = clone_of(name)
    return {'hub': name, 'url': url, 'path': str(repo), 'initialised': fresh,
            'pushed': outcome['pushed'], 'notice': outcome['notice'],
            'decks': len(latest(repo))}


def listing(root: Path) -> dict:
    """The hubs joined here, and whether each has changes the remote does not."""
    current = chosen(root)
    hubs = []
    for name, entry in sorted(joined().items()):
        repo = clone_of(name)
        item = {'name': name, 'url': entry.get('url'), 'path': str(repo),
                'joined_at': entry.get('joined_at'), 'synced_at': entry.get('synced_at'),
                'chosen': name == current}
        try:
            if not (repo / '.git').exists():
                raise WorkspaceError('Its local copy is missing. Join it again with hub join.')
            unpushed = ahead(repo, upstream(repo)[1])
            uncommitted = bool(git(repo, 'status', '--porcelain'))
            item.update(unpushed=unpushed, uncommitted=uncommitted,
                        pushed=not unpushed and not uncommitted)
        except WorkspaceError as problem:
            item.update(unpushed=None, uncommitted=None, pushed=False, notice=str(problem))
        hubs.append(item)
    return {'hubs': hubs}


def use(root: Path, name: str) -> dict:
    """Make a joined hub the one this deck publishes to."""
    choose(root, resolve(root, name))
    return {'hub': name}


# --- what a hub holds ---------------------------------------------------------------

def hub_file(repo: Path, relative: str) -> Path | None:
    """A file inside a hub's local copy. A hub is other people's data, so a path that
    leaves the copy, or goes through a symbolic link, is not followed."""
    path = repo / relative
    inside = PurePosixPath(relative)
    if inside.is_absolute() or '..' in inside.parts or not path.is_file():
        return None
    return path if path.resolve() == repo.resolve() / relative else None


def slot(repo: Path, relative: str) -> Path:
    """Where something new goes in a hub's local copy. Refuses a place that a symbolic
    link in the hub would carry somewhere else."""
    path = repo / relative
    if path.is_symlink() or path.parent.resolve() != (repo.resolve() / relative).parent:
        raise WorkspaceError(f'{relative} in this hub goes through a symbolic link, so '
                             'nothing was written. Ask whoever looks after the hub to '
                             'remove the link.')
    return path


def read(repo: Path, relative: str) -> str | None:
    path = hub_file(repo, relative)
    return path.read_text(encoding='utf-8', errors='replace') if path else None


def load(repo: Path, relative: str):
    """A JSON file in a hub's local copy, or None when it is missing or cannot be read."""
    try:
        return json.loads(read(repo, relative) or '')
    except ValueError:
        return None


def revisions(repo: Path, deck: str) -> list[int]:
    held = repo / 'decks' / deck
    if not held.is_dir():
        return []
    return sorted(int(path.name) for path in held.iterdir() if REVISION.match(path.name)
                  and hub_file(repo, f'decks/{deck}/{path.name}/record.json'))


def record(repo: Path, deck: str, revision: int) -> dict:
    found = load(repo, f'decks/{deck}/{revision}/record.json')
    found = found if isinstance(found, dict) else {}
    files = found.get('files')
    found['files'] = [entry for entry in files if isinstance(entry, dict)
                      and isinstance(entry.get('path'), str)] if isinstance(files, list) else []
    return found


def latest(repo: Path) -> list[dict]:
    """The newest record of every deck in a hub."""
    held = repo / 'decks'
    found = []
    for path in sorted(held.iterdir()) if held.is_dir() else ():
        numbers = revisions(repo, path.name) if IDENT.match(path.name) else []
        if numbers:
            found.append({**record(repo, path.name, numbers[-1]), 'deck': path.name,
                          'revision': numbers[-1]})
    return found


def cell(value) -> str:
    return ' '.join(str(value).split()).replace('|', '\\|')


def index(repo: Path) -> str:
    """The hub's README: an index built from what the hub holds, and from nothing else."""
    described = load(repo, 'hub.json')
    name = described.get('name') if isinstance(described, dict) else None
    lines = [f'# {cell(name or repo.name)}', '',
             'A Presentation Studio team hub. This page is rebuilt whenever someone syncs, so '
             'changes made to it by hand are lost.', '', '## Decks', '']
    decks = latest(repo)
    if decks:
        lines += ['| Deck | Revision | Published |', '| --- | --- | --- |']
    for entry in decks:
        where = f"decks/{entry['deck']}/{entry['revision']}/"
        lines.append(
            f"| [{cell(entry.get('title') or entry['deck'])}]({where}) "
            f"| {entry['revision']} | {cell(str(entry.get('published_at'))[:10])} by "
            f"{cell(entry.get('published_by'))} |")
    lines += [] if decks else ['None yet.']
    return '\n'.join(lines) + '\n'


def reindex(repo: Path) -> bool:
    """Rebuild the index. False when it already said the same."""
    page = repo / 'README.md'
    text = index(repo)
    if read(repo, 'README.md') == text:
        return False
    page.unlink(missing_ok=True)
    page.write_text(text, encoding='utf-8')
    return True


# --- sync -----------------------------------------------------------------------------

def settle(repo: Path, unmerged: list[str], report: dict) -> None:
    """Resolve the commit a rebase stopped on, keeping everything the remote already has.

    A revision whose number is taken moves to the next free number. The index and hub.json
    are the remote's. Anything else is a conflict for the user, and raises.
    """
    picked = git(repo, 'rev-parse', 'REBASE_HEAD')
    collided = sorted({RECORD.match(path).groups() for path in unmerged if RECORD.match(path)})
    for path in unmerged:
        parts = path.split('/')
        if parts[0] == 'decks' and tuple(parts[1:3]) in collided:
            continue
        if path not in REBUILT or not passes(repo, 'checkout', 'HEAD', '--', path):
            raise WorkspaceError(
                f'The copy of this hub on this computer and its remote both changed {path}, '
                f'and Presentation Studio cannot tell which to keep. Nothing was pushed. '
                f'Settle it with git in {repo}, then run hub sync again.')
    for deck, revision in collided:
        held = repo / 'decks' / deck
        old = f'decks/{deck}/{revision}'
        mine = names(git(repo, 'ls-tree', '-r', '-z', '--name-only', picked, '--', old + '/'))
        git(repo, 'checkout', picked, '--', old)
        new = max(int(path.name) for path in held.iterdir() if REVISION.match(path.name)) + 1
        for path in mine:
            target = held / str(new) / PurePosixPath(path).relative_to(old)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(repo / path, target)
        git(repo, 'checkout', 'HEAD', '--', old)
        moved = home.read_json(held / str(new) / 'record.json', {})
        home.write_json(held / str(new) / 'record.json', {**moved, 'revision': new})
        report['renumbered'].append({'deck': deck, 'from': int(revision), 'to': new})
    git(repo, 'add', '-A')


def rebase(repo: Path, tracking: str, report: dict) -> None:
    """Replay local commits on top of the remote's. Published history is never rewritten."""
    done = run(repo, 'rebase', tracking)
    while done.returncode != 0:
        unmerged = names(run(repo, 'diff', '-z', '--name-only', '--diff-filter=U').stdout)
        try:
            if not unmerged or not (repo / '.git' / 'rebase-merge').is_dir():
                raise GitError(f'git could not replay the changes made on this computer '
                               f'({reason(done)}). Nothing was pushed.')
            settle(repo, unmerged, report)
        except WorkspaceError:
            run(repo, 'rebase', '--abort')
            raise
        done = run(repo, 'rebase', '--continue')


def _sync(name: str) -> dict:
    """Commit, fetch, rebase and push one hub. The caller holds its lock.

    `pushed` is true only when nothing in the local copy is missing from the remote. When
    the remote cannot be reached or refuses, the work stays committed here and `notice`
    says so.
    """
    repo = clone_of(name)
    branch, tracking = upstream(repo)
    report = {'hub': name, 'reached': True, 'received': 0, 'renumbered': [],
              'notice': None}
    commit(repo, 'Add changes made in the local copy')
    waiting, refused = None, None
    for _ in range(ATTEMPTS):
        fetched = run(repo, 'fetch', '--quiet', 'origin')
        if fetched.returncode != 0:
            report['reached'] = False
            break
        mine, theirs = apart(repo, tracking) or (None, 0)
        if refused and not theirs:
            break  # nobody pushed in between: the remote refused for a reason of its own
        if theirs:
            report['received'] += theirs
            rebase(repo, tracking, report)
        indexed = reindex(repo) and commit(repo, 'Update the index')
        waiting = ahead(repo, tracking) if theirs or mine is None else mine + bool(indexed)
        if not waiting:
            break
        sent = run(repo, 'push', '--quiet', 'origin', f'HEAD:refs/heads/{branch}')
        if sent.returncode == 0:
            waiting = 0
            break
        refused = reason(sent)
    report['unpushed'] = ahead(repo, tracking) if waiting is None else waiting
    report['pushed'] = not report['unpushed']
    if not report['reached']:
        report['notice'] = f"The hub's remote could not be reached ({reason(fetched)}). " + (
            'What was added is kept on this computer and is not shared yet. Run hub sync when '
            'the remote can be reached.' if report['unpushed'] else
            'Nothing here is waiting to be shared, but this copy may be out of date.')
    elif report['unpushed']:
        report['notice'] = (f"The hub's remote did not accept the changes ({refused}). They "
                            'are kept on this computer and are not shared yet. Check that you '
                            'may push to the hub, then run hub sync.')
    else:
        remember(name, synced_at=home.now())
    report['synced_at'] = joined()[name].get('synced_at')
    return report


def sync(name: str) -> dict:
    with locked(name):
        return _sync(name)
