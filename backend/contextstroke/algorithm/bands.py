"""Depth-band slots for a set of subject hits."""

from __future__ import annotations

from .types import Hit, Slot


def slots_for_hits(hits: list[Hit]) -> list[Slot]:
    """The band before the nearest hit, then the band behind every hit group.

    Depth 1 is in front as 0-1 and behind as 1-2. The last depth 4 is behind as 4-5.
    Coplanar subjects share one group, so they do not order each other.
    Used when contiguous spans have no shared envelope (true subject crossing).
    """
    ordered = _depth_groups(hits)
    if not ordered:
        return []
    slots = [
        Slot(
            ordered[0][0] - 0.5,
            "band",
            tuple(hit.id for hit in ordered[0][1]),
            f"{ordered[0][0] - 1}-{ordered[0][0]}",
        )
    ]
    for depth, members in ordered:
        slots.append(
            Slot(
                depth + 0.5,
                "band",
                tuple(hit.id for hit in members),
                f"{depth}-{depth + 1}",
            )
        )
    return slots


def slots_around_hits(hits: list[Hit]) -> list[Slot]:
    """Only the band in front of and behind one depth group.

    Nested readings use this: slippers narrative → slippers front/behind;
    carpet coarse narrative → carpet front/behind. Does not open bands behind
    a deeper supporting subject.
    """
    ordered = _depth_groups(hits)
    if not ordered:
        return []
    depth, members = ordered[0]
    ids = tuple(hit.id for hit in members)
    return [
        Slot(depth - 0.5, "band", ids, f"{depth - 1}-{depth}"),
        Slot(depth + 0.5, "band", ids, f"{depth}-{depth + 1}"),
    ]


def _depth_groups(hits: list[Hit]) -> list[tuple[int, tuple[Hit, ...]]]:
    groups: dict[int, list[Hit]] = {}
    for hit in hits:
        groups.setdefault(hit.depth, []).append(hit)
    return [(depth, tuple(sorted(groups[depth], key=lambda hit: hit.id))) for depth in sorted(groups)]
