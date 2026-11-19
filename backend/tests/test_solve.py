import numpy as np

from contextstroke.algorithm.scene import Layer, Scene
from contextstroke.algorithm.solve import resample_2d, solve


def _layer(layer_id, name, depth, width, height, rect):
    mask = np.zeros((height, width), np.uint8)
    x, y, rect_width, rect_height = rect
    mask[y : y + rect_height, x : x + rect_width] = 255
    return Layer(layer_id, name, depth, 0, 0, f"{layer_id}.png", mask)


def _scene(layers, width=400, height=200):
    return Scene("memory", "memory", width, height, layers)


def test_resample_keeps_vertices_and_spacing():
    points = resample_2d([(0, 0), (30, 40), (100, 0)], spacing=10, maximum=50)
    assert points is not None
    assert points[0] == (0, 0)
    assert points[-1] == (100, 0)
    assert (30, 40) in points
    gaps = [
        ((right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2) ** 0.5
        for left, right in zip(points, points[1:])
    ]
    assert gaps
    assert max(gaps) <= 10 + 1e-6


def test_identical_points_are_rejected():
    result = solve(_scene([]), [(10, 10), (10, 10)])
    assert result["status"] == "insufficient_input"
    assert result["tracks"] == []


def test_all_off_has_explicit_status():
    layer = _layer("box", "方块", 1, 400, 200, (50, 50, 40, 40))
    result = solve(_scene([layer]), [(10, 10), (30, 10)])
    assert result["status"] == "all_off"
    assert result["message"]
    assert result["tracks"] == []
    assert result["samples"]
    assert all(not sample["on"] for sample in result["samples"])


def test_background_alone_is_off_and_subjects_are_on():
    background = _layer("wall", "背景墙", 3, 400, 200, (0, 0, 400, 200))
    background.background = True
    subject = _layer("sofa", "沙发", 1, 400, 200, (120, 60, 160, 80))
    scene = _scene([background, subject])
    only_wall = solve(scene, [(20, 20), (80, 20)])
    assert only_wall["status"] == "all_off"
    assert all(not sample["on"] for sample in only_wall["samples"])

    across = solve(scene, [(20, 100), (280, 100)])
    assert across["status"] == "ok"
    assert across["samples"][0]["on"] is False
    assert any(sample["on"] and any(hit["id"] == "sofa" for hit in sample["hits"]) for sample in across["samples"])
    assert "空白" in across["tracks"][0]["summary"]
    assert across["tracks"][0]["segments"][0]["relation"] == "off"
    assert across["tracks"][0]["segments"][0]["slot_depth"] == 2.5


def test_single_layer_offers_both_bands_and_prefers_the_nearer():
    layer = _layer("plant", "前景植物", 1, 400, 200, (20, 20, 200, 80))
    result = solve(_scene([layer]), [(40, 50), (180, 50)])
    assert result["status"] == "ok"
    assert result["discontinuities"] == []
    selected = result["tracks"][0]
    assert selected["selected"] is True
    assert selected["cost"] == 0
    assert selected["summary"] == "0-1"
    assert all(segment["relation"] == "band" for segment in selected["segments"])
    assert selected["segments"][0]["slot_depth"] == 0.5
    behind = next(track for track in result["tracks"] if track["summary"] == "1-2")
    assert behind["cost"] == 0
    assert behind["segments"][0]["slot_depth"] == 1.5


def test_coplanar_subjects_share_one_band():
    table = _layer("table", "白色矮桌", 2, 400, 200, (40, 40, 120, 80))
    slippers = _layer("slippers", "紫色拖鞋", 2, 400, 200, (80, 60, 120, 80))
    result = solve(_scene([table, slippers]), [(100, 90), (140, 100)])
    assert result["status"] == "ok"
    assert result["tracks"][0]["summary"] == "1-2"
    front = result["tracks"][0]["segments"][0]
    assert front["relation"] == "band"
    assert front["slot_depth"] == 1.5
    assert set(front["layer_ids"]) == {"table", "slippers"}
    assert any(track["summary"] == "2-3" for track in result["tracks"])
    overlap = result["samples"][0]["hits"]
    assert [hit["depth"] for hit in overlap] == [2, 2]


def test_gap_of_one_missing_layer_still_connects():
    near = _layer("near", "近处", 1, 400, 200, (0, 40, 80, 80))
    far = _layer("far", "远处", 3, 400, 200, (160, 40, 80, 80))
    result = solve(_scene([near, far]), [(40, 80), (200, 80)])
    assert result["status"] == "ok"
    assert result["discontinuities"] == []
    assert result["tracks"][0]["cost"] == 1
    assert "1-2" in result["tracks"][0]["summary"]
    assert "2-3" in result["tracks"][0]["summary"]


def test_off_may_cross_large_depth_jumps():
    near = _layer("near", "近处", 1, 400, 200, (0, 40, 80, 80))
    far = _layer("far", "远处", 4, 400, 200, (240, 40, 80, 80))
    result = solve(_scene([near, far]), [(40, 80), (280, 80)])
    assert result["status"] == "ok"
    assert result["discontinuities"] == []
    assert result["tracks"]
    assert result["tracks"][0]["breaks"] == []
    assert result["tracks"][0]["cost"] == 2
    off = next(segment for segment in result["tracks"][0]["segments"] if segment["relation"] == "off")
    xs = [point["x"] for point in off["points"]]
    assert min(xs) <= 80 and max(xs) >= 239
    assert max(xs) - min(xs) > 150


def test_each_on_run_keeps_an_alternating_candidate():
    table = _layer("table", "白色矮桌", 2, 400, 200, (50, 40, 80, 80))
    result = solve(_scene([table]), [(10, 70), (90, 70), (180, 70), (180, 100), (90, 100), (10, 100)])
    summaries = [track["summary"] for track in result["tracks"]]
    assert "空白 → 1-2 → 空白 → 1-2 → 空白" in summaries
    assert "空白 → 2-3 → 空白 → 2-3 → 空白" in summaries
    assert any("1-2 → 空白 → 2-3" in summary for summary in summaries)
    assert any("2-3 → 空白 → 1-2" in summary for summary in summaries)
    assert result["tracks"][0]["summary"] == "空白 → 1-2 → 空白 → 1-2 → 空白"
    assert result["tracks"][0]["cost"] == 0


def test_on_off_switches_on_the_mask_edge():
    layer = _layer("box", "方块", 1, 200, 80, (40, 10, 80, 60))
    result = solve(_scene([layer], 200, 80), [(10, 40), (160, 40)])
    samples = result["samples"]
    first_on = next(index for index, sample in enumerate(samples) if sample["on"])
    assert first_on > 0
    assert 38.5 <= samples[first_on]["x"] <= 41
    assert samples[first_on - 1]["x"] >= 38
    band = next(segment for segment in result["tracks"][0]["segments"] if segment["relation"] == "band")
    assert 38.5 <= band["points"][0]["x"] <= 41


def test_crossed_layers_split_by_hit_set():
    plant = _layer("plant", "前景植物", 1, 800, 600, (480, 70, 240, 280))
    table = _layer("table", "白色矮桌", 2, 800, 600, (220, 240, 360, 200))
    scene = _scene([plant, table], 800, 600)
    result = solve(scene, [(660, 112), (520, 300), (300, 320)])
    assert result["status"] == "ok"
    assert [hit["id"] for hit in result["samples"][0]["hits"]] == ["plant"]
    assert [hit["id"] for hit in result["samples"][-1]["hits"]] == ["table"]
    assert any({hit["id"] for hit in sample["hits"]} == {"plant", "table"} for sample in result["samples"])
    labels = {
        segment["label"]
        for track in result["tracks"]
        for segment in track["segments"]
        if segment["relation"] == "band"
    }
    assert {"0-1", "1-2", "2-3"} <= labels
    assert result["tracks"][0]["cost"] == 0


def test_overlapping_subjects_use_nested_and_envelope_bands():
    """Slippers on carpet: fine = slippers front/behind; coarse = carpet front/behind."""
    carpet = _layer("carpet", "地毯", 3, 400, 200, (40, 40, 280, 120))
    slippers = _layer("slippers", "拖鞋", 1, 400, 200, (100, 60, 80, 60))
    scene = _scene([carpet, slippers])
    # carpet → both → carpet → both → carpet, never fully off
    stroke = [(60, 90), (140, 90), (220, 90), (140, 110), (60, 110)]
    result = solve(scene, stroke)
    assert result["status"] == "ok"
    hit_sets = []
    for sample in result["samples"]:
        if not sample["on"]:
            continue
        key = tuple(sorted(hit["id"] for hit in sample["hits"]))
        if not hit_sets or hit_sets[-1] != key:
            hit_sets.append(key)
    assert hit_sets == [
        ("carpet",),
        ("carpet", "slippers"),
        ("carpet",),
        ("carpet", "slippers"),
        ("carpet",),
    ]
    summaries = [track["summary"] for track in result["tracks"]]
    labels = {
        segment["label"]
        for track in result["tracks"]
        for segment in track["segments"]
        if segment["relation"] == "band"
    }
    # Fine narrative: slippers only. Coarse narrative: carpet only.
    assert labels == {"0-1", "1-2", "2-3", "3-4"}
    assert "0-1" in summaries
    assert "1-2" in summaries
    assert "2-3" in summaries
    assert "3-4" in summaries
    # Fine must not offer carpet-behind mixed into slippers atomic reading.
    assert all("3-4 → 0-1" not in summary and "0-1 → 3-4" not in summary for summary in summaries)
    assert all("2-3 → 0-1" not in summary and "0-1 → 2-3" not in summary for summary in summaries)


def test_contiguous_nested_stroke_keeps_narratives_separate():
    """Carpet-only + slippers spans stay in slippers bands; coarse stays on carpet."""
    carpet = _layer("carpet", "地毯", 3, 400, 200, (40, 40, 280, 120))
    slippers = _layer("slippers", "拖鞋", 1, 400, 200, (100, 60, 80, 60))
    scene = _scene([carpet, slippers])
    result = solve(scene, [(60, 90), (140, 90), (220, 90)])
    summaries = [track["summary"] for track in result["tracks"]]
    labels = {
        segment["label"]
        for track in result["tracks"]
        for segment in track["segments"]
        if segment["relation"] == "band"
    }
    assert labels == {"0-1", "1-2", "2-3", "3-4"}
    assert "0-1" in summaries and "1-2" in summaries
    assert "2-3" in summaries and "3-4" in summaries
    assert all(
        "3-4 → 0-1" not in summary
        and "0-1 → 3-4" not in summary
        and "2-3 → 0-1" not in summary
        and "0-1 → 2-3" not in summary
        for summary in summaries
    )


def test_front_subject_constrains_only_spans_it_participates_in():
    """Sofa and carpet do not overlap. Tea constrains its own span and the neighbor it cuts."""
    sofa = _layer("sofa", "沙发", 3, 400, 300, (40, 20, 220, 110))
    carpet = _layer("carpet", "地毯", 2, 400, 300, (40, 160, 280, 110))
    table = _layer("table", "茶几", 1, 400, 300, (120, 90, 70, 120))
    scene = _scene([sofa, carpet, table], 400, 300)
    # sofa only → carpet only → carpet+tea
    result = solve(scene, [(80, 80), (80, 200), (160, 200)])
    assert result["status"] == "ok"

    def hits_at(x, y):
        best = None
        for sample in result["samples"]:
            if abs(sample["x"] - x) > 8 or abs(sample["y"] - y) > 12:
                continue
            best = tuple(sorted(hit["id"] for hit in sample["hits"]))
        return best

    assert hits_at(80, 80) == ("sofa",)
    assert hits_at(80, 200) == ("carpet",)
    assert hits_at(160, 200) == ("carpet", "table")

    def covering(x, y):
        found = []
        for track in result["tracks"]:
            for segment in track["segments"]:
                if segment["relation"] != "band":
                    continue
                if any(abs(point["x"] - x) <= 8 and abs(point["y"] - y) <= 12 for point in segment["points"]):
                    found.append(segment)
        return found

    # Tea constrains the carpet span it cuts and the span on the tea table.
    for point in ((80, 200), (160, 200)):
        tea_segments = [segment for segment in covering(*point) if "table" in segment["layer_ids"]]
        assert tea_segments
        assert {segment["label"] for segment in tea_segments} <= {"0-1", "1-2"}
    # Rear envelope still reads the tea-table samples as carpet, without tea.
    assert any(
        "carpet" in segment["layer_ids"] and "table" not in segment["layer_ids"]
        for segment in covering(160, 200)
    )
    # Sofa span is outside the tea cut.
    sofa_segments = covering(80, 80)
    assert sofa_segments
    assert all("table" not in segment["layer_ids"] for segment in sofa_segments)
    assert {segment["label"] for segment in sofa_segments} <= {"2-3", "3-4"}


def test_wide_gap_uses_nested_fine_and_rear_coarse_bands():
    """Fully overlapping near+far: fine around near, coarse around far."""
    near = _layer("near", "近处", 1, 200, 80, (0, 0, 200, 80))
    far = _layer("far", "远处", 4, 200, 80, (0, 0, 200, 80))
    result = solve(_scene([near, far], 200, 80), [(20, 40), (180, 40)])
    depths = {
        segment["slot_depth"]
        for track in result["tracks"]
        for segment in track["segments"]
        if segment["slot_depth"] is not None
    }
    labels = {
        segment["label"]
        for track in result["tracks"]
        for segment in track["segments"]
        if segment["relation"] == "band"
    }
    assert depths == {0.5, 1.5, 3.5, 4.5}
    assert labels == {"0-1", "1-2", "3-4", "4-5"}
