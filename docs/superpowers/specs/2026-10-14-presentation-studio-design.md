# Presentation Studio — Design

Date: 2026-10-14
Status: Draft for review

> **Amendment: any brand (2026-10-14).** Presentation Studio is for any brand. The brand
> skill, and the repository it is installed from, are inputs the person gives: Settings
> names the repository and release, and the page installs and upgrades the brand skill
> from there with the brand skill's own installer, as Training Studio does. Nothing in the
> product names, defaults to or pins a particular brand. The default brand and variant are
> the first the installed brand skill lists, unless Settings or the studios config name
> one. The installer pins only harness-slides and harness-research. Without a brand
> skill, a deck is made up to the first step that needs its brand, and stops there with
> one sentence saying to name the brand skill's repository in Settings. The text below
> is written to match.

## 1. Purpose

Presentation Studio is the third studio beside Training Studio and Blog Studio. It lets
colleagues — a mix of technical and non-technical people — make decks in their brand
through a guided, approval-gated page, without knowing the tools underneath.

It has three entry routes:

1. **Start from scratch** — a brief (and optional research) becomes a deck.
2. **Start from a document** — a document that either *specifies* the slides or is
   *source material* for them becomes a deck.
3. **Redesign an existing deck** — a `.pptx` or Google Slides deck gets your brand's design
   applied, at a chosen level of change.

Success means a colleague installs it with the one-click installer, picks a route, approves
each step on the page while seeing the real slides, and gets a Google Slides deck in their brand
(or `.pptx`) — with all of the work, decisions and the deck link shared in the team
repository.

### Decisions made during brainstorming

| Topic | Decision |
|---|---|
| Audience | Mixed technical and non-technical. The page is the primary surface; a `/presentation-studio` chat skill serves technical users. |
| Output | Google Slides by default, `.pptx` available per deck. No Google sign-in → `.pptx`. |
| Existing-deck change levels | All five harness-slides intake levels, shown as plain-language cards. |
| "From a document" | Handles both slide specs and source material; the studio classifies and the person may correct it. Accepts Markdown/text, Word, PDF, Google Docs and pasted text. |
| Research (from scratch) | Optional per-deck toggle, off by default. |
| Storage and sync | Training Studio's workspace model, in the team's shared repository under `presentations/`, beside `trainings/` and `blogs/`. Blog Studio adopting the same model is tracked in dbbaskette/blog-studio#93. |
| Architecture | Fork-and-trim of Training Studio's runner (approach 1). Extracting a shared studio core is a later, separate project. |
| Rehearsal (Yoodli) | Shown in the flow as "coming later"; not built in v1. |

## 2. Stages, routes and gates

One pipeline; the route and options decide which stages run. ⏸ is a gate: the person
**Approves** or **Asks for changes** (with notes), and every decision is a commit.

| Stage | From scratch | From a document | Existing deck |
|---|---|---|---|
| **Intake** — title, audience, goal, rough length, brand variant, output | ✓ | ✓ + the document (upload, link, or paste) | ✓ + the deck (`.pptx` upload or Slides link) + change level |
| **Classify** | — | *Slide spec* or *source material*, shown for correction ⏸ | Deck inventory (`pptx inspect` / `google snapshot`) shown as slide pictures ⏸ |
| **Research plan** | ⏸ if research is on | ⏸ if source material and research is on | — |
| **Research** | ⏸ if research is on | ⏸ if source material and research is on | — |
| **Outline** — per slide: title, key message, notes | Drafted ⏸ | Material: drafted ⏸ · Spec: parsed, confirmed ⏸ | Full rework only: proposed restructure ⏸ |
| **Look** — one sample slide built 2–3 ways, rendered as pictures, pick one | ⏸ | ⏸ | Redesign, Full rework (skipped for Brand only, Polish, Selected changes) |
| **Build** — compose, render, brand audit, critique | ⏸ | ⏸ | ⏸ with before/after per slide |
| **Deliver** — Google Slides link and/or `.pptx`, recorded in the deck | ✓ | ✓ | ✓ always a new copy; the original is never changed |
| **Rehearse with Yoodli** | coming later | coming later | coming later |

Existing-deck change levels (harness-slides `references/intake.md`):

| Level | Plain-language card | Stages after Classify |
|---|---|---|
| Brand only | "Same slides in your brand's look: colors, fonts, logo, master layouts." | Build, Deliver |
| Polish | "Brand plus tidier layouts, spacing and overflow fixes. Words stay." | Build, Deliver |
| Redesign, keep content | "Rebuilt with your brand's layouts, icons and diagrams. Same message per slide." | Look, Build, Deliver |
| Full rework | "We may tighten, split, merge or reorder content, then redesign." | Outline, Look, Build, Deliver |
| Selected changes | "Tell us which slides and what to fix." | A *which slides / what* step at intake, then Build (only those slides), Deliver |

**Changes after delivery.** "Ask for changes" on a finished deck reopens Build with the
person's notes. It uses harness-slides' review/patch path, renders only the changed
slides again and delivers a new numbered revision; it does not start over.

**Brand.** The brands and variants are those the person's brand skill lists, chosen at
intake; the default is the one Settings names, else the first the brand skill lists. When
a deck first needs its brand, the runner runs the brand skill's `contract export` and
passes the contract to harness-slides with `--brand`.
The exported contract, `DESIGN.md` and `VOICE.md` are kept in the deck so a rerun uses the
same brand version.

## 3. Seeing the slides at each gate

Slides are the product, so every gate after Classify shows real slide pictures — the same
viewer Training Studio's deck gate uses: harness-slides `compose preview` renders each slide
to a PNG (through LibreOffice on this computer, or a single "Preview: …" presentation in the
person's Google Drive — chosen in Settings, as in Training Studio), and the page fetches each
picture as bytes and shows it in a slide-by-slide pager.

- **Classify (existing deck):** the original slides as pictures, with what the inventory found.
- **Look:** the 2–3 sample directions side by side as rendered slides; click one to choose it.
- **Build:** the full pager plus the contact sheet; per-slide brand-audit and critique notes;
  per-slide "Ask for changes". Existing decks show original and redesigned versions side by side.
- **After a change request:** only the changed slides are rendered again; the pager marks them.
- **Outline and Research** are text gates (editable outline: reorder, add, remove slides).

Pictures are local work and not shared (§4); a teammate sees the committed contact sheet.

## 4. Workspace layout and sharing

The workspace is a folder in a git repository, as in Training Studio (`runner/gitstate.py`
with `FOLDER = 'presentations'`, `TOOL = 'presentation-studio'`). It is either the team
repository — shared with Training Studio's `trainings/` and Blog Studio's `blogs/` — or a
folder on this computer only. The runner works in its own clone under its per-user data
folder and only ever reads and writes under `presentations/`.

```
<team-repo>/presentations/
  hub.json                     # {schema, tool: "presentation-studio"}
  README.md                    # index of decks
  .gitignore                   # work/, sources/, locks, harness guidance caches
  <deck-id>/
    README.md                  # title, route, state, Slides link, who drives it
    run.json                   # route, options, stage, gate state, driver claim, revisions
    intake.md
    classify.md                # spec/material verdict, or deck inventory + source name and sha256
    research/plan.md
    research/report.md
    outline.json               # the outline as harness-slides reads it
    outline.md
    look.json  look.md         # the looks proposed and the chosen direction
    brand/                     # brand-contract.json, DESIGN.md, VOICE.md, brand version
    reviews/build-<n>.md       # what the review of each build round found
    deliver.json               # Slides file ID and URL, pptx name, revision number
    contact-sheet.png          # one small picture of the deck for teammates
    sources/                   # never shared: uploaded documents and the original deck
    work/                      # never shared: harness-slides workspace, the build plan and
                               #   each section's drawing (work/build/), previews, renders, .pptx
```

Team rules are Training Studio's (`docs/runner.md`, "With a team"):

- One computer drives a deck at a time. Starting a deck claims it, and the claim is pushed
  before any work. Teammates' decks are read-only under "Run by your teammates", with
  **Take over**; the driver can **Hand over**. A finished deck has no driver.
- Each decision is a commit. Sharing happens after each decision (default) or when the person
  presses "Share now". Pushes are never forced.
- A clash sets this computer's unshared commits aside under a ref and carries on from the
  shared version; the page says what was kept and where.
- **Publish** marks a deck as its next numbered revision in place.
- Unreachable repository: work is kept and labeled "not shared yet", and goes with the next share.

## 5. Page

Same look and patterns as Training Studio: `style.css` and `markdown.js` vendored and pinned
by revision, as Blog Studio does in `training-studio-ui.json`.

**First launch.**
1. *Check this computer*: Claude Code or Codex CLI, Node 20+, git, harness-slides,
   harness-research, a brand skill, LibreOffice, Poppler, Arial, Google sign-in. Each missing
   item says one sentence and, where the installer can, has a **Fix it** button.
2. *Workspace*: "Join our team repository" (address → `presentations/` added beside
   whatever is there) or "Just this computer".
3. *Defaults*: assistant and model, your name, brand and variant (from your brand skill), output (Google Slides),
   preview renderer, share after each decision or when asked, time and cost limit per step.

**Home**: Needs you · In progress · Finished (Slides link + contact-sheet thumbnail) · Run by
your teammates.

**New deck**: three route cards — *Start from scratch*, *Start from a document*, *Redesign an
existing deck* — each opening a two- or three-step form with only that route's intake fields.

**Deck screen**: a stage timeline (done ✓ / current / upcoming; Yoodli dimmed as "coming
later") and the current gate (§3). Controls: Approve, Ask for changes, Pause, Stop, Undo the
last step.

**Other screens** (kept from Training Studio): Decks (searchable), Published, Status (runs,
costs, problems), Settings, Versions/upgrade.

## 6. Architecture

Fork-and-trim of Training Studio. Python 3.11+, standard library only; vanilla JS page; no
build step.

```
presentation-studio/
  runner/                      # forked from training-studio/runner
    studio.py page.py setup.py settings.py upkeep.py      # kept, renamed strings
    gitstate.py team.py                                   # kept; FOLDER/TOOL changed
    agents.py worker_tools.py claude-code-models.json     # kept
    slides.py brand.py research.py documents.py companion.py   # kept; slides.py gains pptx/google intake calls
    engine.py                  # trimmed to decks
    stages.py                  # replaces pipeline.py: §2 table + skip map per route/level
    briefs/                    # worker prompts: classify, outline-from-material,
                               # outline-from-spec, restructure, look, change-request
  skills/presentation-studio/  # SKILL.md for chat use, references/, scripts/desk (page assets)
  installer/                   # install.sh, .command, companions.json
  guidance/manifest.json  VERSION  vendor.json  tests/  docs/
```

- **Dropped from the fork:** training levels, scenarios, learner guide, Yoodli builder,
  Word copies (`copies.py`), and anything else only a training uses.
- **`vendor.json`** records, for each module taken from Training Studio, the revision it came
  from, so drift is visible until a shared core exists.
- **Agents.** As in Training Studio: the person's own `claude` or `codex` CLI as a subprocess,
  a stripped environment, no built-in tools, only the runner's MCP worker tools (plus web
  search for research jobs), no session persistence. Agents propose; only a decision on the
  page approves.
- **Slides work** is done only through the harness-slides CLI — `outline check/draft`,
  `compose compile/preview/render/critique/sheet`, `google compile`, `pptx inspect/patch/compare`,
  `workspace init --source`, `review`. The studio never edits slide files itself.
- **Documents** (Word, PDF, Google Docs, Markdown, pasted text) are read into text by the
  forked `documents.py`; the classify worker decides spec vs material.
- **Companions.** `installer/companions.json` pins harness-slides and harness-research
  (repository, version, commit, sha256), as Training Studio pins them. The installer and
  "Check this computer" install or upgrade them.
- **The brand skill** is the person's own. Settings names its repository and release; the
  Versions view installs or upgrades it with its own installer (Training Studio's
  `brand_source`), leaving the pinned companions alone.
- **Launch.** `~/.local/share/presentation-studio/studio` or `Open Presentation Studio.command`;
  binds 127.0.0.1 on a random port; the printed URL carries a key after `#`; one runner per
  computer.

## 7. Errors

- Every failure is one plain sentence on the page; details go to Status.
- A failed step offers **Try again** or **Carry on** where carrying on is safe.
- No Google sign-in: the deck is made as `.pptx` and the page says so.
- No Arial, LibreOffice or Poppler: Build is blocked with what to install; Drive previews
  are offered when signed in to Google.
- Repository unreachable: work kept locally, labeled "not shared yet".
- An existing deck that harness-slides cannot read: refused at Classify with the tool's reason.
- A document that cannot be read into text: refused at intake with the reason.

## 8. Testing

- `unittest` with fake adapters, as in Training Studio: no test starts an agent, calls
  Google, renders, or runs harness-slides.
- One end-to-end test per route (and per existing-deck level) through every gate, with a
  stub slides tool that records the commands it was given.
- `stages.py` skip map tested as a table.
- Claim, take over, hand over and clash tests adapted from Training Studio's.
- Manual acceptance walkthrough per route against the real harness-slides and a real brand skill,
  recorded in `docs/`.

## 9. Not in v1

- Rehearse with Yoodli (shown as "coming later").
- Bringing hand edits made in Google Slides back into the outline.
- A shared studio core used by all three studios (separate project, after Blog Studio adopts
  the shared sync — blog-studio#93).
- Reusing a teammate's deck as a starting point (beyond Take over).
