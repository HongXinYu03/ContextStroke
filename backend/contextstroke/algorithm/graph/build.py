"""Build the undirected scene graph from a layered scene."""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import median

from ..scene.model import InstanceNote, Layer, Scene
from .instances import Instance, detect_instances, match_notes
from .raster import Footprint, footprint, overlap_cells
from .types import Occlusion, SceneEdge, SceneGraph, SceneNode, direction_label, wrap_angle

_ROUND = 6


@dataclass
class _Item:
    layer: Layer
    instance: Instance
    note: InstanceNote | None
    footprint: Footprint
    category: str


def reference_frame(scene: Scene) -> dict:
    """Background display rect when there is one, else the whole canvas."""
    background = next((layer for layer in scene.layers if layer.background), None)
    if background is not None and background.mask.size:
        scale = background.scale if background.scale > 1e-9 else 1.0
        height, width = background.mask.shape
        return {
            "x": float(background.x),
            "y": float(background.y),
            "width": float(width * scale),
            "height": float(height * scale),
            "source": "background",
        }
    return {"x": 0.0, "y": 0.0, "width": float(scene.width), "height": float(scene.height), "source": "canvas"}


def build_scene_graph(scene: Scene) -> SceneGraph:
    frame = reference_frame(scene)
    fx, fy, fw, fh = frame["x"], frame["y"], max(frame["width"], 1e-9), max(frame["height"], 1e-9)
    diagonal = math.hypot(fw, fh)

    items: list[_Item] = []
    unmatched: list[dict] = []
    for layer in scene.layers:
        if layer.background:
            continue
        instances = detect_instances(layer)
        matched, missed = match_notes(instances, layer.instances)
        for note in missed:
            unmatched.append(
                {
                    "layer_id": layer.id,
                    "layer_name": layer.name,
                    "seed": list(note.seed),
                    "category": note.category,
                    "metric_width": note.metric_width,
                    "metric_height": note.metric_height,
                }
            )
        for instance in instances:
            note = matched.get(instance.id)
            default = layer.name if len(instances) == 1 else f"{layer.name} #{instance.index + 1}"
            category = note.category if note is not None and note.category else default
            items.append(_Item(layer, instance, note, footprint(layer, instance), category))

    meters_per_pixel, mpp_source = _meters_per_pixel(scene, items)

    def norm_x(value: float) -> float:
        return round((value - fx) / fw, _ROUND)

    def norm_y(value: float) -> float:
        return round((value - fy) / fh, _ROUND)

    nodes: list[SceneNode] = []
    by_id: dict[str, tuple[SceneNode, _Item]] = {}
    for item in items:
        x0, y0, x1, y1 = item.footprint.bbox
        pixel_w, pixel_h = x1 - x0, y1 - y0
        width, width_source = _metric(item.note.metric_width if item.note else None, pixel_w, meters_per_pixel)
        height, height_source = _metric(item.note.metric_height if item.note else None, pixel_h, meters_per_pixel)
        scale = item.layer.scale if item.layer.scale > 1e-9 else 1.0
        node = SceneNode(
            id=item.instance.id,
            layer_id=item.layer.id,
            name=item.layer.name,
            category=item.category,
            depth=item.layer.depth,
            center=(norm_x((x0 + x1) / 2), norm_y((y0 + y1) / 2)),
            centroid=(norm_x(item.footprint.centroid[0]), norm_y(item.footprint.centroid[1])),
            bbox=(norm_x(x0), norm_y(y0), norm_x(x1), norm_y(y1)),
            pixel_size=(round(pixel_w, 3), round(pixel_h, 3)),
            area_px=round(item.instance.area * scale * scale, 3),
            metric_width=width,
            metric_height=height,
            width_source=width_source,
            height_source=height_source,
            annotated=item.note is not None,
        )
        nodes.append(node)
        by_id[node.id] = (node, item)
    nodes.sort(key=lambda node: (node.depth, node.id))

    edges: list[SceneEdge] = []
    for left_index, u in enumerate(nodes):
        for v in nodes[left_index + 1 :]:
            edges.append(_edge(u, v, by_id[u.id][1], by_id[v.id][1], fw, fh, diagonal))
    edges.sort(key=lambda edge: (edge.u, edge.v))

    return SceneGraph(
        frame={key: (round(value, 3) if isinstance(value, float) else value) for key, value in frame.items()},
        meters_per_pixel=None if meters_per_pixel is None else round(meters_per_pixel, 8),
        meters_per_pixel_source=mpp_source,
        nodes=nodes,
        edges=edges,
        unmatched_annotations=unmatched,
    )


def _edge(u: SceneNode, v: SceneNode, item_u: _Item, item_v: _Item, fw: float, fh: float, diagonal: float) -> SceneEdge:
    # Nodes are sorted by (depth, id), so u is the canonical nearer end.
    dx = v.center[0] - u.center[0]
    dy = v.center[1] - u.center[1]
    px, py = dx * fw, dy * fh
    distance = math.hypot(px, py) / diagonal if diagonal > 0 else 0.0
    angle = wrap_angle(math.degrees(math.atan2(-py, px))) if distance > 1e-12 else 0.0
    same_layer = u.layer_id == v.layer_id
    overlap = 0 if same_layer else overlap_cells(item_u.footprint, item_v.footprint)
    smaller = min(item_u.footprint.cells.size, item_v.footprint.cells.size)
    ratio = overlap / smaller if smaller else 0.0
    occluded = overlap > 0 and u.depth != v.depth
    occlusion = Occlusion(
        occluded=occluded,
        occluder=u.id if occluded else None,
        overlap_ratio=round(ratio, 4),
        coplanar_overlap=overlap > 0 and u.depth == v.depth,
    )
    return SceneEdge(
        u=u.id,
        v=v.id,
        dx=round(dx, _ROUND),
        dy=round(dy, _ROUND),
        distance=round(distance, _ROUND),
        angle_deg=round(angle, 3),
        direction=direction_label(angle, distance),
        depth_delta=v.depth - u.depth,
        same_layer=same_layer,
        occlusion=occlusion,
    )


def _meters_per_pixel(scene: Scene, items: list[_Item]) -> tuple[float | None, str | None]:
    if scene.meters_per_pixel is not None:
        return scene.meters_per_pixel, "manual"
    ratios: list[float] = []
    for item in items:
        if item.note is None:
            continue
        x0, y0, x1, y1 = item.footprint.bbox
        if item.note.metric_width is not None and x1 - x0 > 0:
            ratios.append(item.note.metric_width / (x1 - x0))
        if item.note.metric_height is not None and y1 - y0 > 0:
            ratios.append(item.note.metric_height / (y1 - y0))
    if not ratios:
        return None, None
    return float(median(ratios)), "derived"


def _metric(manual: float | None, pixels: float, meters_per_pixel: float | None) -> tuple[float | None, str]:
    if manual is not None:
        return manual, "manual"
    if meters_per_pixel is not None and pixels > 0:
        return round(pixels * meters_per_pixel, 4), "estimated"
    return None, "unknown"
