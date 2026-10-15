# The three routes

Every route starts at intake and ends at delivery. Write the person's answers to `intake.md` and the form in `run.json`, then confirm them before anything else. Research is offered for the first two routes only, and is off unless the person turns it on.

## From scratch

The person has an idea and writes a short brief: the title, who it is for, what it should achieve and roughly how long it runs.

1. **Research plan and research**, only when research is on. Draft the questions in `research/plan.md` and stop. Once approved, run them with harness-research and write `research/report.md`. Stop again.
2. **Outline.** Draft `outline.md` from the brief and the research: for each slide a title, its key message and speaker notes. Check it with harness-slides' outline check against the brand contract. Stop. The person may reorder, add and remove slides.
3. **Look.** Draw the first content slide two or three different ways with harness-slides and preview each as a picture. Stop: the person picks one. Keep the choice in `look.json`.
4. **Build.** Compose and compile the whole deck with harness-slides, preview it, and run the brand skill's audit and harness-slides' critique. Show the pictures, the contact sheet and the findings. Stop.
5. **Deliver.** Render the approved deck and deliver it as Google Slides, or as PowerPoint when that was chosen or Google cannot be reached. Write `deliver.json`.

## From a document

The document is Markdown or text, Word, PDF, a Google Doc or pasted text. Keep it in `sources/`, which is never shared.

1. **Classify.** Decide whether it is a *spec*, which already lays out the slides one by one, or *material*, which has to be turned into slides. When in doubt it is material. Write the verdict and why in `classify.md` and stop: the person may correct it.
2. **A spec** becomes the outline slide for slide, keeping its words. Show it and stop.
3. **Material** may be researched further, when research is on, as from scratch. The outline is then drafted from it.
4. Look, Build and Deliver follow, as from scratch.

## From an existing deck

The deck is a `.pptx` file or a Google Slides link. Keep a copy in `sources/`; the original is never changed.

1. **Classify.** List every slide with harness-slides' inventory, and show the slides as pictures with what was found. Write `classify.md` with the deck's name and its SHA-256. Stop.
2. The person's [level](levels.md) decides what follows: some levels skip the outline or the look.
3. **Build** shows each slide before and after. **Deliver** is always a new copy.
