"""User-defined logical groups for plant units."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .common import require_id, require_positive


@dataclass
class SystemGroup:
    group_id: str
    name: str
    preferred_radius: Optional[float] = None
    preference: str = "loosely_clustered"

    def __post_init__(self) -> None:
        require_id(self.group_id, "group_id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("group name is required")
        require_positive(self.preferred_radius, "preferred_radius")
        if self.preference not in ("strongly_clustered", "loosely_clustered", "neutral"):
            raise ValueError("invalid group preference")

    def to_dict(self) -> Dict[str, Any]:
        return {"group_id": self.group_id, "name": self.name,
                "preferred_radius": self.preferred_radius, "preference": self.preference}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemGroup":
        return cls(data["group_id"], data["name"], data.get("preferred_radius"),
                   data.get("preference") or "loosely_clustered")
