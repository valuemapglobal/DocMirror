import math
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SpatialNode:
    """Represents a physical text block or cell on the PDF page."""
    id: str
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


class LayoutGraph:
    """
    Constructs a 2D directed acyclic graph based on BBox proximities.
    Resolves data structures based on relative spatial topological layout
    rather than linear textual strings.
    """

    def __init__(self, nodes: list[SpatialNode]):
        self.nodes = nodes

    def find_node_by_text(self, text_pattern: str) -> SpatialNode | None:
        """Find the first node that exactly matches or contains the pattern."""
        for n in self.nodes:
            if text_pattern in n.text:
                return n
        return None

    def find_nearest_right(self, reference_text: str, y_tolerance: float = 5.0) -> SpatialNode | None:
        """
        Finds the closest node geometrically to the right of the reference text.
        Tolerates slight Y-axis pixel shifts (y_tolerance) typical in PyMuPDF/OCR.
        """
        ref_node = self.find_node_by_text(reference_text)
        if not ref_node:
            return None

        candidates = [
            n for n in self.nodes
            if n.id != ref_node.id
            # Must strictly be to the right of the bounding box
            and n.x0 >= ref_node.x1 - 1.0
            # Must be vertically aligned
            and abs(n.center_y - ref_node.center_y) <= y_tolerance
        ]

        if not candidates:
            return None

        # Return closest node by X-distance
        return min(candidates, key=lambda n: n.x0 - ref_node.x1)

    def find_nearest_below(self, reference_text: str, x_tolerance: float = 15.0) -> SpatialNode | None:
        """
        Finds the closest node geometrically below the reference text.
        """
        ref_node = self.find_node_by_text(reference_text)
        if not ref_node:
            return None

        candidates = [
            n for n in self.nodes
            if n.id != ref_node.id
            # Must stringently be below the bounding box
            and n.y0 >= ref_node.y1 - 1.0
            # Must share horizontal column alignment
            and abs(n.center_x - ref_node.center_x) <= x_tolerance
        ]

        if not candidates:
            return None

        # Return closest node by Y-distance
        return min(candidates, key=lambda n: n.y0 - ref_node.y1)

    def resolve_anchor_value(self, anchor_text: str) -> str | None:
        """
        Intelligently resolves a value for an anchor text.
        First looks right. If not found, looks down.
        """
        right_node = self.find_nearest_right(anchor_text)
        if right_node:
            return right_node.text

        below_node = self.find_nearest_below(anchor_text)
        if below_node:
            return below_node.text

        return None
