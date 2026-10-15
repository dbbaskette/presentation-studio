# Presentation Studio

Presentation Studio makes Tanzu-branded slide decks. You give it an idea, a document or a deck you already have, and it builds the deck with you one step at a time. Nothing moves forward until you approve it, and at each stop you see the real slides, not a description of them.

The work is done by an AI assistant you already have, Claude Code or Codex. Presentation Studio guides it, checks what it makes, and keeps track of what you have approved. The assistant never touches your files or runs commands on its own; only you approve.

It is the third studio beside [Training Studio](https://github.com/dbbaskette/training-studio) and [Blog Studio](https://github.com/dbbaskette/blog-studio), and made for Tanzu colleagues, technical or not.

## Three ways in

| You have | Choose | What happens |
| --- | --- | --- |
| An idea | **Start from scratch** | You write a short brief. Research is optional and off unless you turn it on. |
| A document | **Start from a document** | A Markdown or text file, a Word file, a PDF, a Google Doc or pasted text. The studio says whether it thinks the document lays out the slides or is material to turn into slides. You can correct it. |
| A deck | **Redesign an existing deck** | A `.pptx` file or a Google Slides link. You choose how much may change (below). Your original is never changed; you always get a new copy. |

Redesigns come in five levels:

- **Brand only**: same slides, Tanzu look.
- **Polish**: brand plus tidier layouts and spacing. The words stay.
- **Redesign, keep content**: rebuilt with Tanzu layouts, icons and diagrams. Same message on each slide.
- **Full rework**: may tighten, split, merge or reorder the content, then redesign it.
- **Selected changes**: you say which slides and what to fix.

## What you do at each step

The page stops at each of these and waits for you. Which ones apply depends on how you started.

1. **Check what you brought** (documents and existing decks). You see the verdict, or the original slides as pictures.
2. **Research plan and research** (only if you turned research on).
3. **Outline.** A title, key message and notes for each slide. You can reorder, add and remove slides.
4. **Look.** One sample slide drawn two or three ways. You pick the one you like.
5. **Build.** The whole deck in a slide viewer, plus a contact sheet and notes from the brand check. Redesigns show before and after. Each slide has its own **Ask for changes**.
6. **Deliver.** A Google Slides deck by default, or a PowerPoint file.

**Rehearse with Yoodli** is shown on the page as coming later.

Brand defaults to Tanzu. VMware (light or dark) and Broadcom are available when you start a deck.

## Before you start

You need:

- **A Mac.**
- **Claude Code or Codex**, installed and signed in.
- **Python 3.11 or newer**, **Node 20 or newer** and **git**.
- **Arial**, which the brand uses.
- **A way to see slides**: LibreOffice and Poppler on this computer, or Google Drive previews if you sign in to Google.
- **Google sign-in** (gcloud), only if you want Google Slides as the output or a Google Doc as the input. Without it you get a PowerPoint file.
- **Three companion skills**: [harness-slides](https://github.com/dbbaskette/harness-slides-skill) builds the decks, [harness-research](https://github.com/dbbaskette/harness-research-skill) does the research, and tanzu-brand holds the Tanzu, VMware and Broadcom brands. The installer brings all three at the versions it was tested with.

The page checks this computer the first time you open it and says in one sentence what is missing.

## Install

Download Presentation Studio and run its installer:

```bash
git clone https://github.com/dbbaskette/presentation-studio.git
cd presentation-studio
sh installer/install.sh
```

Or double-click `Install Presentation Studio.command` in the `installer` folder.

The installer says what it is about to do and asks before changing anything. It adds Presentation Studio to Claude Code and Codex, whichever you have, then offers the companion skills.

## Your first deck

**1. Open Presentation Studio.** Double-click "Open Presentation Studio" in the Applications folder inside your home folder, or run:

```bash
sh ~/.local/share/presentation-studio/studio
```

A terminal window opens and the page opens in your browser. It works on this computer only. Leave the window open while you work.

**2. Set it up, once.** Say where decks are kept: a folder on this computer to try things out, or your team's shared repository. Then choose your assistant, your name, the brand and where decks are delivered. If you already use Training Studio or Blog Studio, the answers they share are filled in for you (see [shared settings](#shared-settings)).

**3. Press "New deck"** and choose how you are starting. Fill in the short form. It begins at once.

**4. Decide at each stop.** The page shows what needs you. Approve, or ask for changes in your own words. You can close the page while it works and come back later.

**5. Collect your deck.** When it is done, the page shows the Google Slides link or the PowerPoint file. Ask for changes on a finished deck and only the slides that changed are rebuilt, delivered as a new numbered revision.

### In a conversation instead

If you are comfortable in a terminal, open your assistant and ask for `/presentation-studio` instead of using the page. It follows the same steps and waits for you at the same stops.

## Working with a team

Keep your decks in your team's shared repository. They go in a `presentations/` folder, beside Training Studio's `trainings/` and Blog Studio's `blogs/`.

- One computer runs a deck at a time. Teammates' decks are read-only, and you can **take over** one or **hand over** your own.
- Every decision you make is saved as a commit.
- Google Slides links are saved with the deck.
- Uploaded files and slide pictures stay on your computer. Teammates see a small contact sheet.

[The runner](docs/runner.md) has the details, including what happens when two computers disagree.

## Shared settings

`~/.config/studios-config.json` holds the choices common to every studio: your team repository, your name, your assistant and model, brand and output. Setup fills the page from it, so you answer each question once.

## If something goes wrong

| What you see | What it means |
| --- | --- |
| The page says it needs LibreOffice or Poppler | Slides cannot be drawn on this computer. Install them, or sign in to Google and use Drive previews |
| You get a PowerPoint file, not Google Slides | You are not signed in to Google. Sign in with gcloud and deliver again |
| A step failed | The page says why in one sentence. Choose Try again, or Carry on if offered |
| Your team repository cannot be reached | Your work is kept and marked "not shared yet". It goes up with the next share |
| A deck cannot be read | The page gives the reason when you add it. Try saving it as `.pptx` again |
| The page does not open | Open the link exactly as the terminal printed it, and keep that window open. The part after `#` is a key |

## Learn more

- [The runner](docs/runner.md): how the page and runner work, and working as a team.
- [Development](docs/development.md): the repository, running the tests, and how to change Presentation Studio.
- [Acceptance](docs/acceptance.md): what has been tried by hand.
- [Design](docs/superpowers/specs/2026-10-14-presentation-studio-design.md): the full specification.

## Licence

[MIT](LICENSE).
