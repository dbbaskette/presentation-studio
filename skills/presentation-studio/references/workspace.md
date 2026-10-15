# The workspace

Decks live in a `presentations/` folder: in the team's shared repository, beside Training Studio's `trainings/` and Blog Studio's `blogs/`, or in a folder on this computer. `presentations/hub.json` says `{"schema": 1, "tool": "presentation-studio"}`. If there is no such folder, ask where decks are kept before making one. The team repository is `team.repository` in the shared values.

## A deck's folder

`presentations/<deck-id>/`, the id being the title in lower case with hyphens, numbered when that is taken.

```
README.md          title, route, where it stands, the delivered link
run.json           the run record; what marks the folder as a deck
intake.md          the form, in words
classify.md        a document's kind, or an existing deck's inventory
research/plan.md   research/report.md
outline.md         each slide's title, key message and notes
look.json          the chosen look
plan/              harness-slides' outline, composition and plan files
brand/             brand-contract.json, DESIGN.md, VOICE.md
reviews/<step>-<n>.md   each request for changes and what was done
deliver.json       the Google Slides link or the .pptx name, and the revision
contact-sheet.png  one small picture of the deck
sources/           never shared: documents and the original deck
work/              never shared: harness-slides' workspace, previews and renders
```

`run.json` holds `schema` (1), `id`, `title`, `route`, `form` (`route`, `title`, `audience`, `goal`, `minutes`, `brand`, `variant`, `output`, `research`, and for an existing deck `level`, with `selected` for that level) and `gates`. Record each stop under `gates` by its step, such as `gate:outline`: `{"state": "approved"}` or `{"state": "changes", "note": "<their words>"}`, with `at` and `by` from `person.name`. Keep the brand contract a deck was built with, so that a rerun uses the same brand.

## What is never shared

`*/sources/`, `*/work/`, lock files, and the guidance caches harness-research and harness-slides keep. `presentations/.gitignore` lists them; keep it so.

## With a team

- **One computer drives a deck at a time.** A deck whose `run.json` names a driver other than this computer is someone else's: read it, do not change it.
- **Each decision is a commit**, saying what was decided. Share it when the person asks, or after each decision when `share` in the shared values is `decision`. Never force a push. If the shared version moved on, stop and say so.
- **The runner.** Keep `run.json` in the shape above: the runner can bring a deck made here into its workspace and carry on from what it says. A deck the runner drives is never also driven from a conversation.
