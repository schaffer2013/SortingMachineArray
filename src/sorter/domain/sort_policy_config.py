from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

SUPPORTED_CRITERIA_KINDS = {"category_rank", "numeric", "threshold_bucket", "alpha"}


@dataclass(frozen=True)
class ThresholdBucket:
    label: str
    gte: float | int | None = None
    gt: float | int | None = None
    lte: float | int | None = None
    lt: float | int | None = None


@dataclass(frozen=True)
class SortCriterion:
    kind: str
    field: str
    order: list[str] | None = None
    direction: str = "asc"
    missing_last: bool = True
    unknown_last: bool = True
    buckets: list[ThresholdBucket] | None = None
    missing_bucket: str | None = None


@dataclass(frozen=True)
class SortPolicyConfig:
    version: int
    policy_name: str
    criteria: list[SortCriterion]


class PolicyConfigError(ValueError):
    pass


def load_sort_policy_file(path: Path) -> SortPolicyConfig:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return parse_sort_policy_config(raw, source=str(path))


def load_sort_policy_by_name(policy_name: str, policy_dir: Path) -> SortPolicyConfig:
    path = policy_dir / f"{policy_name}.json"
    if not path.exists():
        raise PolicyConfigError(f"Policy file not found: {path}")
    return load_sort_policy_file(path)


def parse_sort_policy_config(raw: dict, source: str = "<memory>") -> SortPolicyConfig:
    version = raw.get("version")
    if not isinstance(version, int):
        raise PolicyConfigError(f"{source}: 'version' must be an integer")

    policy_name = raw.get("policy_name")
    if not isinstance(policy_name, str) or not policy_name.strip():
        raise PolicyConfigError(f"{source}: 'policy_name' must be a non-empty string")

    raw_criteria = raw.get("criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise PolicyConfigError(f"{source}: 'criteria' must be a non-empty list")

    criteria: list[SortCriterion] = []
    for index, raw_criterion in enumerate(raw_criteria):
        criteria.append(_parse_criterion(raw_criterion, source, index))

    return SortPolicyConfig(version=version, policy_name=policy_name.strip(), criteria=criteria)


def _parse_criterion(raw: dict, source: str, index: int) -> SortCriterion:
    if not isinstance(raw, dict):
        raise PolicyConfigError(f"{source}: criteria[{index}] must be an object")

    kind = raw.get("kind")
    field = raw.get("field")
    if kind not in SUPPORTED_CRITERIA_KINDS:
        raise PolicyConfigError(
            f"{source}: criteria[{index}] has unsupported kind '{kind}', "
            f"expected one of {sorted(SUPPORTED_CRITERIA_KINDS)}"
        )
    if not isinstance(field, str) or not field.strip():
        raise PolicyConfigError(f"{source}: criteria[{index}] must define a non-empty 'field'")

    order = raw.get("order")
    if order is not None:
        if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
            raise PolicyConfigError(f"{source}: criteria[{index}].order must be a list[str]")

    direction = str(raw.get("direction", "asc")).lower()
    if direction not in {"asc", "desc"}:
        raise PolicyConfigError(f"{source}: criteria[{index}].direction must be 'asc' or 'desc'")

    missing_last = bool(raw.get("missing_last", True))
    unknown_last = bool(raw.get("unknown_last", True))

    buckets: list[ThresholdBucket] | None = None
    raw_buckets = raw.get("buckets")
    if raw_buckets is not None:
        if not isinstance(raw_buckets, list) or not raw_buckets:
            raise PolicyConfigError(f"{source}: criteria[{index}].buckets must be a non-empty list")
        buckets = [_parse_threshold_bucket(item, source, index, bucket_index) for bucket_index, item in enumerate(raw_buckets)]

    if kind == "category_rank" and not order:
        raise PolicyConfigError(f"{source}: criteria[{index}] category_rank requires 'order'")
    if kind == "threshold_bucket" and not buckets:
        raise PolicyConfigError(f"{source}: criteria[{index}] threshold_bucket requires 'buckets'")

    return SortCriterion(
        kind=kind,
        field=field.strip(),
        order=[item.strip().lower() for item in order] if order else None,
        direction=direction,
        missing_last=missing_last,
        unknown_last=unknown_last,
        buckets=buckets,
        missing_bucket=(
            str(raw.get("missing_bucket")).strip().lower()
            if raw.get("missing_bucket") is not None
            else None
        ),
    )


def _parse_threshold_bucket(raw: dict, source: str, criterion_index: int, bucket_index: int) -> ThresholdBucket:
    if not isinstance(raw, dict):
        raise PolicyConfigError(
            f"{source}: criteria[{criterion_index}].buckets[{bucket_index}] must be an object"
        )

    label = raw.get("label")
    if not isinstance(label, str) or not label.strip():
        raise PolicyConfigError(
            f"{source}: criteria[{criterion_index}].buckets[{bucket_index}] must define non-empty 'label'"
        )

    allowed_keys = {"gte", "gt", "lte", "lt"}
    if not any(key in raw for key in allowed_keys):
        raise PolicyConfigError(
            f"{source}: criteria[{criterion_index}].buckets[{bucket_index}] requires one of {sorted(allowed_keys)}"
        )

    return ThresholdBucket(
        label=label.strip().lower(),
        gte=raw.get("gte"),
        gt=raw.get("gt"),
        lte=raw.get("lte"),
        lt=raw.get("lt"),
    )
