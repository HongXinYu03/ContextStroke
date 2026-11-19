"""On-span construction.

Fine spans keep hit-set cuts. A subject participates in a span when it is in
that span's hits, or when a contiguous endpoint was opened by that subject
entering on top of a shared deeper hit. The span may then sit only in front
of or behind its front-most participant. Spans the front subject does not
touch keep the rear subjects that actually cut them.

Coarse spans ignore those front overlays and follow the deepest hit at each
sample, so sofa and carpet stay one rear envelope without a separate
front-subject cut.
"""

from __future__ import annotations

from .bands import slots_around_hits
from .types import Hit, Run, Sample


def hit_key(sample: Sample) -> tuple[str, ...]:
    """Stable identity of which subjects a sample touches."""
    return tuple(hit.id for hit in sample.hits)


def fine_runs(samples: list[Sample]) -> list[Run]:
    """Hit-set spans whose bands follow the front-most subject that participates."""
    raw = _raw_hitset_spans(samples)
    if not raw:
        return []
    runs: list[Run] = []
    for chain in _contiguous_span_chains(raw):
        runs.extend(_participant_runs(samples, chain))
    return runs


def _raw_hitset_spans(samples: list[Sample]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    key: tuple[str, ...] | None = None
    for index, sample in enumerate(samples):
        if not sample.on:
            if start is not None:
                spans.append((start, index - 1))
                start = None
                key = None
            continue
        current = hit_key(sample)
        if start is None:
            start = index
            key = current
            continue
        if current != key:
            spans.append((start, index - 1))
            start = index
            key = current
    if start is not None:
        spans.append((start, len(samples) - 1))
    return spans


def _contiguous_span_chains(spans: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    chains: list[list[tuple[int, int]]] = [[spans[0]]]
    for span in spans[1:]:
        if chains[-1][-1][1] + 1 == span[0]:
            chains[-1].append(span)
        else:
            chains.append([span])
    return chains


def _participant_runs(samples: list[Sample], chain: list[tuple[int, int]]) -> list[Run]:
    span_hits = [list(samples[start].hits) for start, _end in chain]
    runs: list[Run] = []
    for index, ((start, end), hits) in enumerate(zip(chain, span_hits)):
        chosen = {hit.id: hit for hit in hits}
        front = min((hit.depth for hit in hits), default=None)
        for neighbor in (index - 1, index + 1):
            if neighbor < 0 or neighbor >= len(chain) or front is None:
                continue
            if not _spans_touch(chain[index], chain[neighbor]):
                continue
            own_ids = {hit.id for hit in hits}
            other = span_hits[neighbor]
            # A subject in the neighbor but not here opened this endpoint.
            for hit in other:
                if hit.id not in own_ids and hit.depth < front:
                    chosen[hit.id] = hit
        ref_depth = min(hit.depth for hit in chosen.values())
        ref = [hit for hit in chosen.values() if hit.depth == ref_depth]
        runs.append(Run(start, end, tuple(slots_around_hits(ref))))
    return runs


def _spans_touch(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[1] + 1 == right[0] or right[1] + 1 == left[0]


def _deepest(hits: list[Hit]) -> list[Hit]:
    if not hits:
        return []
    depth = max(hit.depth for hit in hits)
    return [hit for hit in hits if hit.depth == depth]


def coarse_runs(samples: list[Sample]) -> list[Run]:
    """Rear envelope: each sample keeps its deepest hit, then spans follow that key.

    A front subject that only lies on a deeper one drops out, so the stroke is
    cut by sofa and carpet without a tea-table band.
    """
    runs: list[Run] = []
    start: int | None = None
    key: tuple[str, ...] | None = None
    rear: list[Hit] = []
    for index, sample in enumerate(samples):
        if not sample.on:
            if start is not None:
                runs.append(Run(start, index - 1, tuple(slots_around_hits(rear))))
                start = None
                key = None
            continue
        current = _deepest(sample.hits)
        current_key = tuple(hit.id for hit in sorted(current, key=lambda hit: hit.id))
        if start is None:
            start = index
            key = current_key
            rear = current
            continue
        if current_key != key:
            runs.append(Run(start, index - 1, tuple(slots_around_hits(rear))))
            start = index
            key = current_key
            rear = current
    if start is not None:
        runs.append(Run(start, len(samples) - 1, tuple(slots_around_hits(rear))))
    return runs


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
