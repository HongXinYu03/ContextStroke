"""Depth-band candidate enumeration and track geometry."""

from __future__ import annotations

import itertools

from .types import Run, Sample, Slot

COMBO_LIMIT = 4096
# Adjacent atomic spans with no off between them cannot jump more than one band.
MAX_CONTIGUOUS_JUMP = 1.0 + 1e-6


def build_tracks(
    samples: list[Sample],
    fine_runs: list[Run],
    coarse_runs: list[Run],
    max_tracks: int,
    off_depth: float | None,
) -> list[dict]:
    ranked: list[tuple[tuple, dict]] = []
    # Oversample combinations: contiguous-jump filtering drops many fine combos.
    pool = max(max_tracks * 8, max_tracks)
    for runs in (fine_runs, coarse_runs):
        for combo in combinations(runs, pool):
            if not combo_valid(runs, combo):
                continue
            built = build_track(samples, runs, combo, off_depth)
            ranked.append((rank_track(built), built))
    ranked.sort(key=lambda item: item[0])

    tracks = []
    summaries: set[str] = set()
    for _key, built in ranked:
        summary = built["summary"]
        if summary in summaries:
            continue
        summaries.add(summary)
        tracks.append(
            {
                "id": str(len(tracks) + 1),
                "cost": built["cost"],
                "selected": not tracks,
                "summary": summary,
                "segments": built["segments"],
                "breaks": built["breaks"],
            }
        )
        if len(tracks) >= max_tracks:
            break
    return tracks


def combo_valid(runs: list[Run], combo: tuple[int, ...]) -> bool:
    """Reject contiguous atomic spans that jump more than one depth band."""
    for index in range(len(runs) - 1):
        left_run = runs[index]
        right_run = runs[index + 1]
        if left_run.end + 1 != right_run.start:
            # Off samples between spans may bridge any depth jump.
            continue
        left = left_run.slots[combo[index]]
        right = right_run.slots[combo[index + 1]]
        if abs(left.slot_depth - right.slot_depth) > MAX_CONTIGUOUS_JUMP:
            return False
    return True


def combinations(runs: list[Run], limit: int) -> list[tuple[int, ...]]:
    counts = [len(run.slots) for run in runs]
    total = 1
    overflow = False
    for count in counts:
        total *= count
        if total > COMBO_LIMIT:
            overflow = True
            break
    pinned = pinned_combos(counts)
    if not overflow and total <= limit:
        return dedupe(pinned + list(itertools.product(*[range(count) for count in counts])))

    chosen = list(pinned)
    seen = set(chosen)

    def add(combo: tuple[int, ...]) -> bool:
        if combo in seen:
            return len(chosen) >= limit
        seen.add(combo)
        chosen.append(combo)
        return len(chosen) >= limit

    # Single-span edits of every pinned base keep mixed readings like
    # "front of slippers, then between slippers and carpet".
    for index, count in enumerate(counts):
        for rank in range(count):
            for base in pinned:
                combo = list(base)
                combo[index] = rank
                if add(tuple(combo)):
                    return chosen

    if not overflow:
        combos = list(itertools.product(*[range(count) for count in counts]))
        combos.sort(key=lambda combo: combo_rank(combo, pinned))
        for combo in combos:
            if add(combo):
                return chosen
    return chosen[:limit]


def pinned_combos(counts: list[int]) -> list[tuple[int, ...]]:
    shallow = tuple(0 for _ in counts)
    deep = tuple(count - 1 for count in counts)
    # Prefer the middle band on every span (e.g. between two overlapping subjects).
    middle = tuple((count - 1) // 2 for count in counts)
    alternate = tuple(0 if index % 2 == 0 else count - 1 for index, count in enumerate(counts))
    opposite = tuple(count - 1 if index % 2 == 0 else 0 for index, count in enumerate(counts))
    # Step one band deeper on each successive span when the span allows it.
    ramp = tuple(min(index, count - 1) for index, count in enumerate(counts))
    return dedupe([shallow, deep, middle, alternate, opposite, ramp])


def dedupe(combos: list[tuple[int, ...]]) -> list[tuple[int, ...]]:
    result: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for combo in combos:
        if combo in seen:
            continue
        seen.add(combo)
        result.append(combo)
    return result


def combo_rank(combo: tuple[int, ...], pinned: list[tuple[int, ...]]) -> tuple:
    switches = sum(left != right for left, right in zip(combo, combo[1:]))
    return (0 if combo in pinned else 1, -switches, sum(combo))


def rank_track(built: dict) -> tuple:
    return (built["cost"], built["slot_sum"])


def build_track(
    samples: list[Sample], runs: list[Run], combo: tuple[int, ...], off_depth: float | None
) -> dict:
    choice: list[Slot | None] = [None] * len(samples)
    slot_sum = 0.0
    for run, rank in zip(runs, combo):
        slot = run.slots[rank]
        slot_sum += slot.slot_depth
        for index in range(run.start, run.end + 1):
            choice[index] = slot

    cost = 0.0
    for index in range(len(runs) - 1):
        left = runs[index].slots[combo[index]]
        right = runs[index + 1].slots[combo[index + 1]]
        # Contiguous jumps are capped by combo_valid; off may still cross many layers.
        cost += abs(left.slot_depth - right.slot_depth)

    segments = segments_for_track(samples, runs, combo, choice, off_depth)
    return {
        "cost": round(cost, 4),
        "slot_sum": slot_sum,
        "summary": summary_for(segments),
        "segments": segments,
        "breaks": [],
    }


def segments_for_track(
    samples: list[Sample],
    runs: list[Run],
    combo: tuple[int, ...],
    choice: list[Slot | None],
    off_depth: float | None,
) -> list[dict]:
    segments: list[dict] = []
    current: dict | None = None
    previous: dict | None = None
    for index, sample in enumerate(samples):
        described = describe_sample(samples, runs, combo, choice, index, off_depth)
        if described is None:
            continue
        if current is None:
            current = open_segment(described, None)
        elif (described["relation"], described["label"]) != (current["relation"], current["label"]):
            segments.append(close_segment(current))
            current = open_segment(described, previous)
        else:
            current["points"].append(geometry(described))
            current["end"] = described["sample"]
            current["semantic"].append(described["slot_depth"])
        previous = described
    if current is not None:
        segments.append(close_segment(current))
    return segments


def describe_sample(
    samples: list[Sample],
    runs: list[Run],
    combo: tuple[int, ...],
    choice: list[Slot | None],
    index: int,
    off_depth: float | None,
) -> dict | None:
    sample = samples[index]
    slot = choice[index]
    if sample.on and slot is not None:
        return {
            "sample": index,
            "x": sample.x,
            "y": sample.y,
            "slot_depth": slot.slot_depth,
            "relation": slot.relation,
            "label": slot.label,
            "layer_ids": list(slot.layer_ids),
        }
    if sample.on:
        return None
    depth = off_slot_depth(runs, combo, index, off_depth)
    if depth is None:
        return None
    return {
        "sample": index,
        "x": sample.x,
        "y": sample.y,
        "slot_depth": depth,
        "relation": "off",
        "label": "空白",
        "layer_ids": [],
    }


def off_slot_depth(
    runs: list[Run], combo: tuple[int, ...], index: int, off_depth: float | None
) -> float | None:
    if off_depth is not None:
        return off_depth
    previous: tuple[Run, Slot] | None = None
    nxt: tuple[Run, Slot] | None = None
    for run, rank in zip(runs, combo):
        slot = run.slots[rank]
        if run.end < index:
            previous = (run, slot)
        elif run.start > index and nxt is None:
            nxt = (run, slot)
    if previous is not None and nxt is not None:
        span = nxt[0].start - previous[0].end
        if span <= 0:
            return previous[1].slot_depth
        t = (index - previous[0].end) / span
        return previous[1].slot_depth * (1 - t) + nxt[1].slot_depth * t
    if previous is not None:
        return previous[1].slot_depth
    if nxt is not None:
        return nxt[1].slot_depth
    return None


def open_segment(described: dict, joint: dict | None) -> dict:
    points = []
    if joint is not None and (
        abs(joint["x"] - described["x"]) > 0.05 or abs(joint["y"] - described["y"]) > 0.05
    ):
        points.append(geometry(joint))
    points.append(geometry(described))
    return {
        "relation": described["relation"],
        "label": described["label"],
        "layer_ids": list(described["layer_ids"]),
        "start": described["sample"],
        "end": described["sample"],
        "points": points,
        "semantic": [described["slot_depth"]],
    }


def geometry(described: dict) -> dict:
    return {
        "sample": described["sample"],
        "x": round(float(described["x"]), 2),
        "y": round(float(described["y"]), 2),
        "slot_depth": round(float(described["slot_depth"]), 4),
    }


def close_segment(segment: dict) -> dict:
    depths = segment["semantic"]
    uniform = max(depths) - min(depths) <= 1e-6
    return {
        "start": segment["start"],
        "end": segment["end"],
        "relation": segment["relation"],
        "label": segment["label"],
        "layer_ids": segment["layer_ids"],
        "slot_depth": round(float(depths[0]), 4) if uniform else None,
        "points": segment["points"],
    }


def summary_for(segments: list[dict]) -> str:
    labels: list[str] = []
    for segment in segments:
        label = segment["label"]
        if not labels or labels[-1] != label:
            labels.append(label)
    return " → ".join(labels)
