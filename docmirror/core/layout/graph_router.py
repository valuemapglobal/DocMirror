"""
Graph-based Semantic Router
=============================================

DeepSeek-OCR 2 的One core concept is Visual Causal Flow (VCF)，abandoning rigid top-to-bottom scanning,
转而based on各视觉块的Association建立“拓扑Sort流”。
Lightweight Graph Router designed for DocMirror, replacing traditional y-band hard splitting:
1. Spatial Graph Construction (2D connectivity graph)
2. Sidebar Penalization (outlier node suppression)
3. Causal Reading Sequence (topological sort output)
"""

import math
from typing import List, Tuple, Dict, Set, Any, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# To avoid circular imports, we reference the Zone structure from layout_analysis
# Used only for type hints，duck typing with bbox and type also works

class GraphRouter:
    def __init__(self, page_width: float, page_height: float):
        self.page_width = page_width
        self.page_height = page_height

    def _get_center(self, bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
        x0, y0, x1, y1 = bbox
        return (x0 + x1) / 2, (y0 + y1) / 2

    def _is_sidebar(self, bbox: Tuple[float, float, float, float]) -> bool:
        """Heuristically determine if a block is a sidebar or extreme header/footer."""
        x0, y0, x1, y1 = bbox
        w = x1 - x0
        cx, cy = self._get_center(bbox)
        
        # Narrow vertical elements
        if w < self.page_width * 0.15 and (cx < self.page_width * 0.15 or cx > self.page_width * 0.85):
            return True
        return False

    def _detect_columns(self, zones: List[Any]) -> List[int]:
        """Detect column structure (single/double/triple column).

        Determines column count by clustering zone center x-coordinates.
        Returns column number for each zone (0-based, left to right).

        For single-column docs all zones return column 0 — no effect.
        """
        if not zones:
            return []

        # Collect center x-coordinates of non-sidebar zones
        cx_list = []
        for z in zones:
            x0, y0, x1, y1 = z.bbox
            w = x1 - x0
            # Skip blocks wider than 60% of page (cross-column titles, etc.)
            if w > self.page_width * 0.6:
                cx_list.append(None)
            else:
                cx_list.append((x0 + x1) / 2)

        # Filter valid center points
        valid_cx = [cx for cx in cx_list if cx is not None]
        if len(valid_cx) < 2:
            return [0] * len(zones)

        # Simple clustering: find significant gaps after sorting by x-coordinate
        sorted_cx = sorted(valid_cx)
        gaps = []
        for i in range(1, len(sorted_cx)):
            gap = sorted_cx[i] - sorted_cx[i-1]
            if gap > self.page_width * 0.15:  # Gap exceeding 15% of page width is treated as column separator
                gaps.append((sorted_cx[i-1] + sorted_cx[i]) / 2)

        if not gaps:
            return [0] * len(zones)

        # Limit to max 3 columns
        gaps = gaps[:2]

        # Assign column number to each zone
        columns = []
        for cx in cx_list:
            if cx is None:
                # Cross-column block: assign to first column (processed first)
                columns.append(-1)
            else:
                col = 0
                for g in gaps:
                    if cx > g:
                        col += 1
                columns.append(col)

        num_cols = len(gaps) + 1
        if num_cols > 1:
            logger.debug(f"[GraphRouter] Detected {num_cols}-column layout")

        return columns

    def build_flow(self, zones: List[Any], reading_order_model=None,
                   enable_column_detection: bool = True) -> List[Any]:
        """
        Graph-based topological sort of zones by semantic priority and spatial relations.
        No longer relying solely on top/bottom y-band interception.

        Args:
            zones: Zone list.
            reading_order_model: Optional layoutreader model path or "auto".
            enable_column_detection: Whether to enable explicit column detection. Default True.
                No effect on single-column docs, significantly improves reading order for multi-column.
        """
        if not zones:
            return []
            
        n = len(zones)
        if n == 1:
            return zones

        # ── Model branch: layoutreader ──
        if reading_order_model:
            model_result = self._model_reading_order(zones, reading_order_model)
            if model_result is not None:
                return model_result

        # 1. Build adjacency graph
        # Edge direction means "A -> should be read before -> B"
        adj: Dict[int, Set[int]] = defaultdict(set)
        in_degree: Dict[int, int] = defaultdict(int)
        
        # Pre-compute attributes
        is_sidebar = [self._is_sidebar(z.bbox) for z in zones]

        # Column detection (All zones return 0 for single-column docs — no effect)
        columns = self._detect_columns(zones) if enable_column_detection else [0] * n
        
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                
                z_i = zones[i]
                z_j = zones[j]
                x0_i, y0_i, x1_i, y1_i = z_i.bbox
                x0_j, y0_j, x1_j, y1_j = z_j.bbox
                
                cy_i = (y0_i + y1_i) / 2
                cy_j = (y0_j + y1_j) / 2
                
                # Causal Constraints (Causal directed edge construction)

                # Rule 0: Cross-column titles precede column content
                if columns[i] == -1 and columns[j] >= 0:
                    if y1_i < y0_j + 15:
                        adj[i].add(j)
                        continue
                
                # Rule A: Main content precedes sidebar at same vertical level (Penalty logic)
                if is_sidebar[j] and not is_sidebar[i]:
                    # Within same height band, main content must precede sidebar
                    if abs(cy_i - cy_j) < self.page_height * 0.2:
                        adj[i].add(j)
                        continue
                
                # Rule B: Significantly above takes precedence over below
                if y1_i < y0_j + 15:  # i bottom is still at j clearly above top
                    adj[i].add(j)
                    continue
                    
                # Rule C: Horizontal column case (left precedes right)
                # When their heights significantly overlap
                y_overlap = max(0, min(y1_i, y1_j) - max(y0_i, y0_j))
                h_i, h_j = y1_i - y0_i, y1_j - y0_j
                if y_overlap > min(h_i, h_j) * 0.4:  # 40% overlap treated as same column level
                    if x1_i < x0_j + 15:  # i to the left of j
                        adj[i].add(j)
                        
        # Calculate入度
        for i in range(n):
            in_degree[i] = 0 # Initializeall节点
        for u in adj:
            for v in adj[u]:
                in_degree[v] += 1

        # 2. 拓扑Sort (Kahn's Algorithm)
        # 用优先Queue（堆）来做拓扑Sort的决胜局
        # 权重: 栏号 > type 语义 > y 轴Height
        import heapq
        
        _ZONE_ORDER = {
            "title": 0, 
            "summary": 1, 
            "data_table": 2,
            "formula": 2,
            "unknown": 3, 
            "footer": 4
        }
        
        # Queue item: (column, type_weight, y_position, index)
        queue = []
        for i in range(n):
            if in_degree[i] == 0:
                col = max(0, columns[i])  # -1 (跨栏) → 0 (最先)
                qw = _ZONE_ORDER.get(zones[i].type, 3)
                heapq.heappush(queue, (col, qw, zones[i].bbox[1], i))
                
        sorted_indices = []
        
        while queue:
            _, _, _, u = heapq.heappop(queue)
            sorted_indices.append(u)
            
            for v in adj[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    col = max(0, columns[v])
                    qw = _ZONE_ORDER.get(zones[v].type, 3)
                    heapq.heappush(queue, (col, qw, zones[v].bbox[1], v))
        
        # 兜底：如果存在环 (Cycle)，Downgrade to原始 Y 轴+语义双键Sort
        if len(sorted_indices) != n:
            logger.debug("[v2] Graph Router detected cycle, falling back to static sort.")
            return sorted(zones, key=lambda z: (_ZONE_ORDER.get(z.type, 3), z.bbox[1]))
            
        logger.debug(f"[v2] Graph Router applied successfully. Visual Causal Flow established.")
        return [zones[i] for i in sorted_indices]

    def _model_reading_order(self, zones: List[Any], model_path: str) -> Optional[List[Any]]:
        """using layoutreader 模型预测Reading order。

        Args:
            zones: Zone list.
            model_path: HuggingFace 模型Path或 "auto"。

        Returns:
            Sort后的 Zone List，或 None (Failed时Fallback到图Method)。
        """
        try:
            from transformers import LayoutLMv3ForTokenClassification, LayoutLMv3Tokenizer
            import torch
        except ImportError:
            logger.debug("[GraphRouter] transformers/torch not available, using graph fallback")
            return None

        try:
            repo_id = "hantian/layoutreader" if model_path == "auto" else model_path

            if not hasattr(self, '_layoutreader_model'):
                self._layoutreader_model = LayoutLMv3ForTokenClassification.from_pretrained(repo_id)
                self._layoutreader_tokenizer = LayoutLMv3Tokenizer.from_pretrained(repo_id)
                self._layoutreader_model.eval()
                logger.info(f"[GraphRouter] Loaded layoutreader from {repo_id}")

            # 准备 bbox Input (归一化到 0-1000)
            bboxes = []
            for z in zones:
                x0, y0, x1, y1 = z.bbox
                norm_bbox = [
                    max(0, int(x0 / self.page_width * 1000)),
                    max(0, int(y0 / self.page_height * 1000)),
                    min(1000, int(x1 / self.page_width * 1000)),
                    min(1000, int(y1 / self.page_height * 1000)),
                ]
                bboxes.append(norm_bbox)

            # 简化Input: each zone 一个 token
            words = [f"zone{i}" for i in range(len(zones))]

            encoding = self._layoutreader_tokenizer(
                words,
                boxes=bboxes,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )

            with torch.no_grad():
                outputs = self._layoutreader_model(**encoding)

            # 预测的Result是each token 的Reading order标签
            logits = outputs.logits
            predictions = logits.argmax(-1).squeeze().tolist()

            if isinstance(predictions, int):
                predictions = [predictions]

            # 去掉 [CLS] 和 [SEP] 标记的预测
            # 实际 token 对应 predictions[1:-1]
            zone_orders = predictions[1:len(zones)+1]

            # 按照预测的Reading orderSort
            indexed_zones = list(enumerate(zones))
            indexed_zones.sort(key=lambda x: zone_orders[x[0]] if x[0] < len(zone_orders) else 999)

            sorted_zones = [z for _, z in indexed_zones]
            logger.info(f"[GraphRouter] Model reading order applied: {len(sorted_zones)} zones")
            return sorted_zones

        except Exception as e:
            logger.warning(f"[GraphRouter] model reading order failed: {e}, using graph fallback")
            return None
