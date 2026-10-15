---
name: presentation-studio
description: Make a slide deck in your organisation's brand from an idea, a document or an existing deck, one approved step at a time, with harness-slides, harness-research and your brand skill. Use to start, resume, check or revise a deck kept under presentations/.
---

# Presentation Studio

This entry finds the guidance for making a deck in this conversation. Guidance is kept up to date separately from the installed scripts, and each deck stays on the guidance it started with.

1. From the directory the harness was launched in, run this command, which the installer wrote:

   ```sh
   ~/.local/share/presentation-studio/presentation guidance start
   ```

2. It prints JSON. If there is an `error`, show it and stop; do not improvise guidance. If there is a `notice`, tell the user once.
3. Read the file named by `entry` and follow it. Its links are relative to that file. `helper` is a command: wherever guidance says to run the helper, run `helper` itself, as in `"<helper>" status`. Never put `python3` before it.

Only when the user asks to move a deck to newer guidance: run the same command with `update` in place of `start`.
