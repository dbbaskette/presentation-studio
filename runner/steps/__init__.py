"""The steps a deck goes through, one module per family of stages. Each is called by the
engine and holds no state of its own.

    intake     taking in a document or a Google Doc, and telling a spec from material
    outline    writing, extracting and restructuring the outline
    existing   bringing in a deck that exists, and making selected changes to it
    look       the looks a worker proposes, their pictures and the person's choice
    build      the brand, the sections and their composers, the review, the render
    deliver    delivering the deck, and asking for changes once it is delivered

Every step that sets up a worker's job returns a `Work`: what the worker is told (`guidance`
and `task`), the profile it runs under, what `worker_tools.prepare(folder, **prepared)` takes
to set its folder up, and the name it hands its draft back under.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Work:
    """One job for a worker: what it is told, and what its tools are set up with."""
    guidance: str
    task: str
    profile: str
    prepared: dict      # what worker_tools.prepare takes
    name: str = ''      # the name a draft is handed back under

