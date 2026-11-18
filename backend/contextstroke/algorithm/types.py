"""Shared dataclasses for stroke classification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hit:
    id: str
    name: str
    depth: int


@dataclass
class Sample:
    x: float
    y: float
    on: bool
    hits: list[Hit]


@dataclass(frozen=True)
class Slot:
    slot_depth: float
    relation: str
    layer_ids: tuple[str, ...]
    label: str


@dataclass(frozen=True)
class Run:
    start: int
    end: int
    slots: tuple[Slot, ...]
