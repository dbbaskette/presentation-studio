# Acceptance

Live acceptance needs a person: a real install, and real decks taken through every stop with a real assistant, real companion skills and a real brand skill. Nothing on this page is filled in by simulation. Automated verification is described in [development](development.md).

Each run uses a disposable folder outside this repository, and a workspace made for it. Record refusals and failed checks as well as approvals.

## The setup

| | |
| --- | --- |
| Date | |
| Computer and system | |
| Presentation Studio commit and version | |
| Assistant and version | |
| harness-slides version | |
| harness-research version | |
| Brand skill and version (named here only in the run's own notes, not in this repository) | |
| Previews made with | LibreOffice / Google Drive |
| Google sign-in | yes / no |

## Install

| Check | Outcome | Notes |
| --- | --- | --- |
| `sh installer/install.sh` on a fresh home: the plan, the question, the links for each assistant | | |
| Each companion offered, fetched at its pin, checked and installed by its own installer | | |
| "Worth knowing" lists only what is really missing | | |
| "Open Presentation Studio" opens the page; `studio status` answers | | |
| The brand skill installed from Settings, from its repository | | |
| `check`, then `uninstall`, then install again | | |

## On the page

### Run 1: from scratch, research on

| Stop | Outcome | Notes |
| --- | --- | --- |
| Research plan | | |
| Research | | |
| Outline | | |
| Look | | |
| Build | | |
| Delivered as Google Slides | | |

### Run 2: from a document

The document's kind, what the studio said it was, and whether it was corrected.

| Stop | Outcome | Notes |
| --- | --- | --- |
| Classify | | |
| Outline | | |
| Look | | |
| Build | | |
| Delivered as PowerPoint | | |

### Run 3: an existing deck, at each level

| Level | Classify | Outline | Look | Build | Delivered | The original unchanged |
| --- | --- | --- | --- | --- | --- | --- |
| Brand only | | — | — | | | |
| Polish | | — | — | | | |
| Redesign, keep content | | — | | | | |
| Full rework | | | | | | |
| Selected changes | | — | — | | | |

### Changes after delivery

Which slides were named, which were rebuilt, and the revision delivered.

### With a team

Two computers against one team repository: a deck started on one and read-only on the other, taken over, handed back, and published. What each page said, and the commits that resulted.

### Stopped and started again

The stop where the runner was closed, and what the page showed when it was opened again.

## In a conversation

A deck made with `/presentation-studio` in Claude Code and in Codex: the route, whether every stop waited for approval, the deck folder it left under `presentations/`, and whether its `run.json` reads as the runner's do.

| Assistant | Route | Every stop waited | Folder as described | Notes |
| --- | --- | --- | --- | --- |
| Claude Code | | | | |
| Codex | | | | |

## Recorded runs

### 2026-10-15: install and the page, on a computer without LibreOffice, Poppler or Google

A partial run. This computer has no LibreOffice, no Poppler and no Google Cloud CLI, and none was installed for it. Everything was done in a disposable home (`HOME=$(mktemp -d)`) and a workspace folder outside this repository, both removed afterwards; the runner was stopped and nothing was left running.

| | |
| --- | --- |
| Date | 2026-10-15 |
| Computer and system | Mac, macOS 15.7.9, Python 3.12 by its full path (the system `python3` is 3.9) |
| Presentation Studio commit and version | 0.1.0 at 32d2694, with the changes of the end-to-end route tests |
| Assistant and version | Claude Code 2.1.300 and Codex 0.162.1, both installed, neither signed in inside the disposable home |
| harness-slides version | 0.14.1 (79eaf89), from a local checkout at its pin |
| harness-research version | 0.8.0 (547506e), from a local checkout at its pin |
| Brand skill and version | a brand skill from a local checkout, release v0.13.3 |
| Previews made with | neither: no LibreOffice, and no Google sign-in |
| Google sign-in | no |

#### Install

| Check | Outcome | Notes |
| --- | --- | --- |
| `installer/install.py install --yes --target claude --companions install --home <disposable home> --pins <pins>` | Installed | The pins file was `companions.json` with each repository pointed at the local checkout, at the same commit and hash. Run with Python 3.12 by its path, since `install.sh` refuses the system 3.9. |
| Each companion fetched at its pin, checked and installed by its own installer | Yes | "harness-research 0.8.0 was installed by its own installer." and the same for harness-slides 0.14.1, whose installer fetched its engine's packages from npm. |
| "Worth knowing" | As expected | git had no identity in the new home; `python3` is 3.9; no brand skill was found. It also said Claude Code cannot be asked whether it is signed in without starting it. |
| `studio status` answers; the page is served | Yes | `studio serve --port <free port>` served the page (200, text/html) and every call below. |
| The brand skill installed from Settings, from its repository | Yes | `POST /api/brand` with the local checkout's absolute path offered release v0.13.3; `POST /api/brand/install` installed it with its own installer in about 45 seconds. Settings then said it "is installed, from <the checkout> at v0.13.3 (revision 0d5c183a1adb). New decks can use it." and listed its brands with a default. |

The workspace was a folder on this computer, set up through `POST /api/setup/check` (all four checks passed) and `POST /api/setup`. Check this computer showed Google Cloud CLI not found and LibreOffice missing; previews were set to this computer.

#### On the page

| Walk | Where it stopped | What the page said |
| --- | --- | --- |
| Run 1, from scratch, research on, five minutes, the brand skill's default brand, delivered as Google Slides | At the start form: no deck was made | "Claude Code is not signed in. Run claude auth login in a terminal, then try again." |
| An existing deck at Brand only: the brand skill's own presentation template (1.9 MB .pptx), uploaded | At the start form: no deck was made | "Claude Code is not signed in. Run claude auth login in a terminal, then try again." |

Claude Code is signed in in the person's own home on this computer, but not in a fresh one, and no credentials were copied in; so no worker ran and nothing was spent. A deck is refused at its start when its assistant cannot be used, before any step, even on a route such as Brand only whose first steps (fetching the deck and listing its slides) need no assistant. Neither walk reached a render: without LibreOffice or Google, the first step that pictures slides (listing the slides of an existing deck, or the look of a new one) would have been the next to stop.

Still to do on a computer with a signed-in assistant and LibreOffice or Google: every stop of Runs 1 to 3, changes after delivery, the team and the restart checks, and the conversation runs.
