# Reviewing stops: deciding item by item

Date: 2026-10-15. Status: built.

## Why

The research plan, research findings and outline stops show a document and ask for one
decision on all of it. In a real run the research findings stop showed a report of 11,580
words for 16 questions, 7 of them not settled, and the outline 15 slides in about 2,000
words. A person cannot judge that much before approving, and the only way to object is one
free-text note for the whole thing, so in practice everything is approved.

Underneath, the work is already itemised: the plan has one entry per question, harness-
research keeps one finding per question (status, summary, limits, quoted sources), and the
outline has one entry per slide. The runner can already research named questions again.
The page uses none of that.

This design shows each of the three stops as a list of items the person can mark one by
one, with what most needs them first, and one button that says what it will do.

Two other findings of the same audit are separate pieces of work, each to get its own
design: showing the rounds of the build as they happen, and making "no team repository" a
first-class choice in set-up.

## The shared pattern

Every reviewed stop is drawn the same way.

1. **A count strip first.** Two to four counts, such as "16 questions · 9 answered · 7 not
   settled". No document above it.
2. **What needs the person first.** Items likely to need a decision are cards, with their
   actions on them. The rest are one-line rows that open into the same card on a click.
3. **Marks, not notes.** The person marks items as they go: drop, reword, research again,
   leave out, change this slide. Nothing is sent until they press the decision button.
   Marks are kept for the deck, the stop and its round, as the page keeps the outline's
   edits now (`chosenFor`), so a refresh loses nothing.
4. **One decision button that says what it will do,** at the foot of the list and mirrored
   by the toolbar's main button:
   - no marks: **Approve**;
   - only marks that need no assistant: **Approve without 2 questions** (or **Approve,
     leaving out 1 finding**): one click applies them and approves;
   - any mark that needs an assistant: **Send 3 changes**: the stop is reopened and comes
     back to the person.
   A line beside it tallies the marks: "1 to research again · 1 left out · 0 added".
5. **The full text one click away.** "Read the full plan" or "Read the full report" opens
   the document as it is shown now, folded by default.
6. **Free text stays.** The toolbar's "Ask for changes" still opens the note sheet, for what
   is not about one item. A note and marks can be sent together.

Approve acts at once, as it does since the one-click change: no second question.

## The research plan stop

- One row per question: a short title made from its ID (`licensing-cost` reads "Licensing
  cost"), the question beneath it, and its search words in small type.
- Per question: **Drop**, or **Reword**, which opens a box holding the question to edit.
  Under the list: **Add a question**, a box and a button.
- **Drops** need no assistant. They go with Approve as `{"dropped": [ids]}`: the runner
  removes those items from `research/plan.json` and `research/plan.md`, then approves. It
  refuses, in a sentence, a plan left with no question.
- **Rewording and adding** go back to the planner. They are sent as changes,
  `{"dropped": [...], "reword": {id: text}, "add": [text]}`. The runner applies the drops
  first, then writes the note the planner reads from the marks, one line each ("Reword
  `licensing-cost` as: …", "Add a question: …"), followed by any free text. The planner
  keeps questions neutral and writes their search words, and the plan stops again.

## The research findings stop

- **Headline.** The worker researching a question also hands back a headline: the answer in
  one sentence of at most 25 words. It is kept with the finding in harness-research's own
  record, which takes a `headline` from 0.8.1 (its design:
  `~/projects/harness-research-skill/docs/superpowers/specs/2026-10-15-keep-findings-and-headlines-design.md`).
  A finding with no headline (made before this change) shows its summary's first sentence.
- **Cards.** A finding whose status is not `supported` (`insufficient`, `unavailable`,
  `contradicted`, or `pending` when no worker could answer it) is a card, under "Look at
  these first", with its status in its own words ("Not settled", "Not found",
  "Contradicted", "Not answered"): its title, its headline, "Not known:" with the first
  sentence of its limits (left out when the limits are "none"), and **N sources**. A
  supported finding is a one-line row, under "Answered", that opens into the same card.
- **Per finding:** **Research again** opens a line for what was wrong; **Leave out** greys
  the item and keeps it out of what the outline is drafted from; **N sources** opens the
  quoted passages, each with its source's title and, where it has one, its address as a
  link that opens in a new tab.
- **Under the list:** **Add a question**.
- **Leave-outs go with Approve** as `{"left_out": [ids]}`. The runner records them on the run
  (`research.left_out`), writes `research/report.md` again without them and with a "Left out
  by you" list of their titles, and approves. The outline worker reads that report, so the
  outline is drafted without them. The report is written from each question's data (title,
  status, headline, summary, what is not known, quoted passages) rather than by cutting
  sections out of harness-research's own report.
- **Research again and Add a question are changes,** `{"left_out": [...], "again": {id:
  line}, "add": [text]}`. The runner records the leave-outs, adds each new question to the
  plan as typed (with no search words), and reopens the research for the named and new
  questions only, as it does now for IDs named in a note. Each worker researching again is
  given the person's line for its question. The stop comes back when they are done.
- Adding a question changes the plan, and harness-research starts a new run for a changed
  plan. From 0.8.1 that run keeps the findings of every unchanged question (when the topic,
  scope and sources are unchanged), so only the new question is researched. Presentation
  Studio pins 0.8.1 for this.

## The outline stop

- **Compact rows.** One row per slide: its number and kind, its title (still editable), and
  what the audience must understand from it on one line. Its points and notes open on a
  click.
- **Edits as now.** Move, add and remove work as they do and go with Approve as `{"edited":
  [...]}`, checked by the slides tool first.
- **Ask for changes to this slide** on each row opens a line, as the build stop's per-slide
  marks do. Marked slides are sent as changes, `{"slides": {id: line}, "edited"?: [...]}`.
  Edits sent with them are checked and saved first; the runner then writes the note the
  outline worker reads, one line per slide naming its ID ("Slide `pricing-table`: …"),
  followed by any free text.

## What changes in the runner

- **`Engine.decide`** takes the marks above in `extra`, and a note is no longer needed for
  changes that carry marks. Each mark is checked before anything is written: an ID the stop
  does not have, an empty line for a slide or a rewording (a line to research again with
  may be empty), a plan left with no question, each is refused in one sentence and
  nothing moves. The page's server (`/api/decide`) applies the same rule about the note.
- **The note a worker reads** is written by the runner from the marks, then the person's
  free text. Workers' briefs need no change for marks.
- **The research views.** `_show_research_plan` gives each item's `id`, `title`, `question`
  and `public_query`. `_show_research` gives, besides the report's text, each
  item's `id`, `title`, `question`, `status`, `headline`, `summary`, `limits`, `unknown`
  (the first sentence of the limits), `left_out` and `sources` [{`title`, `origin`,
  `quote`}], read from harness-research's record. A path on this computer is never sent.
- **`submit_finding`** takes a `headline`, required, at most 25 words; one longer is
  refused with the count. The research-question brief says to give it. `Research.record`
  hands it to harness-research with the rest of the finding.
- **The research report** is written from each question's data, leaves out what the person
  left out, and lists their titles.
- **harness-research is pinned at 0.8.1,** and the tests' stand-in keeps unchanged findings
  across a plan change and takes a headline, as 0.8.1 does.

## What changes on the page

- One review component draws the count strip, the sections, the cards and rows, and the
  decision button with its tally, and holds the marks. The three panels are rebuilt on it;
  the outline keeps its add-a-slide form.
- The toolbar's main button mirrors the decision button: same words, same action.
- Words the person reads follow the house rules: no "artifact", "stale" or "lineage", and
  no brand named.

## Testing

- **Engine:** each mark applied or refused, with nothing written on a refusal; the note
  each worker reads, composed from marks and free text; left-out findings missing from
  `report.md` and listed under "Left out by you"; only the named and new questions
  researched again; a finding without a headline shown with its summary's first sentence.
- **Worker tools:** a finding without a headline, or with one over 25 words, refused with
  what to fix.
- **Server:** changes with marks and no note accepted; changes with neither refused.
- **Page harness:** marks on each stop become the right request and the right button
  words; a refresh keeps the marks; the full document is behind its fold; sources open.
- The whole suite once at the end.

## Not in this piece

- The build rounds view and local-only set-up (separate designs).
- The classify, brand and build stops, which already have short content or per-slide marks.
- Changing harness-research's record or its commands here: that is its own piece of work,
  in its own repository, released as 0.8.1 before this one.
