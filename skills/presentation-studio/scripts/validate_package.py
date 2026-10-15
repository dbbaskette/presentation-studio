#!/usr/bin/env python3
"""Confirm the skill package is whole and keeps its progressive-disclosure contract."""
import re
import sys
from pathlib import Path

LINK = re.compile(r'\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)')
EXTERNAL = re.compile(r'^[a-z][a-z0-9+.-]*:')
DESCRIPTION = re.compile(r'^description:\s*(.+)$', re.MULTILINE)
BUDGET = {'description': 100, 'skill': 1000, 'reference': 1000, 'example': 1200}
REQUIRED = (
    'SKILL.md',
    'VERSION',
    'references/routes.md',
    'references/levels.md',
    'references/workspace.md',
    'scripts/validate_package.py',
    'scripts/workspace.py',
    'scripts/home.py',
    'scripts/hub.py',
    'scripts/sync_guidance.py',
    'scripts/studios_config.py',
    'scripts/computer.py',
    'scripts/gdrive.py',
    'scripts/server.py',
    'scripts/desk/index.html',
    'scripts/desk/app.js',
    'scripts/desk/markdown.js',
    'scripts/desk/style.css',
    'scripts/desk/deck.css',
)
GUIDANCE_PARTS = ('SKILL.md', 'references/', 'assets/')


def estimate(text: str) -> int:
    """Estimated tokens: characters divided by four, rounded up."""
    return (len(text) + 3) // 4


def loading_sets() -> dict[str, tuple[list[str], int]]:
    """What each operation reads, and the budget for it in estimated tokens."""
    return {
        'start': (['SKILL.md', 'references/routes.md'], 2000),
        'existing': (['SKILL.md', 'references/routes.md', 'references/levels.md'], 2500),
        'workspace': (['SKILL.md', 'references/workspace.md'], 2000),
    }


def measured(skill: Path) -> dict[str, int]:
    """Estimated tokens for every guidance and example file that exists."""
    files = [skill / 'SKILL.md', *sorted((skill / 'references').rglob('*.md')),
             *sorted((skill / 'assets' / 'examples').glob('*.md'))]
    return {path.relative_to(skill).as_posix(): estimate(path.read_text(encoding='utf-8'))
            for path in files if path.is_file()}


def local_links(document: Path) -> list[tuple[str, Path]]:
    return [(target, (document.parent / target).resolve())
            for target in LINK.findall(document.read_text(encoding='utf-8'))
            if not EXTERNAL.match(target)]


def problems(skill: Path, guidance_only: bool = False) -> list[str]:
    """Everything wrong with the package at `skill`; empty when it is whole.

    `guidance_only` checks a folder holding just SKILL.md, references and assets, which is
    how guidance is kept inside an installed copy and in the fetched cache.
    """
    skill = skill.resolve()
    required = [name for name in REQUIRED
                if not guidance_only or name.startswith(GUIDANCE_PARTS)]
    found = [f'Missing: {name}' for name in required if not (skill / name).is_file()]
    sizes = measured(skill)
    entry = skill / 'SKILL.md'

    for name in sizes:
        if name.startswith('assets/'):
            continue
        for target, resolved in local_links(skill / name):
            if not resolved.exists():
                found.append(f'{name} links to missing {target}')
    from_entry = {resolved for _, resolved in local_links(entry)} if entry.is_file() else set()
    for name in sizes:
        if name != 'SKILL.md' and (skill / name).resolve() not in from_entry:
            found.append(f'{name} is not linked from SKILL.md, so it is more than one hop away')

    for name, size in sizes.items():
        kind = ('skill' if name == 'SKILL.md'
                else 'example' if name.startswith('assets/') else 'reference')
        if size > BUDGET[kind]:
            found.append(f'{name} is {size} estimated tokens; the budget is {BUDGET[kind]}')
    if entry.is_file():
        description = DESCRIPTION.search(entry.read_text(encoding='utf-8'))
        if not description:
            found.append('SKILL.md has no description in its frontmatter')
        elif estimate(description.group(1)) > BUDGET['description']:
            found.append(f'The description is {estimate(description.group(1))} estimated '
                         f"tokens; the budget is {BUDGET['description']}")
    for label, (files, budget) in loading_sets().items():
        if all(name in sizes for name in files):
            total = sum(sizes[name] for name in files)
            if total > budget:
                found.append(f'Loading set {label} is {total} estimated tokens; '
                             f'the budget is {budget}')
    return found


def measure(skill: Path) -> str:
    """A markdown table of every file and loading set against its budget."""
    sizes = measured(skill.resolve())
    lines = ['| File | Estimated tokens |', '| --- | ---: |']
    lines += [f'| `{name}` | {size:,} |' for name, size in sizes.items()]
    lines += [f'| Whole library | {sum(sizes.values()):,} |', '',
              '| Loading set | Estimated tokens | Budget |', '| --- | ---: | ---: |']
    for label, (files, budget) in loading_sets().items():
        total = sum(sizes.get(name, 0) for name in files)
        lines.append(f'| `{label}` | {total:,} | {budget:,} |')
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    show, guidance_only = '--measure' in args, '--guidance' in args
    paths = [arg for arg in args if arg not in ('--measure', '--guidance')]
    skill = Path(paths[0]) if paths else Path(__file__).resolve().parent.parent
    if show:
        print(measure(skill))
        return 0
    found = problems(skill, guidance_only)
    for line in found:
        print(line)
    print('ok' if not found else f'{len(found)} problem(s)')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
