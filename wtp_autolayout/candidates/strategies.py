"""Simple placement strategies for initial candidate generation."""

import random
from typing import Optional, Tuple

from wtp_autolayout.models import LayoutMode


ROTATIONS = (0.0, 90.0, 180.0, 270.0)


def choose_point(
    rng: random.Random,
    bounds: Tuple[float, float, float, float],
    mode: LayoutMode,
    process_fraction: Optional[float] = None,
) -> Tuple[float, float]:
    """Choose a candidate point inside a boundary bounding box."""
    minx, miny, maxx, maxy = bounds
    width = maxx - minx
    height = maxy - miny
    centroid_x = minx + width / 2.0
    centroid_y = miny + height / 2.0

    if mode == LayoutMode.SHRINK:
        x = _clamp(rng.gauss(centroid_x, max(width, 1.0) / 6.0), minx, maxx)
        y = _clamp(rng.gauss(centroid_y, max(height, 1.0) / 6.0), miny, maxy)
        return x, y

    if mode == LayoutMode.BALANCED and process_fraction is not None:
        bias_x = minx + width * process_fraction
        x = _clamp(rng.gauss(bias_x, max(width, 1.0) / 10.0), minx, maxx)
        y = rng.uniform(miny, maxy)
        return x, y

    return rng.uniform(minx, maxx), rng.uniform(miny, maxy)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
