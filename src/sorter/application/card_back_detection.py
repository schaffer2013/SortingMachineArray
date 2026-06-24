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


def refine_card_back_corners_to_truth(
    image: Image.Image,
    corners: tuple[tuple[float, float], ...] | list[list[float]],
    truth_image: Image.Image,
    *,
    output_size: tuple[int, int] = (630, 880),
    score_size: tuple[int, int] = (315, 440),
    max_corner_adjust_px: float = 45.0,
) -> tuple[tuple[tuple[float, float], ...], dict[str, Any]]:
    if len(corners) != 4:
        raise ValueError("Card corner refinement requires exactly four card corners")

    import numpy as np

    ordered = _ordered_corners(tuple((float(point[0]), float(point[1])) for point in corners))
    truth = truth_image.convert("RGB").resize(score_size, Image.Resampling.LANCZOS)
    source_rgb = np.array(image.convert("RGB"))
    truth_rgb = np.array(truth)
    initial_warp_rgb = _warp_card_back_rgb_array(source_rgb, ordered, output_size=score_size)
    truth_circles = _detect_center_circles(truth_rgb)
    initial_score, initial_circle_metrics = _circle_truth_score(initial_warp_rgb, truth_rgb, truth_circles)
    seed_corners, seed_metrics = _circle_seeded_corners(
        initial_warp_rgb,
        ordered,
        truth_circles,
        score_size=score_size,
        max_corner_adjust_px=max_corner_adjust_px,
    )
    seed_score, _ = _circle_truth_score(
        _warp_card_back_rgb_array(source_rgb, seed_corners, output_size=score_size),
        truth_rgb,
        truth_circles,
    )
    if seed_score < initial_score:
        seed_corners = ordered
        seed_metrics = {"applied": False, "reason": "circle_seed_did_not_improve"}
    best_corners, best_score = _coordinate_descent_corners(
        source_rgb,
        seed_corners,
        truth_rgb,
        truth_circles,
        score_size=score_size,
        initial_score=initial_score,
        max_corner_adjust_px=max_corner_adjust_px,
        original_corners=ordered,
    )
    best_warp_rgb = _warp_card_back_rgb_array(source_rgb, best_corners, output_size=score_size)
    _, final_circle_metrics = _circle_truth_score(best_warp_rgb, truth_rgb, truth_circles)
    ordered_best = _ordered_corners(best_corners)
    return (
        tuple((round(float(x), 2), round(float(y), 2)) for x, y in ordered_best),
        {
            "applied": best_score > initial_score + 0.0005,
            "initial_score": round(initial_score, 5),
            "refined_score": round(best_score, 5),
            "score_delta": round(best_score - initial_score, 5),
            "max_corner_adjust_px": round(_max_corner_delta(ordered, ordered_best), 2),
            "corner_regularization_penalty": round(_corner_regularization_penalty(ordered, ordered_best, max_corner_adjust_px), 5),
            "method": "bounded_center_circle_search",
            "output_size": [output_size[0], output_size[1]],
            "score_size": [score_size[0], score_size[1]],
            "circle_seed": seed_metrics,
            "initial_circle_fit": initial_circle_metrics,
            "final_circle_fit": final_circle_metrics,
        },
    )


def _coordinate_descent_corners(
    source_rgb: Any,
    corners: tuple[tuple[float, float], ...],
    truth_rgb: Any,
    truth_circles: tuple[tuple[float, float, float], ...],
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
    for step in (14.0, 7.0, 3.5, 1.75):
        for _ in range(2):
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
                    raw_score, _ = _circle_truth_score(
                        _warp_card_back_rgb_array(source_rgb, candidate_tuple, output_size=score_size),
                        truth_rgb,
                        truth_circles,
                    )
                    score = raw_score - _corner_regularization_penalty(original, candidate_tuple, max_corner_adjust_px)
                    if score > best_score + 0.0005:
                        best = candidate_tuple
                        best_score = score
                        improved = True
            if not improved:
                break
    return best, best_score


def _circle_seeded_corners(
    initial_warp_rgb: Any,
    corners: tuple[tuple[float, float], ...],
    truth_circles: tuple[tuple[float, float, float], ...],
    *,
    score_size: tuple[int, int],
    max_corner_adjust_px: float,
) -> tuple[tuple[tuple[float, float], ...], dict[str, Any]]:
    import cv2
    import numpy as np

    candidate_circles = _detect_center_circles(initial_warp_rgb)
    candidate_points, truth_points, mean_error = _best_circle_center_match(candidate_circles, truth_circles)
    if candidate_points is None or truth_points is None:
        return corners, {"applied": False, "reason": "not_enough_circle_matches"}
    affine, inlier_mask = cv2.estimateAffinePartial2D(
        np.array(candidate_points, dtype="float32").reshape(-1, 1, 2),
        np.array(truth_points, dtype="float32").reshape(-1, 1, 2),
        method=cv2.LMEDS,
    )
    if affine is None:
        return corners, {"applied": False, "reason": "circle_affine_failed", "mean_center_error_px": round(mean_error, 2)}
    alignment = np.vstack([affine, [0.0, 0.0, 1.0]])

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
    refined = cv2.perspectiveTransform(destination.reshape(-1, 1, 2), np.linalg.inv(refined_matrix)).reshape(4, 2)
    refined_corners = _ordered_corners(tuple((float(x), float(y)) for x, y in refined))
    max_delta = _max_corner_delta(corners, refined_corners)
    if max_delta > max_corner_adjust_px:
        return corners, {
            "applied": False,
            "reason": "circle_adjustment_exceeded_limit",
            "mean_center_error_px": round(mean_error, 2),
            "max_corner_adjust_px": round(max_delta, 2),
        }
    return refined_corners, {
        "applied": True,
        "mean_center_error_px": round(mean_error, 2),
        "max_corner_adjust_px": round(max_delta, 2),
        "inliers": None if inlier_mask is None else int(inlier_mask.sum()),
    }


def _warp_card_back_rgb_array(
    source_rgb: Any,
    corners: tuple[tuple[float, float], ...],
    *,
    output_size: tuple[int, int],
) -> Any:
    import cv2
    import numpy as np

    ordered = _ordered_corners(corners)
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
    return cv2.warpPerspective(source_rgb, matrix, (width, height))


def _circle_truth_score(
    candidate_rgb: Any,
    truth_rgb: Any,
    truth_circles: tuple[tuple[float, float, float], ...],
) -> tuple[float, dict[str, Any]]:
    candidate_circles = _detect_center_circles(candidate_rgb)
    circle_score, mean_error = _circle_center_score(candidate_circles, truth_circles)
    texture_score = _texture_similarity_score(candidate_rgb, truth_rgb)
    score = circle_score * 0.88 + texture_score * 0.12
    return score, {
        "truth_circle_count": len(truth_circles),
        "detected_circle_count": len(candidate_circles),
        "mean_center_error_px": None if mean_error is None else round(mean_error, 2),
        "circle_score": round(circle_score, 5),
        "texture_score": round(texture_score, 5),
        "truth_centers_px": [[round(x, 2), round(y, 2)] for x, y, _ in truth_circles],
        "detected_centers_px": [[round(x, 2), round(y, 2)] for x, y, _ in candidate_circles],
    }


def _detect_center_circles(rgb: Any) -> tuple[tuple[float, float, float], ...]:
    import cv2
    import numpy as np

    height, width = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 1.5)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(18, int(width * 0.08)),
        param1=60,
        param2=14,
        minRadius=max(3, int(width * 0.012)),
        maxRadius=max(8, int(width * 0.04)),
    )
    if circles is None:
        return ()

    candidates: list[tuple[float, float, float]] = []
    min_x = width * 0.25
    max_x = width * 0.75
    min_y = height * 0.42
    max_y = height * 0.74
    for x, y, radius in circles[0]:
        if min_x <= x <= max_x and min_y <= y <= max_y:
            candidates.append((float(x), float(y), float(radius)))
    if len(candidates) <= 5:
        return tuple(sorted(candidates, key=lambda circle: (circle[1], circle[0])))

    expected_center = np.array([width * 0.5, height * 0.57])
    candidates.sort(key=lambda circle: abs(circle[2] - width * 0.028) + np.linalg.norm(np.array(circle[:2]) - expected_center) * 0.01)
    selected = candidates[:5]
    return tuple(sorted(selected, key=lambda circle: (circle[1], circle[0])))


def _circle_center_score(
    candidate_circles: tuple[tuple[float, float, float], ...],
    truth_circles: tuple[tuple[float, float, float], ...],
) -> tuple[float, float | None]:
    _, _, best_error = _best_circle_center_match(candidate_circles, truth_circles)
    if best_error is None:
        return 0.0, None
    return max(0.0, 1.0 - best_error / 35.0), best_error


def _best_circle_center_match(
    candidate_circles: tuple[tuple[float, float, float], ...],
    truth_circles: tuple[tuple[float, float, float], ...],
) -> tuple[list[tuple[float, float]] | None, list[tuple[float, float]] | None, float | None]:
    import itertools

    if len(candidate_circles) < 5 or len(truth_circles) < 5:
        return None, None, None
    candidate_centers = [(x, y) for x, y, _ in candidate_circles[:5]]
    truth_centers = [(x, y) for x, y, _ in truth_circles[:5]]
    best_error: float | None = None
    best_permutation: tuple[tuple[float, float], ...] | None = None
    for permutation in itertools.permutations(candidate_centers, len(truth_centers)):
        error = sum(_distance(candidate, truth) for candidate, truth in zip(permutation, truth_centers)) / len(truth_centers)
        if best_error is None or error < best_error:
            best_error = error
            best_permutation = permutation
    assert best_error is not None
    assert best_permutation is not None
    return list(best_permutation), truth_centers, best_error


def _corner_regularization_penalty(
    original: tuple[tuple[float, float], ...],
    candidate: tuple[tuple[float, float], ...],
    max_corner_adjust_px: float,
) -> float:
    if max_corner_adjust_px <= 0:
        return 0.0
    return min(0.12, 0.08 * (_max_corner_delta(original, candidate) / max_corner_adjust_px))


def _texture_similarity_score(candidate_rgb: Any, truth_rgb: Any) -> float:
    import cv2
    import numpy as np

    candidate_gray = cv2.cvtColor(candidate_rgb, cv2.COLOR_RGB2GRAY)
    truth_gray = cv2.cvtColor(truth_rgb, cv2.COLOR_RGB2GRAY)
    candidate_edges = cv2.Canny(candidate_gray, 60, 140)
    truth_edges = cv2.Canny(truth_gray, 60, 140)
    edge_error = float(np.mean(cv2.absdiff(candidate_edges, truth_edges))) / 255.0
    color_error = float(np.mean(cv2.absdiff(candidate_rgb, truth_rgb))) / 255.0
    return max(0.0, 1.0 - (edge_error * 0.55 + color_error * 0.45))


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
