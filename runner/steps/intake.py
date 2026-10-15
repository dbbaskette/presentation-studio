"""Taking in a document, and telling a spec from material.

What a caller needs to know
---------------------------
    entry = intake.take_document(root, source, drive=None)   # keep what the person gave
    work  = intake.classify_work(root, run, request, error)  # the classifier's job
    intake.keep_classification(root, run, handed)            # keep its verdict, open the gate
    run   = intake.correct(root, run, 'spec' | 'material')   # the person's correction

- `source` is the form's: {'kind': 'upload', 'name', 'data'}, {'kind': 'paste', 'text'} or
  {'kind': 'google', 'link'}. A Google Doc is fetched with `drive` (a gdrive.Drive by
  default), which needs the gcloud sign-in. A document that cannot be read is not kept: it
  is refused with the sentence that says why.
- The classifier hands back `classification`, a kind checked by `check_classification`
  and registered here: {"kind": "spec"|"material", "reason", "slides"}.
- `keep_classification` writes classify.md, sets run['classified'] and puts the gate in
  front of the person. `correct` is the person's word at that gate: the verdict changes,
  the research steps a material has and a spec has not are reset by name, everything after
  is redone, and the gate is approved. The document is never removed.
- Both write the run record, and change and return the run they are given.
"""
from __future__ import annotations

import json
from pathlib import Path

import runner  # noqa: F401  puts the core on the import path
import gdrive
from workspace import WorkspaceError, write_atomic

from runner import briefs, decks, documents, stages, worker_tools
from runner.steps import Work

KINDS = ('spec', 'material')
CORRECTED = {'spec': 'You said it is a spec.', 'material': 'You said it is material.'}
NAME = 'classification'
FILE = 'classify.md'
GATE = 'gate:classify'
RESEARCH_STEPS = ('research-plan', 'research', 'research-report')
RESEARCH_GATES = ('gate:research-plan', 'gate:research')


# --- the documents --------------------------------------------------------------------------

def take_document(root, source: dict, drive=None) -> dict:
    """Keep one document the person gave, and return its entry."""
    root = Path(root)
    kind = source.get('kind') if isinstance(source, dict) else None
    if kind == 'upload':
        entry = documents.add(root, source.get('name'), source.get('data'))
    elif kind == 'paste':
        entry = documents.add_text(root, 'Pasted text', source.get('text'))
    elif kind == 'google':
        ident = gdrive.file_id(source.get('link'))
        text = (drive or gdrive.Drive()).export_text(ident)
        entry = documents.add_text(root, 'Google Doc', text)
    else:
        raise WorkspaceError('Say where the document comes from: upload, paste or google.')
    if not entry['readable']:
        documents.remove(root, entry['name'])
        raise WorkspaceError(f'"{entry["name"]}" could not be read. {entry["problem"]}')
    return entry


# --- the classifier's job -------------------------------------------------------------------

def classify_work(root, run: dict, request: dict | None = None,
                  error: str | None = None) -> Work:
    """The job of reading the person's document and saying what it is."""
    root = Path(root)
    form = run.get('form') or {}
    inputs = {}
    for entry in documents.listed(root):
        if entry['readable']:
            inputs[entry.get('title') or entry['name']] = documents.text_of(root, entry)
    if not inputs:
        raise WorkspaceError('There is no document to read yet. Add one first.')
    lines = [f"Deck title: {run.get('title') or form.get('title') or 'not given'}",
             f"Audience: {form.get('audience') or 'not given'}",
             f"Goal: {form.get('goal') or 'not given'}",
             f'Hand your verdict back under the name "{NAME}".']
    if request and request.get('note'):
        lines.append(f"The person added:\n\n{request['note']}")
    if error:
        lines.append(f'An earlier try at this job did not work: {error}\n'
                     'Take care not to end the same way.')
    return Work(guidance=briefs.guidance('classify'), task='\n\n'.join(lines),
                profile='write', name=NAME,
                prepared={'inputs': inputs, 'artifacts': {NAME: {'kind': 'classify'}},
                          'ask': False})


def check_classification(text: str, spec: dict):
    """A verdict: {"kind", "reason", "slides"}. Returns problems, the checks that ran,
    warnings and the text to keep."""
    problems = []
    try:
        given = json.loads(text)
    except ValueError as failure:
        return [f'The classification is not valid JSON ({failure}).'], [], [], text
    if not isinstance(given, dict):
        return ['The classification is one JSON object with "kind", "reason" and "slides".'], \
            [], [], text
    kind, reason, slides = given.get('kind'), given.get('reason'), given.get('slides')
    if kind not in KINDS:
        problems.append('"kind" must be "spec" or "material".')
    if not isinstance(reason, str) or not reason.strip():
        problems.append('"reason" must be a sentence saying why.')
    if kind == 'spec':
        if isinstance(slides, bool) or not isinstance(slides, int) or slides < 1:
            problems.append('A spec needs "slides", the number of slides it lays out.')
    elif slides is not None:
        problems.append('"slides" is null unless the document is a spec.')
    outcome = worker_tools.result('classify.verdict', problems)
    return problems, [outcome], [], text


worker_tools.register('classify', check_classification)


# --- the verdict ----------------------------------------------------------------------------

def _write_note(root, kind: str, reason: str, slides, corrected: bool) -> None:
    lines = ['# What your document is', '',
             f'Verdict: {kind}' + (' (Corrected by you)' if corrected else ''),
             f'Reason: {reason}']
    if kind == 'spec' and slides:
        lines.append(f'Slides: {slides}')
    write_atomic(Path(root) / FILE, '\n'.join(lines) + '\n')


def keep_classification(root, run: dict, handed) -> dict:
    """Keep the classifier's verdict and put it in front of the person."""
    if isinstance(handed, str):
        handed = json.loads(handed)
    kind, slides = handed['kind'], handed.get('slides')
    _write_note(root, kind, handed['reason'], slides, corrected=False)
    run['classified'] = kind
    gate = (run.setdefault('gates', {})).get(GATE) or {}
    run['gates'][GATE] = {'state': 'waiting', 'round': int(gate.get('round') or 0) + 1}
    decks.write_run(root, run)
    return run


def correct(root, run: dict, kind: str) -> dict:
    """The person's correction at the gate. Returns the updated run."""
    if kind not in KINDS:
        raise WorkspaceError('A document is a spec or material.')
    run['classified'] = kind
    # The research steps come and go with the verdict, so they are reset by name: reopen
    # only walks the steps the deck has now.
    for name in RESEARCH_STEPS:
        run.setdefault('steps', {})[name] = {**run['steps'].get(name, {}), 'done': False}
    for name in RESEARCH_GATES:
        run.setdefault('gates', {})[name] = {**run['gates'].get(name, {}), 'state': 'absent'}
    feeder = stages.feeder(run, GATE)
    kept = dict(run['steps'].get(feeder, {}))
    run = stages.reopen(run, GATE)
    if feeder in run['steps']:      # the person's word is the verdict: it is not asked again
        run['steps'][feeder] = kept
    run['gates'][GATE] = {**run['gates'].get(GATE, {}), 'state': 'approved'}
    _write_note(root, kind, CORRECTED[kind], None, corrected=True)
    decks.write_run(root, run)
    return run
