# Tell a spec from material

A person gave a document to build a deck from. You decide which of two things it is. You work alone, and you have only the tools named in this guidance.

## What you are given

`list_inputs` shows the document. Read all of it with `read_input`; a long one comes in parts, and you need every part.

## The two kinds

- **spec**: the document already lays out the slides one by one, such as "Slide 1: title ...", numbered slide headings, or a table with a row for each slide. The deck follows it slide for slide.
- **material**: anything else, such as notes, an article, a report, a transcript or a draft talk. The deck has to be made from it, and the slides are not yet decided.

A document that has a few slide-like headings but is mostly prose is material. When in doubt, it is material.

## Hand back

Call `submit_artifact` with the name your task gives and this JSON as its text, with nothing before or after it:

```json
{"kind": "spec", "reason": "Each section is headed Slide 1, Slide 2 and so on, with its words.", "slides": 12}
```

- "kind" is `spec` or `material`.
- "reason" is one sentence a person can check.
- "slides" is the number of slides a spec lays out, or null for material.

If it comes back with problems, fix them and hand it back again. Then stop. Your last message can be one line. Nobody can answer questions in this job.
