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
| Brand | | |
| Build | | |
| Delivered as Google Slides | | |

### Run 2: from a document

The document's kind, what the studio said it was, and whether it was corrected.

| Stop | Outcome | Notes |
| --- | --- | --- |
| Classify | | |
| Outline | | |
| Brand | | |
| Build | | |
| Delivered as PowerPoint | | |

### Run 3: an existing deck, at each level

| Level | Classify | Outline | Brand | Build | Delivered | The original unchanged |
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
| Presentation Studio commit and version | 0.1.0: the working tree of 32d2694 with the end-to-end route tests and a fix to the look step not yet committed; they were committed afterwards, with this record, as a12cbbf |
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

### 2026-10-15: two decks with a signed-in assistant, on a computer without LibreOffice, Poppler or Google

A partial run, after the final review's fixes. The person's own home was kept only so that Claude Code, signed in there, could run; nothing was installed into it. The data folder was a new folder in the home made for this run (a data folder under a shared temporary folder is refused for job folders, see below), the studios config a file in a temporary folder, and the workspace a folder in that temporary folder. The companions and the brand skill were used from local checkouts, named in `HARNESS_SLIDES_RUNTIME`, `HARNESS_RESEARCH_RUNTIME` and `BRAND_SKILL_RUNTIME`; harness-slides had no npm packages in its checkout and none were installed. The page was driven through its addresses with the key handed to the runner at its start. Afterwards the runner was stopped, nothing was left running, and every folder made for the run was removed; the checkouts were unchanged.

| | |
| --- | --- |
| Date | 2026-10-15 |
| Computer and system | Mac, macOS 15.7.9, Python 3.12 by its full path |
| Presentation Studio commit and version | 0.1.0: 95dccdc, with the brand-skill fix below made during the run; both fixes the run found were committed afterwards as 5e8e427 |
| Assistant and version | Claude Code 2.1.300, signed in; model `sonnet`, effort `low`; a deck limit of 4 dollars |
| harness-slides version | 0.14.1 (79eaf89), local checkout |
| harness-research version | 0.8.0 (547506e), local checkout |
| Brand skill and version | a brand skill from a local checkout, v0.13.3 (0d5c183) |
| Previews made with | neither: no LibreOffice, and no Google sign-in |
| Google sign-in | no |

| Walk | Where it stopped | What the page said |
| --- | --- | --- |
| From scratch, research off, four minutes, the brand skill's default brand, as PowerPoint | At the look, after the outline was approved | "The slides cannot be drawn on this computer yet. This computer has no way to render previews of slides. Install LibreOffice, or give it Google access that reaches Drive. The programs the slides tool uses to turn a render into pictures are not on this computer." |
| An existing deck at Brand only: a copy of the brand skill's sample template (35 slides), uploaded, as PowerPoint | At the start of classify, after the deck was brought in | The same sentence. |

On the way:

- The outline was drafted by Claude Code and checked by the real `outline check` (cover, two content slides, closing). It was approved with one slide added the way the page adds one: a light content slide with notes. The real check took it, and the outline was kept with it.
- The brand was exported and the looks were proposed and compiled by the real slides tool; drawing them on a sample slide is where it stopped. The scratch deck spent 0.24 dollars (148,672 tokens). The existing deck spent nothing.
- The real inventory of the sample template (35 slides, most of them showing no words) was read by `pptx inspect` and held to the outline rules offline: whole texts and runs copied slide by slide pass at Brand only, and a cut text is refused.

What the real tools showed, and what was changed for it:

1. The brand skill refused to export the brand ("set up harness-slides ... No executable dependency was downloaded"): it looks for harness-slides in `HARNESS_SLIDES_ROOT` or its own install places, and the runner had found it elsewhere. The runner now tells the brand skill's command the harness-slides and harness-research it uses, in `HARNESS_SLIDES_ROOT` and `HARNESS_RESEARCH_ROOT`, as harness-slides tells a brand adapter to be told (tests: `test_runner_brand.CompanionsTests`).
2. A slide that shows no words, such as a picture alone, could not be read into an outline at any level: every slide needs a title, and every title had to be copied from the deck. Its title is now its own, and is not compared (test: `test_step_outline`, a slide that shows no words).
3. With the data folder in a temporary folder, the outline step failed three times before it said why: job folders may not be under a folder other programs share. This is the rule working; it was met by moving the data folder, and is noted here for whoever runs this next.
4. The first start of the runner, from a program rather than a terminal, opened the page in the browser, as it is meant to; the runner was then started again with a key of its own handed to it.

Still to do on a computer with LibreOffice or Google: everything from the brand (then the look) and from classify onward, changes after delivery, Deliver to Google Slides, the team and the restart checks, and the conversation runs.
