"""On-span construction.

Overlapping subjects: each depth is one cut, deepest first, using only that
subject's front or behind band. Hollow contours keep the hole on that cut.

Disjoint subjects separated by a real off gap: do not emit half cuts that drop
the other subject's on spans. One full-stroke bridge keeps every on segment.
"""

from __future__ import annotations

from .bands import slots_around_hits
from .types import Hit, Run, Sample


def hit_key(sample: Sample) -> tuple[str, ...]:
    """Stable identity of which subjects a sample touches."""
    return tuple(hit.id for hit in sample.hits)


def depth_passes(
    samples: list[Sample], overlaps: set[frozenset[str]] | None = None
) -> list[list[Run]]:
    """Per-depth cuts for one overlapping component; bridge for disjoint islands."""
    spans = _raw_hitset_spans(samples)
    if not spans:
        return []
    span_hits = [list(samples[start].hits) for start, _end in spans]
    overlap_set = overlaps or set()
    claimed = _exclusive_claims(spans, span_hits, overlap_set)
    # Lamp then blank then picture: two islands. A lamp-only cut would hide the
    # picture on segment. Overlapping stacks stay one component and still cut
    # deepest-first.
    if _component_count(spans, span_hits, overlap_set) > 1:
        bridge = _bridge_runs(spans, span_hits, claimed)
        return [bridge] if bridge else []
    depths = sorted({hit.depth for hits in span_hits for hit in hits}, reverse=True)
    passes = []
    for depth in depths:
        runs = _pass_runs(spans, span_hits, claimed, depth)
        if runs:
            passes.append(runs)
    if _has_off_gap(spans):
        bridge = _bridge_runs(spans, span_hits, claimed)
        if bridge and bridge not in passes:
            passes.append(bridge)
    return passes


def _has_off_gap(spans: list[tuple[int, int]]) -> bool:
    return any(left[1] + 1 != right[0] for left, right in zip(spans, spans[1:]))


def _component_count(
    spans: list[tuple[int, int]], span_hits: list[list[Hit]], overlaps: set[frozenset[str]]
) -> int:
    """How many stroke islands after joining contiguous or overlapping neighbors."""
    if not spans:
        return 0
    parent = list(range(len(spans)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for index in range(len(spans) - 1):
        contiguous = spans[index][1] + 1 == spans[index + 1][0]
        if contiguous or _subjects_overlap(span_hits[index], span_hits[index + 1], overlaps):
            union(index, index + 1)
    return len({find(index) for index in range(len(spans))})


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


def _exclusive_claims(
    spans: list[tuple[int, int]], span_hits: list[list[Hit]], overlaps: set[frozenset[str]]
) -> dict[int, list[Hit]]:
    """Spans opened by a deeper contour stay with that contour.

    A blank gap counts too when the subjects overlap, so a shelf hollow or
    silhouette still owns the span on the other side of that off.
    """
    claimed: dict[int, list[Hit]] = {}
    for index in range(len(spans) - 1):
        contiguous = spans[index][1] + 1 == spans[index + 1][0]
        if not contiguous and not _subjects_overlap(span_hits[index], span_hits[index + 1], overlaps):
            continue
        _claim_exit(span_hits[index], span_hits[index + 1], index + 1, claimed)
        _claim_exit(span_hits[index + 1], span_hits[index], index, claimed)
    return claimed


def _subjects_overlap(left: list[Hit], right: list[Hit], overlaps: set[frozenset[str]]) -> bool:
    left_ids = {hit.id for hit in left}
    right_ids = {hit.id for hit in right}
    return any(
        frozenset((left_id, right_id)) in overlaps
        for left_id in left_ids
        for right_id in right_ids
        if left_id != right_id
    )


def _claim_exit(source: list[Hit], dest: list[Hit], dest_index: int, claimed: dict[int, list[Hit]]) -> None:
    dest_ids = {hit.id for hit in dest}
    disappeared = [hit for hit in source if hit.id not in dest_ids]
    if not disappeared or not dest:
        return
    dest_rear = max(hit.depth for hit in dest)
    owners = [hit for hit in disappeared if hit.depth > dest_rear]
    if not owners:
        return
    owner_depth = max(hit.depth for hit in owners)
    owners = [hit for hit in owners if hit.depth == owner_depth]
    previous = claimed.get(dest_index)
    if previous is None or owner_depth > previous[0].depth:
        claimed[dest_index] = owners


def _pass_runs(
    spans: list[tuple[int, int]],
    span_hits: list[list[Hit]],
    claimed: dict[int, list[Hit]],
    depth: int,
) -> list[Run]:
    """This cut uses only this subject's front/behind bands.

    Spans where this subject stays hit and the spans touch are one segment, so
    a rear layer under a hollow frame moves as a whole. A span this contour
    opens but does not hit — the hole, or the stroke just outside the frame —
    stays its own segment on this cut. Spans claimed by another depth are left
    out.
    """
    owned = [
        index
        for index in range(len(spans))
        if _owner_hits(spans, span_hits, claimed, index, depth) is not None
    ]
    if not owned:
        return []
    groups: list[list[int]] = [[owned[0]]]
    for index in owned[1:]:
        previous = groups[-1][-1]
        if _same_presence(spans, span_hits, previous, index, depth):
            groups[-1].append(index)
        else:
            groups.append([index])
    runs: list[Run] = []
    for group in groups:
        start = spans[group[0]][0]
        end = spans[group[-1]][1]
        reference = _reference_hits(spans, span_hits, claimed, group[0], depth)
        runs.append(Run(start, end, tuple(slots_around_hits(reference))))
    return runs


def _same_presence(
    spans: list[tuple[int, int]],
    span_hits: list[list[Hit]],
    left: int,
    right: int,
    depth: int,
) -> bool:
    """Merge only while this subject itself stays hit. A hole breaks the merge."""
    if left + 1 != right:
        return False
    if spans[left][1] + 1 != spans[right][0]:
        return False
    return _has_depth(span_hits[left], depth) and _has_depth(span_hits[right], depth)


def _has_depth(hits: list[Hit], depth: int) -> bool:
    return any(hit.depth == depth for hit in hits)


def _reference_hits(
    spans: list[tuple[int, int]],
    span_hits: list[list[Hit]],
    claimed: dict[int, list[Hit]],
    index: int,
    depth: int,
) -> list[Hit]:
    owners = claimed.get(index)
    if owners is not None and owners[0].depth == depth:
        return owners
    found = [hit for hit in span_hits[index] if hit.depth == depth]
    if found:
        return found
    return _hits_at_depth(spans, span_hits, index, depth)


def _bridge_runs(
    spans: list[tuple[int, int]], span_hits: list[list[Hit]], claimed: dict[int, list[Hit]]
) -> list[Run]:
    """Full-stroke reading across a real off gap.

    Each span stays with the contour that claimed it, otherwise with the front
    subject on that span. A sofa behind the tea table must not pull the span
    back to sofa depth just because the mask is also hit.
    """
    runs: list[Run] = []
    for index, (start, end) in enumerate(spans):
        reference = claimed.get(index) or _front(span_hits[index])
        runs.append(Run(start, end, tuple(slots_around_hits(reference))))
    return runs


def _owner_hits(
    spans: list[tuple[int, int]],
    span_hits: list[list[Hit]],
    claimed: dict[int, list[Hit]],
    index: int,
    depth: int,
) -> list[Hit] | None:
    owners = claimed.get(index)
    if owners is not None:
        if owners[0].depth != depth:
            return None
        return owners
    if not _depth_cuts(spans, span_hits, index, depth):
        return None
    return _hits_at_depth(spans, span_hits, index, depth)


def _front(hits: list[Hit]) -> list[Hit]:
    depth = min(hit.depth for hit in hits)
    return [hit for hit in hits if hit.depth == depth]


def _depth_cuts(
    spans: list[tuple[int, int]], span_hits: list[list[Hit]], index: int, depth: int
) -> bool:
    """True when this depth is hit here, or its contour is a contiguous endpoint.

    The rear subject under a hollow frame is hit inside the hole and on the
    frame, so it owns the whole stroke. The hollow subject also owns the hole:
    its contour is the endpoint, even though the hole itself does not hit it.
    """
    if _has_depth(span_hits[index], depth):
        return True
    own_ids = {hit.id for hit in span_hits[index]}
    for neighbor in (index - 1, index + 1):
        if neighbor < 0 or neighbor >= len(spans):
            continue
        if spans[index][1] + 1 != spans[neighbor][0] and spans[neighbor][1] + 1 != spans[index][0]:
            continue
        if any(hit.depth == depth and hit.id not in own_ids for hit in span_hits[neighbor]):
            return True
    return False


def _hits_at_depth(
    spans: list[tuple[int, int]], span_hits: list[list[Hit]], index: int, depth: int
) -> list[Hit]:
    found = [hit for hit in span_hits[index] if hit.depth == depth]
    if found:
        return found
    own_ids = {hit.id for hit in span_hits[index]}
    for neighbor in (index - 1, index + 1):
        if neighbor < 0 or neighbor >= len(spans):
            continue
        if spans[index][1] + 1 != spans[neighbor][0] and spans[neighbor][1] + 1 != spans[index][0]:
            continue
        found = [hit for hit in span_hits[neighbor] if hit.depth == depth and hit.id not in own_ids]
        if found:
            return found
    raise RuntimeError(f"depth {depth} cuts span {index} but has no hits")


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
