import math

import numpy as np
import pytest

from contextstroke.algorithm.graph import build_scene_graph, detect_instances, match_notes, seed_for
from contextstroke.algorithm.graph.types import direction_label, wrap_angle
from contextstroke.algorithm.scene import InstanceNote, Layer, Scene


def _mask(width, height, rects):
    mask = np.zeros((height, width), dtype=np.uint8)
    for x, y, w, h in rects:
        mask[y : y + h, x : x + w] = 255
    return mask


def _layer(layer_id, depth, mask, *, x=0, y=0, scale=1.0, background=False, notes=()):
    return Layer(
        id=layer_id,
        name=layer_id,
        depth=depth,
        x=x,
        y=y,
        file=f"{layer_id}.png",
        mask=mask,
        scale=scale,
        background=background,
        instances=tuple(notes),
    )


def _scene(layers, width=400, height=200, meters_per_pixel=None):
    return Scene(id="t", name="t", width=width, height=height, layers=layers, meters_per_pixel=meters_per_pixel)


# --- instances -----------------------------------------------------------


def test_two_separate_blobs_in_one_layer_are_two_instances():
    layer = _layer("shelf", 1, _mask(200, 100, [(10, 10, 30, 30), (120, 40, 40, 40)]))
    instances = detect_instances(layer)
    assert [item.id for item in instances] == ["shelf:0", "shelf:1"]
    assert instances[0].bbox_local == (10, 10, 40, 40)
    assert instances[1].bbox_local == (120, 40, 160, 80)
    assert instances[0].area == 900


def test_hairline_gap_merges_and_specks_drop():
    # 3 px crack between two halves -> one object; a 4x4 speck is noise.
    layer = _layer("chair", 1, _mask(200, 100, [(10, 10, 30, 40), (43, 10, 30, 40), (150, 80, 4, 4)]))
    instances = detect_instances(layer)
    assert len(instances) == 1
    assert instances[0].bbox_local == (10, 10, 73, 50)


def test_instance_numbering_ignores_layer_transform():
    mask = _mask(200, 100, [(10, 10, 30, 30), (120, 40, 40, 40)])
    plain = detect_instances(_layer("a", 1, mask))
    moved = detect_instances(_layer("a", 1, mask, x=55, y=-20, scale=0.5))
    assert [item.bbox_local for item in plain] == [item.bbox_local for item in moved]


def test_seed_lies_inside_and_notes_match_by_seed():
    layer = _layer("shelf", 1, _mask(200, 100, [(10, 10, 30, 30), (120, 40, 40, 40)]))
    instances = detect_instances(layer)
    seed = seed_for(instances[1])
    assert instances[1].mask[seed[1], seed[0]]
    good = InstanceNote(seed=seed, category="花瓶")
    stale = InstanceNote(seed=(90, 90), category="消失的")
    matched, unmatched = match_notes(instances, [good, stale])
    assert matched == {"shelf:1": good}
    assert unmatched == [stale]


# --- graph geometry ------------------------------------------------------


def test_centers_normalize_to_background_frame():
    background = _layer("bg", 9, _mask(200, 100, [(0, 0, 200, 100)]), x=100, y=50, scale=2.0, background=True)
    # Transparent padding: the opaque block is 20x20 at local (10, 10); layer at (150, 100) scale 2.
    subject = _layer("cup", 1, _mask(60, 60, [(10, 10, 20, 20)]), x=150, y=100, scale=2.0)
    graph = build_scene_graph(_scene([background, subject], width=600, height=400))
    assert graph.frame == {"x": 100.0, "y": 50.0, "width": 400.0, "height": 200.0, "source": "background"}
    assert [node.id for node in graph.nodes] == ["cup:0"]
    # Canvas bbox = (170, 120)-(210, 160), center (190, 140).
    assert graph.nodes[0].center == pytest.approx(((190 - 100) / 400, (140 - 50) / 200))
    assert graph.nodes[0].pixel_size == (40.0, 40.0)


def test_canvas_frame_without_background():
    subject = _layer("cup", 1, _mask(400, 200, [(0, 0, 100, 100)]))
    graph = build_scene_graph(_scene([subject]))
    assert graph.frame["source"] == "canvas"
    assert graph.nodes[0].center == pytest.approx((50 / 400, 50 / 200))


def test_edge_is_canonical_and_antisymmetric():
    near = _layer("near", 1, _mask(400, 200, [(200, 20, 40, 40)]))
    far = _layer("far", 3, _mask(400, 200, [(20, 140, 40, 40)]))
    graph = build_scene_graph(_scene([far, near]))
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert (edge.u, edge.v) == ("near:0", "far:0")
    assert edge.depth_delta == 2
    dx, dy, angle = edge.vector_from("near:0")
    rdx, rdy, rangle = edge.vector_from("far:0")
    assert (rdx, rdy) == (-dx, -dy)
    assert wrap_angle(rangle - angle) == pytest.approx(180.0)
    # far is left and below near.
    assert dx < 0 and dy > 0
    assert edge.direction == "左下"
    assert edge.direction_from("far:0") == "右上"
    assert graph.edge("far:0", "near:0") is edge
    with pytest.raises(KeyError):
        edge.vector_from("other")


def test_same_depth_orders_by_id():
    a = _layer("b-layer", 2, _mask(400, 200, [(10, 10, 20, 20)]))
    b = _layer("a-layer", 2, _mask(400, 200, [(300, 10, 20, 20)]))
    edge = build_scene_graph(_scene([a, b])).edges[0]
    assert (edge.u, edge.v) == ("a-layer:0", "b-layer:0")


def test_distance_is_aspect_corrected():
    # 2:1 canvas. Horizontal and vertical neighbours both 100 px away.
    origin = _layer("o", 1, _mask(400, 200, [(40, 40, 20, 20)]))
    right = _layer("r", 2, _mask(400, 200, [(140, 40, 20, 20)]))
    down = _layer("d", 3, _mask(400, 200, [(40, 140, 20, 20)]))
    graph = build_scene_graph(_scene([origin, right, down]))
    horizontal = graph.edge("o:0", "r:0")
    vertical = graph.edge("o:0", "d:0")
    assert horizontal.distance == pytest.approx(vertical.distance)
    assert horizontal.distance == pytest.approx(100 / math.hypot(400, 200), rel=1e-5)
    assert horizontal.angle_deg == pytest.approx(0.0)
    assert vertical.angle_deg == pytest.approx(-90.0)
    assert vertical.direction == "下"


def test_direction_labels():
    assert direction_label(0, 1) == "右"
    assert direction_label(22.4, 1) == "右"
    assert direction_label(22.6, 1) == "右上"
    assert direction_label(90, 1) == "上"
    assert direction_label(180, 1) == "左"
    assert direction_label(-170, 1) == "左"
    assert direction_label(-135, 1) == "左下"
    assert direction_label(-45, 1) == "右下"
    assert direction_label(10, 0) == "重合"


def test_occlusion_cases():
    front = _layer("front", 1, _mask(400, 200, [(100, 50, 100, 100)]))
    back = _layer("back", 2, _mask(400, 200, [(150, 50, 100, 100)]))
    apart = _layer("apart", 2, _mask(400, 200, [(320, 10, 40, 40)]))
    peer = _layer("peer", 1, _mask(400, 200, [(180, 120, 60, 60)]))
    graph = build_scene_graph(_scene([front, back, apart, peer]))
    overlapped = graph.edge("front:0", "back:0").occlusion
    assert overlapped.occluded is True
    assert overlapped.occluder == "front:0"
    assert overlapped.overlap_ratio == pytest.approx(0.5, abs=0.05)
    assert graph.edge("front:0", "apart:0").occlusion.occluded is False
    coplanar = graph.edge("front:0", "peer:0").occlusion
    assert coplanar.occluded is False
    assert coplanar.coplanar_overlap is True
    assert coplanar.occluder is None


def test_complete_graph_over_instances_skips_background():
    background = _layer("bg", 9, _mask(400, 200, [(0, 0, 400, 200)]), background=True)
    shelf = _layer("shelf", 2, _mask(400, 200, [(10, 10, 30, 30), (120, 40, 40, 40)]))
    plant = _layer("plant", 1, _mask(400, 200, [(250, 50, 50, 50)]))
    graph = build_scene_graph(_scene([background, shelf, plant]))
    assert [node.id for node in graph.nodes] == ["plant:0", "shelf:0", "shelf:1"]
    assert len(graph.edges) == 3
    inner = graph.edge("shelf:0", "shelf:1")
    assert inner.same_layer is True
    assert inner.depth_delta == 0
    assert inner.occlusion.occluded is False
    assert [node.category for node in graph.nodes] == ["plant", "shelf #1", "shelf #2"]
    assert sorted(graph.neighbors("plant:0")) == ["shelf:0", "shelf:1"]


def test_metric_priority():
    sofa_mask = _mask(400, 200, [(10, 10, 100, 50)])
    lamp_mask = _mask(400, 200, [(200, 10, 20, 80)])
    sofa_seed = seed_for(detect_instances(_layer("sofa", 1, sofa_mask))[0])
    sofa = _layer("sofa", 1, sofa_mask, notes=[InstanceNote(seed=sofa_seed, category="沙发", metric_width=2.0)])
    lamp = _layer("lamp", 2, lamp_mask)

    derived = build_scene_graph(_scene([sofa, lamp]))
    assert derived.meters_per_pixel_source == "derived"
    assert derived.meters_per_pixel == pytest.approx(0.02)
    sofa_node, lamp_node = derived.nodes
    assert sofa_node.category == "沙发"
    assert (sofa_node.metric_width, sofa_node.width_source) == (2.0, "manual")
    assert (sofa_node.metric_height, sofa_node.height_source) == (pytest.approx(1.0), "estimated")
    assert sofa_node.metric_source == "mixed"
    assert lamp_node.metric_width == pytest.approx(0.4)
    assert lamp_node.metric_source == "estimated"

    manual = build_scene_graph(_scene([sofa, lamp], meters_per_pixel=0.01))
    assert manual.meters_per_pixel_source == "manual"
    assert manual.nodes[1].metric_height == pytest.approx(0.8)

    unknown = build_scene_graph(_scene([_layer("lamp", 2, lamp_mask)]))
    assert unknown.meters_per_pixel is None
    assert unknown.nodes[0].metric_source == "unknown"


def test_unmatched_annotation_is_reported():
    stale = InstanceNote(seed=(399, 199), category="旧标注")
    layer = _layer("cup", 1, _mask(400, 200, [(10, 10, 20, 20)]), notes=[stale])
    graph = build_scene_graph(_scene([layer]))
    assert graph.nodes[0].annotated is False
    assert graph.unmatched_annotations[0]["category"] == "旧标注"
    assert graph.to_dict()["nodes"][0]["metric"]["source"] == "unknown"
