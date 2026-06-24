from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from PIL import Image


CARD_ASPECT_WIDTH_OVER_HEIGHT = 63.0 / 88.0


@dataclass(frozen=True)
class CardBackDetection:
    found: bool
    confidence: float
    image_width: int
    image_height: int
    center_px: tuple[float, float] | None
    component_bbox_px: tuple[float, float, float, float] | None
    estimated_card_bbox_px: tuple[float, float, float, float] | None
    corners_px: tuple[tuple[float, float], ...]
    rotation_degrees: float | None
    skew_degrees: float | None
    area_fraction: float
    message: str

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["corners_px"] = [list(point) for point in self.corners_px]
        if self.center_px is not None:
            payload["center_px"] = list(self.center_px)
        if self.component_bbox_px is not None:
            payload["component_bbox_px"] = list(self.component_bbox_px)
        if self.estimated_card_bbox_px is not None:
            payload["estimated_card_bbox_px"] = list(self.estimated_card_bbox_px)
        return payload


def detect_card_back(image: Image.Image) -> CardBackDetection:
    try:
        import cv2
        import numpy as np
    except Exception as exc:  # pragma: no cover - import availability is environment dependent
        width, height = image.size
        return CardBackDetection(
            found=False,
            confidence=0.0,
            image_width=width,
            image_height=height,
            center_px=None,
            component_bbox_px=None,
            estimated_card_bbox_px=None,
            corners_px=(),
            rotation_degrees=None,
            skew_degrees=None,
            area_fraction=0.0,
            message=f"OpenCV is required for card-back detection: {exc}",
        )

    rgb = image.convert("RGB")
    frame = np.array(rgb)
    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    hue, saturation, value = cv2.split(hsv)
    warm_mask = (
        (saturation > 35)
        & (value > 65)
        & (((hue >= 3) & (hue <= 35)) | (hue >= 170))
    )
    mask = warm_mask.astype("uint8") * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    image_area = float(width * height)
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < image_area * 0.01:
            continue
        x, y, box_width, box_height = cv2.boundingRect(contour)
        if box_width <= 0 or box_height <= 0:
            continue
        fill = area / float(box_width * box_height)
        portrait_ratio = box_height / float(box_width)
        portrait_score = max(0.0, 1.0 - abs(portrait_ratio - (88.0 / 63.0)) / (88.0 / 63.0))
        area_fraction = area / image_area
        touches_frame = int(x <= 2) + int(y <= 2) + int(x + box_width >= width - 2) + int(y + box_height >= height - 2)
        score = (area_fraction * 3.5 + fill * 0.35 + portrait_score * 0.45) / (1.0 + touches_frame)
        if best is None or score > best["score"]:
            best = {
                "score": score,
                "contour": contour,
                "area": area,
                "bbox": (float(x), float(y), float(x + box_width), float(y + box_height)),
                "fill": fill,
                "portrait_score": portrait_score,
                "area_fraction": area_fraction,
            }

    if best is None:
        return CardBackDetection(
            found=False,
            confidence=0.0,
            image_width=width,
            image_height=height,
            center_px=None,
            component_bbox_px=None,
            estimated_card_bbox_px=None,
            corners_px=(),
            rotation_degrees=None,
            skew_degrees=None,
            area_fraction=0.0,
            message="No Magic card-back shaped color region found",
        )

    rect = cv2.minAreaRect(best["contour"])
    component_corners = tuple((float(x), float(y)) for x, y in cv2.boxPoints(rect))
    expanded_corners = _expanded_card_corners(component_corners)
    corners = tuple((round(float(x), 2), round(float(y), 2)) for x, y in expanded_corners)
    component_bbox = best["bbox"]
    estimated_bbox = _bbox_from_corners(expanded_corners, width, height)
    center = (
        round((estimated_bbox[0] + estimated_bbox[2]) / 2.0, 2),
        round((estimated_bbox[1] + estimated_bbox[3]) / 2.0, 2),
    )
    rotation = _rotation_from_corners(corners)
    confidence = min(
        0.99,
        max(
            0.0,
            (best["portrait_score"] * 0.42)
            + (min(best["fill"], 0.8) / 0.8 * 0.28)
            + (min(best["area_fraction"], 0.16) / 0.16 * 0.30),
        ),
    )
    return CardBackDetection(
        found=confidence >= 0.45,
        confidence=round(confidence, 4),
        image_width=width,
        image_height=height,
        center_px=center,
        component_bbox_px=tuple(round(value, 2) for value in component_bbox),
        estimated_card_bbox_px=tuple(round(value, 2) for value in estimated_bbox),
        corners_px=corners,
        rotation_degrees=round(rotation, 3),
        skew_degrees=round(abs(rotation), 3),
        area_fraction=round(best["area_fraction"], 5),
        message="Card back found" if confidence >= 0.45 else "Low-confidence card-back candidate found",
    )


def warp_card_back_image(
    image: Image.Image,
    corners: tuple[tuple[float, float], ...] | list[list[float]],
    *,
    output_size: tuple[int, int] = (630, 880),
) -> Image.Image:
    import cv2
    import numpy as np

    if len(corners) != 4:
        raise ValueError("Card warp requires exactly four card corners")
    ordered = _ordered_corners(tuple((float(point[0]), float(point[1])) for point in corners))
    width, height = output_size
    source = np.array(ordered, dtype="float32")
    destination = np.array(
        [
            [0.0, 0.0],
            [float(width - 1), 0.0],
            [float(width - 1), float(height - 1)],
            [0.0, float(height - 1)],
        ],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(np.array(image.convert("RGB")), matrix, (width, height))
    return Image.fromarray(warped)


def _expanded_card_corners(corners: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    top_left, top_right, bottom_right, bottom_left = _ordered_corners(corners)
    left_height = _distance(top_left, bottom_left)
    right_height = _distance(top_right, bottom_right)
    card_height = max(left_height, right_height)
    top_width = _distance(top_left, top_right)
    bottom_width = _distance(bottom_left, bottom_right)
    current_width = max(1.0, (top_width + bottom_width) / 2.0)
    target_width = card_height * CARD_ASPECT_WIDTH_OVER_HEIGHT
    if target_width <= current_width:
        return (top_left, top_right, bottom_right, bottom_left)

    right_mid = ((top_right[0] + bottom_right[0]) / 2.0, (top_right[1] + bottom_right[1]) / 2.0)
    left_mid = ((top_left[0] + bottom_left[0]) / 2.0, (top_left[1] + bottom_left[1]) / 2.0)
    left_direction = _unit((left_mid[0] - right_mid[0], left_mid[1] - right_mid[1]))
    extra_width = target_width - current_width
    expanded_top_left = (
        top_left[0] + left_direction[0] * extra_width,
        top_left[1] + left_direction[1] * extra_width,
    )
    expanded_bottom_left = (
        bottom_left[0] + left_direction[0] * extra_width,
        bottom_left[1] + left_direction[1] * extra_width,
    )
    return (expanded_top_left, top_right, bottom_right, expanded_bottom_left)


def _bbox_from_corners(
    corners: tuple[tuple[float, float], ...],
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    x_values = [point[0] for point in corners]
    y_values = [point[1] for point in corners]
    return (
        max(0.0, min(x_values)),
        max(0.0, min(y_values)),
        min(float(image_width), max(x_values)),
        min(float(image_height), max(y_values)),
    )


def _rotation_from_corners(corners: tuple[tuple[float, float], ...]) -> float:
    if len(corners) != 4:
        return 0.0
    top_left, top_right, _, _ = _ordered_corners(corners)
    dx = top_right[0] - top_left[0]
    dy = top_right[1] - top_left[1]
    if dx == 0 and dy == 0:
        return 0.0
    angle = math.degrees(math.atan2(dy, dx))
    if angle > 45:
        angle -= 90
    if angle < -45:
        angle += 90
    return angle


def _ordered_corners(corners: tuple[tuple[float, float], ...]) -> tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]:
    ordered = sorted(corners, key=lambda point: point[1])
    top_left, top_right = sorted(ordered[:2], key=lambda point: point[0])
    bottom_left, bottom_right = sorted(ordered[2:], key=lambda point: point[0])
    return top_left, top_right, bottom_right, bottom_left


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _unit(vector: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(vector[0], vector[1])
    if length <= 0.0001:
        return (-1.0, 0.0)
    return (vector[0] / length, vector[1] / length)
