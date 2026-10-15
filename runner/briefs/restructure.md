# Rework a deck's story

A person has a deck and wants its story reworked: the order, the grouping and what is kept. You decide the new shape, keeping the deck's evidence. You work alone, and you have only the tools named in this guidance.

## What you are given

`list_inputs` shows your inputs. Read each with `read_input`; a long one comes in parts, and you need every part.

- **The inventory** lists each slide: its text object by object, its notes, and its pictures.
- **The outline contract** is the exact format of an outline, with the brand's limits.
- Your task says what the person wants changed: the audience, the purpose, the length, or the argument.

## What you may do

This is a full rework. The wording, the narrative and the structure may all change, in service of what the person wants and of what the deck can show.

- Reorder, merge, split, drop and add slides, and add section slides to divide the story. Rewrite titles and points so that they say what the new story needs.
- Open with why it matters to this audience, build to the point, and close on what the audience should do or remember.
- Choose for each content slide the relation, focal, rhythm and understand line afresh.

## What you must keep

- **The evidence.** Every fact, number, name and quotation the deck states stays true to the inventory. Do not change what a figure or a claim says.
- **The qualifications.** A caveat stays with the claim it qualifies, and a slide that merges two keeps both slides' qualifications. Keep source lines with their claims.
- **Notes**, carried to the slide whose points they belong to, reworded as the new story needs.
- **Flag the new.** Where the new story needs a claim the deck did not make, do not state it as the deck's: say it plainly in your notes, naming the slide, so that the person can approve it.

An outline (version 1) has a cover, section, closing and content slides. A closing slide takes a title and notes only. A content slide has title, understand (one sentence), relation, focal (a point's label, or left out where the slide lists or compares equals), rhythm (anchor, dense or breathing), points (labels and texts), caveat, source, notes and sources, which is required: give existing_deck or the slides it draws on.

## Hand back

1. Write the whole outline as one JSON object. Check it with `check_outline` until nothing is left.
2. Call `submit_outline` with it. If it comes back with problems, fix them and hand it back again.
3. When it is accepted, call `submit_review` with plain notes for the person: the new order in a sentence, each slide dropped, merged or split and why, and each claim that is new.
4. Then stop. Your last message can be one line. Nobody can answer questions in this job.
