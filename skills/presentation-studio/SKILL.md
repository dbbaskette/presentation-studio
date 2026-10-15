---
name: presentation-studio
description: Make a slide deck in your organisation's brand from an idea, a document or an existing deck, one approved step at a time, with harness-slides, harness-research and your brand skill. Use to start, resume, check or revise a deck kept under presentations/.
---

# Presentation Studio

This guidance is for making a deck in a conversation. Most people use the page instead (`studio` opens it); both follow the same steps and stop at the same places.

## Rules that always hold

- **Only the person approves.** Each step ends at a stop: show what was made, then wait. Move on only when the person says they approve, in this conversation. Never approve for them, and never take silence or "looks fine so far" as approval of a later step. Record each decision as [the workspace](references/workspace.md) says.
- **Slides are made by harness-slides.** Draw, check, preview, render and patch slides only through its own commands, following its own guidance. Never write or edit a slide file yourself.
- **The brand is the person's brand skill.** Before the first step that needs the brand, export its contract into the deck's `brand/` folder with the brand skill's own `contract export` command, and give that contract to harness-slides with `--brand`. Presentation Studio names no brand: offer the brands and variants the brand skill lists.
- **Research is done by harness-research,** following its own guidance, and only when the person turned research on.
- **An original is never changed.** A deck being improved is read; the result is always a new file.
- **Stay inside the deck's folder** under `presentations/`. Never write anywhere else.

## Before you start

1. Check that harness-slides, harness-research and a brand skill are installed for this assistant. If one is missing, say which and stop: the person installs the companions with Presentation Studio's installer, and the brand skill from the page's Settings or by hand.
2. Read the shared values, read-only, from `~/.config/studios-config.json` (the `STUDIOS_CONFIG` variable names another file): `team.repository` and `share`, `person.name`, `brand.brand` and `brand.variant` as the brand offered first, and `output` (`google` or `pptx`). A file that is missing or cannot be read means no defaults; say so once. Never write it from a conversation.
3. Find or make the deck's folder, as [the workspace](references/workspace.md) says. If the page's runner drives that deck, do not work on it here.

## The steps

Ask how the person is starting and follow [the three routes](references/routes.md): from scratch, from a document, or from an existing deck. For an existing deck, they choose one of [the five levels](references/levels.md), which decides which steps run.

| Step | Stops for the person |
| --- | --- |
| Intake: title, audience, goal, length, brand and variant, output | They confirm the form |
| Classify: a document's kind, or an existing deck's slides | Yes, when there is a source |
| Research plan, then research | Each, when research is on |
| Outline: title, key message and notes for each slide | Yes |
| Look: one sample slide drawn two or three ways | They pick one |
| Build: the whole deck, its preview and its checks | Yes, or changes |
| Deliver: Google Slides or PowerPoint | No: say where it is |

"Ask for changes" at any stop means doing that step again with their words, then stopping again. A change to a delivered deck reopens Build for the slides named and delivers a new numbered revision.

## Checking where a deck stands

`run.json` in the deck's folder says which steps are done and which stop waits. Read it before you resume. When guidance start gave you a `helper`, `"<helper>" status` prints, as JSON, every deck the runner knows on this computer.
