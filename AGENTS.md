# Presentation Studio working agreements

- **No deck content here.** Tests use temporary directories. Acceptance runs use disposable directories outside this repository.
- **Verification is proportional.** Work in coherent increments and run the targeted tests at each milestone. Run the whole suite once before calling work complete.
- **The helper has no dependencies.** Python 3.11 or newer, standard library only, no build step. Only guidance sync, `google`, `hub` and the page's check of this computer use the network, each at the user's request.
- **Tests never touch the real data folder.** They set `PRESENTATION_STUDIO_DATA` to a temporary directory (`tests/helpers.py` does it).
- **Guidance is harness-neutral.** It names no harness-specific tools, so it runs on Claude Code and Codex alike.
- **`main` is live.** Guidance that needs a script change raises `minimum_runtime` in `guidance/manifest.json` and the `VERSION` together.
- **Research and slides are delegated.** Do not add research or slide-building logic here; they belong to `harness-research` and `harness-slides`.
- **Ported files are recorded.** Every file taken from Training Studio is listed in `vendor.json` with the file it came from and the revision.
- **Person-facing sentences** never say "artifact", "stale" or "lineage".
