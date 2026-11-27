"""Scene graph records: nodes are object instances, edges are undirected pairs.

Each edge is stored once with a canonical orientation ``u -> v``: the nearer
node (smaller depth, then id) is ``u``. Vector-valued fields are antisymmetric;
read them from either end with :meth:`SceneEdge.vector_from`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MetricSource = Literal["manual", "estimated", "unknown"]


def wrap_angle(angle: float) -> float:
    """Wrap to (-180, 180]."""
    wrapped = (angle + 180.0) % 360.0 - 180.0
    return 180.0 if wrapped == -180.0 else wrapped


_DIRECTIONS = ("右", "右上", "上", "左上", "左", "左下", "下", "右下")


def direction_label(angle_deg: float, distance: float) -> str:
    if distance <= 1e-9:
        return "重合"
    index = int(((angle_deg + 22.5) % 360.0) // 45.0) % 8
    return _DIRECTIONS[index]


@dataclass(frozen=True)
class SceneNode:
    id: str
    layer_id: str
    name: str
    category: str
    depth: int
    center: tuple[float, float]
    centroid: tuple[float, float]
    bbox: tuple[float, float, float, float]
    pixel_size: tuple[float, float]
    area_px: float
    metric_width: float | None
    metric_height: float | None
    width_source: MetricSource
    height_source: MetricSource
    annotated: bool

    @property
    def metric_source(self) -> str:
        sources = {self.width_source, self.height_source}
        if len(sources) == 1:
            return sources.pop()
        return "mixed"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "layer_id": self.layer_id,
            "name": self.name,
            "category": self.category,
            "depth": self.depth,
            "center": list(self.center),
            "centroid": list(self.centroid),
            "bbox": list(self.bbox),
            "pixel_size": list(self.pixel_size),
            "area_px": self.area_px,
            "metric": {
                "width": self.metric_width,
                "height": self.metric_height,
                "width_source": self.width_source,
                "height_source": self.height_source,
                "source": self.metric_source,
            },
            "annotated": self.annotated,
        }


@dataclass(frozen=True)
class Occlusion:
    occluded: bool
    occluder: str | None
    overlap_ratio: float
    coplanar_overlap: bool

    def to_dict(self) -> dict:
        return {
            "occluded": self.occluded,
            "occluder": self.occluder,
            "overlap_ratio": self.overlap_ratio,
            "coplanar_overlap": self.coplanar_overlap,
        }


@dataclass(frozen=True)
class SceneEdge:
    u: str
    v: str
    dx: float
    dy: float
    distance: float
    angle_deg: float
    direction: str
    depth_delta: int
    same_layer: bool
    occlusion: Occlusion

    @property
    def id(self) -> str:
        return f"{self.u}--{self.v}"

    def other(self, node_id: str) -> str:
        if node_id == self.u:
            return self.v
        if node_id == self.v:
            return self.u
        raise KeyError(node_id)

    def vector_from(self, node_id: str) -> tuple[float, float, float]:
        """``(dx, dy, angle_deg)`` pointing from ``node_id`` to the other end."""
        if node_id == self.u:
            return self.dx, self.dy, self.angle_deg
        if node_id == self.v:
            return -self.dx, -self.dy, wrap_angle(self.angle_deg + 180.0)
        raise KeyError(node_id)

    def direction_from(self, node_id: str) -> str:
        _, _, angle = self.vector_from(node_id)
        return direction_label(angle, self.distance)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "u": self.u,
            "v": self.v,
            "dx": self.dx,
            "dy": self.dy,
            "distance": self.distance,
            "angle_deg": self.angle_deg,
            "direction": self.direction,
            "depth_delta": self.depth_delta,
            "same_layer": self.same_layer,
            "occlusion": self.occlusion.to_dict(),
        }


@dataclass
class SceneGraph:
    frame: dict
    meters_per_pixel: float | None
    meters_per_pixel_source: Literal["manual", "derived"] | None
    nodes: list[SceneNode]
    edges: list[SceneEdge]
    unmatched_annotations: list[dict] = field(default_factory=list)

    def node(self, node_id: str) -> SceneNode | None:
        return next((node for node in self.nodes if node.id == node_id), None)

    def edge(self, a: str, b: str) -> SceneEdge | None:
        pair = {a, b}
        return next((edge for edge in self.edges if {edge.u, edge.v} == pair), None)

    def neighbors(self, node_id: str) -> list[str]:
        return [edge.other(node_id) for edge in self.edges if node_id in (edge.u, edge.v)]

    def to_dict(self) -> dict:
        return {
            "frame": self.frame,
            "meters_per_pixel": self.meters_per_pixel,
            "meters_per_pixel_source": self.meters_per_pixel_source,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "unmatched_annotations": self.unmatched_annotations,
        }
