"""Depth-band slots for a set of subject hits."""

from __future__ import annotations

from .types import Hit, Slot


def slots_for_hits(hits: list[Hit]) -> list[Slot]:
    """The band before the nearest hit, then the band behind every hit group.

    Depth 1 is in front as 0-1 and behind as 1-2. The last depth 4 is behind as 4-5.
    Coplanar subjects share one group, so they do not order each other.
    """
    groups: dict[int, list[Hit]] = {}
    for hit in hits:
        groups.setdefault(hit.depth, []).append(hit)
    ordered = [(depth, tuple(sorted(groups[depth], key=lambda hit: hit.id))) for depth in sorted(groups)]
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
