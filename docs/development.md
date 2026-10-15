# Development

Working agreements for this repository are in [AGENTS.md](../AGENTS.md). The specification is the [design](superpowers/specs/2026-10-14-presentation-studio-design.md) and the build order is the [plan](superpowers/plans/2026-10-14-presentation-studio.md). Much of the code was ported from [Training Studio](https://github.com/dbbaskette/training-studio); `vendor.json` lists every ported file with the file and revision it came from.

## Layout

```
skills/presentation-studio/
  SKILL.md                  the chat skill: making a deck in a conversation
  references/               routes, levels and the workspace, each linked from SKILL.md
  VERSION
  scripts/                  the core the runner stands on
    workspace.py            the refusal a person reads, and safe writes
    home.py                 the per-user data folder and its JSON files
    hub.py                  git for a shared workspace
    sync_guidance.py        fetches, pins and verifies guidance
    studios_config.py       the values every studio shares
    computer.py             what this computer has for making a deck
    gdrive.py               Google Drive through gcloud
    server.py               the page's local server and its rules
    validate_package.py     package and progressive-disclosure checks
    desk/                   the page: index.html, app.js, markdown.js and its styles
runner/                     the runner: studio.py, the engine, its steps and the workers' briefs
bootstrap/presentation-studio/  the small entry an installed copy uses
guidance/manifest.json      which runtime version the guidance needs
installer/                  install.sh, install.py and a double-click launcher;
                            companions.json pins harness-slides and harness-research
tests/                      unit tests; temporary directories only
  stand_ins/                harness-slides, harness-research and a brand skill, played in Python
  fixtures/                 a companion's own contract fixtures, copied unchanged
docs/                       this documentation, the spec and the plan
```

## Run the tests

You need Python 3.11 or newer and git. Nothing else is installed, and there is no build step.

```bash
python3 scripts/ci/run_tests.py
```

That runs the whole suite in parallel, each test class in a process of its own, and exits non-zero on any failure. Give it modules, classes or tests to run only those, `--jobs N` to change how many run at once, and `--times` to list each class with the time it took:

```bash
python3 scripts/ci/run_tests.py test_installer test_runner_upkeep.LinkTests --times
```

Plain unittest works too, from the `tests` folder:

```bash
cd tests && python3 -m unittest test_package -v
```

Where `python3` is older than 3.11, as on a stock Mac, run the suite with a newer Python by its full path.

```bash
python3 skills/presentation-studio/scripts/validate_package.py            # whole, or the problems
python3 skills/presentation-studio/scripts/validate_package.py --measure  # sizes against budgets
```

The validator confirms the package is whole: the required files exist, every link resolves, every reference is linked from `SKILL.md`, and each file and loading set is within its budget. The installer runs it before installing anything.

## What the tests never do

- **No network.** Every repository a test uses is a bare one it made in a temporary folder. The installer's tests pin stand-in companion repositories made the same way, and fetch nothing from anywhere else.
- **No real data folder or home.** `tests/helpers.py` sets `PRESENTATION_STUDIO_DATA` to a temporary folder, points `STUDIOS_CONFIG` at a file that is not there until a test writes it, and gives git a quiet config of its own. The installer is always run against a temporary home.
- **No real companion, agent, Google or render.** The runner's tests use the stand-ins in `tests/stand_ins/`, which answer as harness-slides, harness-research and a brand skill do, and scripted workers in place of an assistant. The brand they use is made up.
- **No brand named.** `tests/test_no_brand_named.py` fails if any tracked file names a real brand.

A few tests need Node: those that run the page's own scripts through `tests/page_harness.js`, and those where a stand-in companion installs itself. They are skipped without it.

## Working on the skill

Link your checkout so your assistant and the `studio` command use your changes as you make them:

```bash
sh installer/install.sh install --link
```

Undo it with `sh installer/install.sh uninstall`. Without installing, the runner starts with `python3 runner/studio.py serve --open`; `PRESENTATION_STUDIO_FAKE=1` serves the page over the tests' stand-ins, for looking at it, with nothing of yours read or written.

## Releasing

`main` is live: an installed copy fetches its guidance from it. Guidance that needs a script change raises `minimum_runtime` in `guidance/manifest.json` and the `VERSION` files together. A release is a `vX.Y.Z` tag on `main`; the runner offers it as an upgrade.

To move a companion to a newer revision of its own repository:

```bash
sh installer/install.sh pin harness-slides --revision v0.14.2
```

That fetches the revision, reads its version and writes its commit and the digest of every file into `installer/companions.json`. Read what changed between the two revisions before you commit it.
