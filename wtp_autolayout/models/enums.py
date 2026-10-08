"""Enumeration types for the WTP AutoLayout engineering data model."""

from enum import Enum


class SerializableEnum(Enum):
    """Enum base class that serializes to stable string values."""

    def __str__(self) -> str:
        return str(self.value)


class UnitCategory(SerializableEnum):
    PROCESS = "process"
    HYDRAULIC = "hydraulic"
    CHEMICAL = "chemical"
    SLUDGE = "sludge"
    UTILITY = "utility"
    RESIDENTIAL = "residential"
    HUMAN_OCCUPANCY = "human_occupancy"
    CLEAN_WATER = "clean_water"
    ELECTRICAL = "electrical"
    INFRASTRUCTURE = "infrastructure"
    OTHER = "other"


class ShapeType(SerializableEnum):
    RECTANGLE = "rectangle"
    SQUARE = "square"
    CIRCLE = "circle"
    POLYGON = "polygon"


class HazardLevel(SerializableEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConstraintType(SerializableEnum):
    BOUNDARY = "boundary"
    OVERLAP = "overlap"
    SPACING = "spacing"
    GEOMETRY = "geometry"
    PROCESS_SEQUENCE = "process_sequence"
    GRAVITY = "gravity"
    PIPELINE = "pipeline"
    GROUPING = "grouping"
    SLUDGE = "sludge"
    CHEMICAL = "chemical"
    RESIDENTIAL = "residential"
    ROAD = "road"
    DRAINAGE = "drainage"
    EXPANSION = "expansion"
    COMPACTNESS = "compactness"
    VISUAL_READABILITY = "visual_readability"
    OTHER = "other"


class ConstraintClassification(SerializableEnum):
    HARD = "hard"
    SOFT = "soft"


class Severity(SerializableEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FlowType(SerializableEnum):
    PROCESS_WATER = "process_water"
    SLUDGE = "sludge"
    CHEMICAL = "chemical"
    RECYCLE = "recycle"
    DRAIN = "drain"
    SERVICE_WATER = "service_water"
    BACKWASH = "backwash"
    OTHER = "other"


class LayoutMode(SerializableEnum):
    FIT = "fit"
    SHRINK = "shrink"
    BALANCED = "balanced"


class OptimizationStatus(SerializableEnum):
    SUCCESSFUL = "successful"
    PARTIAL = "partial"
    FAILED = "failed"


class PlantType(SerializableEnum):
    WTP = "wtp"
    PETROCHEMICAL = "petrochemical"


class SpatialRelationshipType(SerializableEnum):
    PREFERRED_NEAR = "preferred_near"
    TARGET_DISTANCE = "target_distance"
    MAX_DISTANCE = "max_distance"
    MIN_DISTANCE = "min_distance"
