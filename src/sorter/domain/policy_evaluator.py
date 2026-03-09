from __future__ import annotations

from sorter.domain.models import CardMeta
from sorter.domain.sort_fields import derive_fields
from sorter.domain.sort_policy_config import SortCriterion, SortPolicyConfig, ThresholdBucket


def build_sort_key(card_meta: CardMeta, policy_config: SortPolicyConfig) -> tuple:
    derived_fields = derive_fields(card_meta)
    criterion_keys = tuple(
        _criterion_key(card_meta, derived_fields, criterion)
        for criterion in policy_config.criteria
    )
    # Add a deterministic tie-breaker so rank assignment is stable.
    return criterion_keys + ((_normalize_text(card_meta.name),),)


def _criterion_key(card_meta: CardMeta, derived_fields: dict[str, object], criterion: SortCriterion) -> tuple:
    value = _field_value(card_meta, derived_fields, criterion.field)

    if criterion.kind == "category_rank":
        return _category_rank_key(value, criterion)
    if criterion.kind == "numeric":
        return _numeric_key(value, criterion)
    if criterion.kind == "threshold_bucket":
        return _threshold_bucket_key(value, criterion)
    if criterion.kind == "alpha":
        return _alpha_key(value, ignore_leading_article=(criterion.field == "name"))

    raise ValueError(f"Unsupported criterion kind: {criterion.kind}")


def _field_value(card_meta: CardMeta, derived_fields: dict[str, object], field: str) -> object:
    if field in derived_fields:
        return derived_fields[field]
    if not hasattr(card_meta, field):
        return None
    return getattr(card_meta, field)


def _category_rank_key(value: object, criterion: SortCriterion) -> tuple[int, int, str]:
    mapping = {label: index for index, label in enumerate(criterion.order or [])}
    normalized = _normalize_text(value)
    if not normalized:
        missing_flag = 1 if criterion.missing_last else 0
        return (missing_flag, len(mapping), "")

    if normalized in mapping:
        return (0, mapping[normalized], normalized)

    unknown_flag = 1 if criterion.unknown_last else 0
    return (unknown_flag, len(mapping), normalized)


def _numeric_key(value: object, criterion: SortCriterion) -> tuple[int, float]:
    number = _to_float(value)
    if number is None:
        missing_flag = 1 if criterion.missing_last else 0
        return (missing_flag, 0.0)

    transformed = -number if criterion.direction == "desc" else number
    return (0, transformed)


def _threshold_bucket_key(value: object, criterion: SortCriterion) -> tuple[int, int, str]:
    mapping = {label: index for index, label in enumerate(criterion.order or [])}
    number = _to_float(value)

    if number is None:
        chosen = _normalize_text(criterion.missing_bucket)
    else:
        chosen = _match_threshold_bucket(number, criterion.buckets or [])

    if chosen in mapping:
        return (0, mapping[chosen], chosen)

    unknown_flag = 1 if criterion.unknown_last else 0
    return (unknown_flag, len(mapping), chosen)


def _alpha_key(value: object, ignore_leading_article: bool = False) -> tuple[int, str]:
    normalized = _normalize_text(value)
    if ignore_leading_article:
        normalized = _strip_leading_article(normalized)
    if not normalized:
        return (1, "")
    return (0, normalized)


def _strip_leading_article(value: str) -> str:
    for prefix in ("the ", "an ", "a "):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _match_threshold_bucket(number: float, buckets: list[ThresholdBucket]) -> str:
    for bucket in buckets:
        if _matches_bucket(number, bucket):
            return bucket.label
    return ""


def _matches_bucket(number: float, bucket: ThresholdBucket) -> bool:
    if bucket.gte is not None and number < float(bucket.gte):
        return False
    if bucket.gt is not None and number <= float(bucket.gt):
        return False
    if bucket.lte is not None and number > float(bucket.lte):
        return False
    if bucket.lt is not None and number >= float(bucket.lt):
        return False
    return True


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip().lower()
    return str(value).strip().lower()


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None
