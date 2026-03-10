"""
Seal detection与极Coordinates拉直Extract器
based on OpenCV (cv2)

supports两种DetectMode:
1. 彩色Seal: HSV red空间分割 (适合彩色扫描)
2. graySeal: 灰度Threshold + 圆度Filter (适合黑白/灰度扫描)

解决极端弯曲Seal(如银行公章)无法被普通 OCR Recognize的问题。
via cv2.warpPolar 进行极Coordinates变换将其"拉直"为水平文本片段。
"""

import logging
from typing import Optional, Tuple, Dict, Any, List
import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False
    logger.warning("OpenCV is not installed. Seal detection will be skipped.")


class SealDetector:
    """Seal detection与极Coordinates拉直器 — supports彩色与灰度扫描"""

    def __init__(self):
        # red在 HSV 中的两个分布区间
        self.lower_red1 = np.array([0, 50, 50])
        self.upper_red1 = np.array([10, 255, 255])
        self.lower_red2 = np.array([160, 50, 50])
        self.upper_red2 = np.array([180, 255, 255])

    # ─────────────────────────────────────────────────────────────────────────
    # 公共 API
    # ─────────────────────────────────────────────────────────────────────────
    def detect_seal(
        self, image_bgr: np.ndarray
    ) -> Dict[str, Any]:
        """
        DetectSeal并ReturnsDetection result (不做极Coordinates展开)。
        
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

        # 1. Try color (red) seal detection first
        result = self._detect_color_seal(image_bgr)
        if result["has_seal"]:
            return result

        # 2. Fallback to grayscale (B&W scan) seal detection
        return self._detect_gray_seal(image_bgr)

    def unwarp_circular_seal(self, image_bgr: np.ndarray) -> Optional[np.ndarray]:
        """从原图中剥离Seal并将其拉直成水平图 (极Coordinates展开)。"""
        info = self.detect_seal(image_bgr)
        if not info["has_seal"]:
            return None

        try:
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
                flags=cv2.WARP_POLAR_LINEAR | cv2.INTER_LINEAR
            )
            unwarped = cv2.rotate(unwarped, cv2.ROTATE_90_COUNTERCLOCKWISE)
            return unwarped

        except Exception as e:
            logger.error(f"Seal unwarping failed: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # 彩色Seal detection (red HSV)
    # ─────────────────────────────────────────────────────────────────────────
    def _detect_color_seal(self, image_bgr: np.ndarray) -> Dict[str, Any]:
        """HSV red空间分割Detect彩色Seal。"""
        empty = {"has_seal": False, "center": None, "radius": None, "bbox": None, "mode": None}
        try:
            hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
            mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
            mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
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
        except Exception:
            return empty

    # ─────────────────────────────────────────────────────────────────────────
    # 灰度Seal detection (适合黑白扫描)
    # ─────────────────────────────────────────────────────────────────────────
    def _detect_gray_seal(self, image_bgr: np.ndarray) -> Dict[str, Any]:
        """
        灰度圆形Contour detection。
        
        算法:
          1. 将图像转灰度, 高斯模糊去噪
          2. 自适应Threshold + 形态学操作仅retain中gray区域
             (排除纯黑文字和白色Background)
          3. 在Threshold图上查找轮廓, 按圆度 (circularity) Filter
          4. 选取Area最大且圆度 > 0.5 的轮廓作为Seal
        """
        empty = {"has_seal": False, "center": None, "radius": None, "bbox": None, "mode": None}
        try:
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            # 只搜索右上角区域 (Sealtypically在右上角)
            roi_y1, roi_y2 = 0, h // 3
            roi_x1, roi_x2 = w // 2, w
            gray_roi = gray[roi_y1:roi_y2, roi_x1:roi_x2]

            # 高斯模糊降噪
            blurred = cv2.GaussianBlur(gray_roi, (5, 5), 0)

            # Extract中gray区域 (排除纯黑文字 <80 和白色Background >200)
            # Sealtypically是gray (扫描后) ~80-200
            mask = cv2.inRange(blurred, 80, 200)

            # 形态学: 闭运算连接断裂弧段, 开运算去小噪点
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return empty

            # 寻找圆度最高, Area足够大的轮廓
            best = None
            best_score = 0
            min_area = 2000  # 最小AreaThreshold
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

                # 综合评分: Area × 圆度
                score = area * circularity
                if score > best_score:
                    best_score = score
                    best = cnt

            if best is None:
                return empty

            (cx, cy), radius = cv2.minEnclosingCircle(best)
            # 转回全图Coordinates
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


# Singleton提供
_default_seal_detector: Optional[SealDetector] = None

def get_seal_detector() -> SealDetector:
    global _default_seal_detector
    if _default_seal_detector is None:
        _default_seal_detector = SealDetector()
    return _default_seal_detector
