"""On-span construction: fine (hit-set) and coarse (on/off) runs."""

from __future__ import annotations

from .bands import slots_for_hits
from .types import Hit, Run, Sample


def hit_key(sample: Sample) -> tuple[str, ...]:
    """Stable identity of which subjects a sample touches."""
    return tuple(hit.id for hit in sample.hits)


def fine_runs(samples: list[Sample]) -> list[Run]:
    """Split on-regions whenever the hit-set changes.

    Carpet-only then slippers+carpet then carpet-only becomes three spans, so
    each can pick a different depth band.
    """
    runs: list[Run] = []
    start: int | None = None
    key: tuple[str, ...] | None = None
    for index, sample in enumerate(samples):
        if not sample.on:
            if start is not None:
                runs.append(make_hitset_run(samples, start, index - 1))
                start = None
                key = None
            continue
        current = hit_key(sample)
        if start is None:
            start = index
            key = current
            continue
        if current != key:
            runs.append(make_hitset_run(samples, start, index - 1))
            start = index
            key = current
    if start is not None:
        runs.append(make_hitset_run(samples, start, len(samples) - 1))
    return runs


def make_hitset_run(samples: list[Sample], start: int, end: int) -> Run:
    # Every sample in the span shares the same hit-set; slots come from that set only.
    return Run(start, end, tuple(slots_for_hits(list(samples[start].hits))))


def coarse_runs(samples: list[Sample]) -> list[Run]:
    """One span per continuous on-region; slots use the union of all hits in it."""
    runs: list[Run] = []
    start: int | None = None
    for index, sample in enumerate(samples):
        if not sample.on:
            if start is not None:
                runs.append(make_union_run(samples, start, index - 1))
                start = None
            continue
        if start is None:
            start = index
    if start is not None:
        runs.append(make_union_run(samples, start, len(samples) - 1))
    return runs


def make_union_run(samples: list[Sample], start: int, end: int) -> Run:
    hits_by_id: dict[str, Hit] = {}
    for sample in samples[start : end + 1]:
        for hit in sample.hits:
            hits_by_id[hit.id] = hit
    hits = sorted(hits_by_id.values(), key=lambda hit: (hit.depth, hit.id))
    return Run(start, end, tuple(slots_for_hits(hits)))


def on_off_sequences(samples: list[Sample]) -> list[dict]:
    if not samples:
        return []
    runs = []
    start = 0
    for index in range(1, len(samples) + 1):
        if index == len(samples) or samples[index].on != samples[start].on:
            runs.append({"start": start, "end": index - 1, "on": samples[start].on})
            start = index
    return runs
