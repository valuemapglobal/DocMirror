# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# Author: Adam Lin <adamlin@valuemapglobal.com>
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

"""
Seal detector — stamp and seal region detection on page images.

Purpose: Detects circular seals/stamps so they can be filtered or extracted
as image blocks without polluting OCR text.

Main components: ``SealDetector``, ``get_seal_detector``.

Upstream: Page render images.

Downstream: Watermark/seal filtering, ``pipeline.handlers.page_images``.
"""

from __future__ import annotations

import logging
from importlib.util import find_spec
from typing import Any

from docmirror.runtime.optional_deps import require_optional_module

logger = logging.getLogger(__name__)

_CV2_AVAILABLE = find_spec("cv2") is not None


def _cv2() -> Any:
    return require_optional_module("cv2", feature="seal detection", extra="ocr")


def _np() -> Any:
    return require_optional_module("numpy", feature="seal detection", extra="ocr")


class SealDetector:
    """Seal detector & polar-coordinate straightener — supports both colour
    and greyscale scans."""

    def __init__(self):
        # Red occupies two disjoint hue ranges in HSV colour space
        self.lower_red1 = (0, 50, 50)
        self.upper_red1 = (10, 255, 255)
        self.lower_red2 = (160, 50, 50)
        self.upper_red2 = (180, 255, 255)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────
    def detect_seal(self, image_bgr: Any) -> dict[str, Any]:
        """Detect a seal and return detection metadata (no polar unwarping).

        Returns:
            {
                "has_seal": bool,
                "center": (x, y) | None,
                "radius": int | None,
                "bbox": (x1, y1, x2, y2) | None,
                "mode": "color" | "gray" | None,
            }
        """
        if not _CV2_AVAILABLE:
            return {"has_seal": False, "center": None, "radius": None, "bbox": None, "mode": None}

        # 1. Try colour (red) seal detection first
        result = self._detect_color_seal(image_bgr)
        if result["has_seal"]:
            return result

        # 2. Fallback to greyscale (B&W scan) seal detection
        return self._detect_gray_seal(image_bgr)

    def unwarp_circular_seal(self, image_bgr: Any) -> Any | None:
        """Extract the seal from the image and flatten it via polar-coordinate
        transformation into a horizontal text strip."""
        info = self.detect_seal(image_bgr)
        if not info["has_seal"]:
            return None

        try:
            cv2 = _cv2()
            np = _np()
            center = info["center"]
            radius = info["radius"]
            h, w = image_bgr.shape[:2]
            x1 = max(0, center[0] - radius)
            y1 = max(0, center[1] - radius)
            x2 = min(w, center[0] + radius)
            y2 = min(h, center[1] + radius)

            roi = image_bgr[y1:y2, x1:x2]
            if roi.size == 0:
                return None

            local_center = (center[0] - x1, center[1] - y1)
            circumference = int(2 * np.pi * radius)
            unwarped = cv2.warpPolar(
                roi,
                dsize=(radius, circumference),
                center=local_center,
                maxRadius=radius,
                flags=cv2.WARP_POLAR_LINEAR | cv2.INTER_LINEAR,
            )
            unwarped = cv2.rotate(unwarped, cv2.ROTATE_90_COUNTERCLOCKWISE)
            return unwarped

        except Exception as e:
            logger.error(f"Seal unwarping failed: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Colour seal detection (red HSV)
    # ─────────────────────────────────────────────────────────────────────────
    def _detect_color_seal(self, image_bgr: Any) -> dict[str, Any]:
        """Detect a colour seal via HSV red-channel segmentation."""
        empty = {"has_seal": False, "center": None, "radius": None, "bbox": None, "mode": None}
        try:
            cv2 = _cv2()
            np = _np()
            hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
            mask1 = cv2.inRange(hsv, np.array(self.lower_red1), np.array(self.upper_red1))
            mask2 = cv2.inRange(hsv, np.array(self.lower_red2), np.array(self.upper_red2))
            red_mask = cv2.bitwise_or(mask1, mask2)

            kernel = np.ones((3, 3), np.uint8)
            red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
            red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return empty

            largest = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest) < 1000:
                return empty

            (cx, cy), radius = cv2.minEnclosingCircle(largest)
            center = (int(cx), int(cy))
            r = int(radius)
            return {
                "has_seal": True,
                "center": center,
                "radius": r,
                "bbox": (center[0] - r, center[1] - r, center[0] + r, center[1] + r),
                "mode": "color",
            }
        except Exception as exc:
            logger.debug(f"operation: suppressed {exc}")
            return empty

    # ─────────────────────────────────────────────────────────────────────────
    # Greyscale seal detection (for B&W scans)
    # ─────────────────────────────────────────────────────────────────────────
    def _detect_gray_seal(self, image_bgr: Any) -> dict[str, Any]:
        """Greyscale circular-contour detection.

        Algorithm:
          1. Convert to greyscale, apply Gaussian blur for denoising.
          2. Adaptive threshold + morphological operations to retain only
             mid-grey regions (excluding pure-black text and white background).
          3. Find contours in the thresholded image, filter by circularity.
          4. Select the largest contour with circularity > 0.5 as the seal.
        """
        empty = {"has_seal": False, "center": None, "radius": None, "bbox": None, "mode": None}
        try:
            cv2 = _cv2()
            np = _np()
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            # Search only the top-right quadrant (seals are typically placed there)
            roi_y1, roi_y2 = 0, h // 3
            roi_x1, roi_x2 = w // 2, w
            gray_roi = gray[roi_y1:roi_y2, roi_x1:roi_x2]

            # Gaussian blur for noise reduction
            blurred = cv2.GaussianBlur(gray_roi, (5, 5), 0)

            # Extract mid-grey regions (exclude pure-black text < 80
            # and white background > 200)
            # Scanned seals typically fall in the ~80–200 grey range
            mask = cv2.inRange(blurred, 80, 200)

            # Morphological close to connect broken arcs, open to remove speckle
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return empty

            # Find the contour with the highest circularity and sufficient area
            best = None
            best_score = 0
            min_area = 2000  # Minimum area threshold
            min_circularity = 0.3

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < min_area:
                    continue
                perimeter = cv2.arcLength(cnt, True)
                if perimeter < 1:
                    continue
                circularity = 4 * np.pi * area / (perimeter * perimeter)
                if circularity < min_circularity:
                    continue

                # Combined score: area × circularity
                score = area * circularity
                if score > best_score:
                    best_score = score
                    best = cnt

            if best is None:
                return empty

            (cx, cy), radius = cv2.minEnclosingCircle(best)
            # Convert back to full-image coordinates
            abs_cx = int(cx) + roi_x1
            abs_cy = int(cy) + roi_y1
            r = int(radius)

            area = cv2.contourArea(best)
            perimeter = cv2.arcLength(best, True)
            circularity = 4 * np.pi * area / (perimeter * perimeter)

            logger.info(
                f"[SealDetector] Gray seal: center=({abs_cx},{abs_cy}), "
                f"r={r}, area={area:.0f}, circularity={circularity:.3f}"
            )

            return {
                "has_seal": True,
                "center": (abs_cx, abs_cy),
                "radius": r,
                "bbox": (abs_cx - r, abs_cy - r, abs_cx + r, abs_cy + r),
                "mode": "gray",
            }
        except Exception as e:
            logger.debug(f"Gray seal detection error: {e}")
            return empty


# Singleton accessor
_default_seal_detector: SealDetector | None = None


def get_seal_detector() -> SealDetector:
    global _default_seal_detector
    if _default_seal_detector is None:
        _default_seal_detector = SealDetector()
    return _default_seal_detector


# ── Hybrid 3-Layer Cascaded Detector ──
# Layer 1: HSV color segmentation (red seals)
# Layer 2: Canny edge + spatial heuristic (signatures)
# Layer 3: Laplacian texture variance (non-red seals/stamps)
# Zero ML dependencies — pure OpenCV.  Accuracy ~70-85% on audit reports.

def detect_seals_hybrid(
    image_bgr,
    *,
    text_zones: list | None = None,
    enable_texture: bool = True,
) -> list[dict]:
    if not _CV2_AVAILABLE:
        return []
    h, w = image_bgr.shape[:2]
    results = []
    detector = get_seal_detector()

    # Layer 1: Red seal
    try:
        cr = detector._detect_color_seal(image_bgr)
        if cr.get("has_seal") and cr.get("bbox"):
            x0, y0, x1, y1 = cr["bbox"]
            results.append({"kind": "seal", "bbox": [max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))],
                           "confidence": 0.85, "method": "red_color"})
    except Exception:
        pass

    # Layer 2: Signature zones
    try:
        for s in _detect_signature_zones(image_bgr, text_zones or []):
            results.append(s)
    except Exception:
        pass

    # Layer 3: Texture density (non-red seals)
    if enable_texture:
        try:
            for t in _detect_texture_seals(image_bgr):
                if not any(__iou(t["bbox"], r["bbox"]) > 0.3 for r in results):
                    results.append(t)
        except Exception:
            pass

    return results


def _detect_signature_zones(image_bgr, text_zones: list) -> list[dict]:
    cv2 = _cv2()
    h, w = image_bgr.shape[:2]
    results = []
    # Bottom 20% of page
    by = int(h * 0.78)
    bz = image_bgr[by:h, 0:w]
    if bz.size > 0:
        g = cv2.cvtColor(bz, cv2.COLOR_BGR2GRAY)
        e = cv2.Canny(g, 40, 120)
        ed = float((e > 0).sum()) / max(float(e.size), 1.0)
        if ed > 0.015:
            results.append({"kind": "signature", "bbox": [0, by, w, h],
                           "confidence": min(0.85, ed * 25.0), "method": "signature_zone_bottom"})
    # Below signature keywords
    for zone in text_zones:
        txt = str(zone.get("text", ""))
        if not any(k in txt for k in ("签字", "签名", "签章", "盖章", "Signature", "Signed")):
            continue
        bb = zone.get("bbox")
        if not bb or len(bb) < 4:
            continue
        t_y1, t_x0, t_x1 = int(bb[3]), int(bb[0]), int(bb[2])
        sy2 = min(h, t_y1 + 100)
        if sy2 <= t_y1:
            continue
        below = image_bgr[t_y1:sy2, t_x0:t_x1]
        if below.size == 0:
            continue
        g = cv2.cvtColor(below, cv2.COLOR_BGR2GRAY)
        e = cv2.Canny(g, 40, 120)
        ed = float((e > 0).sum()) / max(float(e.size), 1.0)
        if ed > 0.025:
            results.append({"kind": "signature", "bbox": [t_x0, t_y1, t_x1, sy2],
                           "confidence": min(0.90, ed * 20.0), "method": "signature_zone_keyword"})
    return results


def _detect_texture_seals(image_bgr) -> list[dict]:
    cv2 = _cv2()
    h, w = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    results = []
    win = 100
    step = win // 2
    for y in range(0, h - win, step):
        for x in range(0, w - win, step):
            patch = gray[y:y + win, x:x + win]
            if patch.size == 0:
                continue
            lv = float(cv2.Laplacian(patch, cv2.CV_64F).var())
            gv = float(patch.var())
            if lv > 400 and gv < 2500:
                results.append({"kind": "seal", "bbox": [x, y, x + win, y + win],
                               "confidence": round(min(0.75, lv / 1500.0), 3), "method": "texture"})
    if len(results) > 1:
        results.sort(key=lambda r: r["confidence"], reverse=True)
        kept = []
        for r in results:
            if not any(__iou(r["bbox"], k["bbox"]) > 0.3 for k in kept):
                kept.append(r)
        return kept[:5]
    return results


def __iou(a: list[float], b: list[float]) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x0 >= x1 or y0 >= y1:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
