from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from PIL import Image, ImageChops, ImageFilter


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


def refine_card_back_corners_to_truth(
    image: Image.Image,
    corners: tuple[tuple[float, float], ...] | list[list[float]],
    truth_image: Image.Image,
    *,
    output_size: tuple[int, int] = (630, 880),
    score_size: tuple[int, int] = (420, 587),
    max_corner_adjust_px: float = 45.0,
) -> tuple[tuple[tuple[float, float], ...], dict[str, Any]]:
    if len(corners) != 4:
        raise ValueError("Card corner refinement requires exactly four card corners")

    ordered = _ordered_corners(tuple((float(point[0]), float(point[1])) for point in corners))
    truth = truth_image.convert("RGB").resize(score_size, Image.Resampling.LANCZOS)
    initial_warp = warp_card_back_image(image, ordered, output_size=score_size)
    initial_score = _truth_similarity_score(initial_warp, truth)
    seed_corners, feature_metrics = _feature_seeded_corners(
        initial_warp,
        truth,
        ordered,
        score_size=score_size,
        max_corner_adjust_px=max_corner_adjust_px,
    )
    seed_score = _truth_similarity_score(warp_card_back_image(image, seed_corners, output_size=score_size), truth)
    if seed_score < initial_score:
        seed_corners = ordered
        seed_score = initial_score
    best_corners, best_score = _coordinate_descent_corners(
        image,
        seed_corners,
        truth,
        score_size=score_size,
        initial_score=seed_score,
        max_corner_adjust_px=max_corner_adjust_px,
        original_corners=ordered,
    )
    ordered_best = _ordered_corners(best_corners)
    return (
        tuple((round(float(x), 2), round(float(y), 2)) for x, y in ordered_best),
        {
            "applied": best_score > initial_score + 0.0005,
            "initial_score": round(initial_score, 5),
            "refined_score": round(best_score, 5),
            "score_delta": round(best_score - initial_score, 5),
            "max_corner_adjust_px": round(_max_corner_delta(ordered, ordered_best), 2),
            "method": "bounded_corner_search",
            "output_size": [output_size[0], output_size[1]],
            "score_size": [score_size[0], score_size[1]],
            "feature_seed": feature_metrics,
        },
    )


def _coordinate_descent_corners(
    image: Image.Image,
    corners: tuple[tuple[float, float], ...],
    truth: Image.Image,
    *,
    score_size: tuple[int, int],
    initial_score: float,
    max_corner_adjust_px: float,
    original_corners: tuple[tuple[float, float], ...] | None = None,
) -> tuple[tuple[tuple[float, float], ...], float]:
    original = tuple((float(x), float(y)) for x, y in (original_corners or corners))
    best = original
    if _max_corner_delta(original, corners) <= max_corner_adjust_px:
        best = tuple((float(x), float(y)) for x, y in corners)
    best_score = initial_score
    for step in (14.0, 7.0, 3.5, 1.75, 0.9):
        improved = True
        while improved:
            improved = False
            for corner_index in range(4):
                for dx, dy in (
                    (step, 0.0),
                    (-step, 0.0),
                    (0.0, step),
                    (0.0, -step),
                    (step, step),
                    (step, -step),
                    (-step, step),
                    (-step, -step),
                ):
                    candidate = [list(point) for point in best]
                    candidate[corner_index][0] += dx
                    candidate[corner_index][1] += dy
                    candidate_tuple = tuple((float(x), float(y)) for x, y in candidate)
                    if _max_corner_delta(original, candidate_tuple) > max_corner_adjust_px:
                        continue
                    score = _truth_similarity_score(
                        warp_card_back_image(image, candidate_tuple, output_size=score_size),
                        truth,
                    )
                    if score > best_score + 0.0005:
                        best = candidate_tuple
                        best_score = score
                        improved = True
    return best, best_score


def _feature_seeded_corners(
    initial_warp: Image.Image,
    truth: Image.Image,
    corners: tuple[tuple[float, float], ...],
    *,
    score_size: tuple[int, int],
    max_corner_adjust_px: float,
) -> tuple[tuple[tuple[float, float], ...], dict[str, Any]]:
    try:
        import cv2
        import numpy as np
    except Exception as exc:  # pragma: no cover - import availability is environment dependent
        return corners, {"applied": False, "reason": f"OpenCV unavailable: {exc}"}

    candidate_gray = cv2.cvtColor(np.array(initial_warp.convert("RGB")), cv2.COLOR_RGB2GRAY)
    truth_gray = cv2.cvtColor(np.array(truth.convert("RGB")), cv2.COLOR_RGB2GRAY)
    detector = cv2.ORB_create(nfeatures=700)
    candidate_keypoints, candidate_descriptors = detector.detectAndCompute(candidate_gray, None)
    truth_keypoints, truth_descriptors = detector.detectAndCompute(truth_gray, None)
    if candidate_descriptors is None or truth_descriptors is None:
        return corners, {"applied": False, "reason": "not_enough_features", "matches": 0}

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw_matches = matcher.knnMatch(candidate_descriptors, truth_descriptors, k=2)
    matches = [
        pair[0]
        for pair in raw_matches
        if len(pair) == 2 and pair[0].distance < pair[1].distance * 0.76
    ]
    if len(matches) < 8:
        return corners, {"applied": False, "reason": "not_enough_matches", "matches": len(matches)}

    source_points = np.float32([candidate_keypoints[match.queryIdx].pt for match in matches]).reshape(-1, 1, 2)
    truth_points = np.float32([truth_keypoints[match.trainIdx].pt for match in matches]).reshape(-1, 1, 2)
    alignment, inlier_mask = cv2.findHomography(source_points, truth_points, cv2.RANSAC, 4.0)
    if alignment is None or inlier_mask is None:
        return corners, {"applied": False, "reason": "homography_failed", "matches": len(matches)}

    width, height = score_size
    source = np.array(_ordered_corners(corners), dtype="float32")
    destination = np.array(
        [
            [0.0, 0.0],
            [float(width - 1), 0.0],
            [float(width - 1), float(height - 1)],
            [0.0, float(height - 1)],
        ],
        dtype="float32",
    )
    initial_matrix = cv2.getPerspectiveTransform(source, destination)
    refined_matrix = alignment @ initial_matrix
    inverse = np.linalg.inv(refined_matrix)
    refined = cv2.perspectiveTransform(destination.reshape(-1, 1, 2), inverse).reshape(4, 2)
    refined_corners = tuple((float(x), float(y)) for x, y in refined)
    if _max_corner_delta(corners, refined_corners) > max_corner_adjust_px:
        return corners, {
            "applied": False,
            "reason": "feature_adjustment_exceeded_limit",
            "matches": len(matches),
            "inliers": int(inlier_mask.sum()),
        }
    return _ordered_corners(refined_corners), {
        "applied": True,
        "matches": len(matches),
        "inliers": int(inlier_mask.sum()),
        "inlier_ratio": round(float(inlier_mask.sum()) / float(len(matches)), 4),
    }


def _truth_similarity_score(candidate: Image.Image, truth: Image.Image) -> float:
    candidate = candidate.convert("RGB").resize(truth.size, Image.Resampling.LANCZOS)
    candidate_edges = candidate.convert("L").filter(ImageFilter.FIND_EDGES)
    truth_edges = truth.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_error = _mean_image_error(ImageChops.difference(candidate_edges, truth_edges))
    color_error = _mean_image_error(ImageChops.difference(candidate, truth))
    return max(0.0, 1.0 - (edge_error * 0.65 + color_error * 0.35))


def _mean_image_error(diff: Image.Image) -> float:
    histogram = diff.histogram()
    channels = max(1, len(histogram) // 256)
    pixels = max(1, diff.width * diff.height * channels)
    mean_error = sum((index % 256) * count for index, count in enumerate(histogram)) / float(pixels * 255)
    return mean_error


def _max_corner_delta(
    first: tuple[tuple[float, float], ...],
    second: tuple[tuple[float, float], ...],
) -> float:
    return max((_distance(a, b) for a, b in zip(first, second)), default=0.0)


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
