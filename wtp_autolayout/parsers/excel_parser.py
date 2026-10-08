"""Excel workbook parser for WTP project data."""

from typing import Any, Dict

import pandas as pd

from .errors import ParserError
from .json_parser import parse_project_data
from .sample_schema import (
    BOUNDARY_COLUMNS,
    CONSTRAINT_COLUMNS,
    FLOW_COLUMNS,
    REQUIRED_EXCEL_SHEETS,
    UNIT_COLUMNS,
)
from .validation import require_columns


def parse_excel_file(path: str):
    """Read an Excel workbook and return a populated Layout."""
    try:
        workbook = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    except ImportError as error:
        raise ParserError("Excel parsing requires pandas and openpyxl: %s" % error)
    except Exception as error:
        raise ParserError("Unable to read Excel input file: %s" % error)

    missing_sheets = [sheet for sheet in REQUIRED_EXCEL_SHEETS if sheet not in workbook]
    if missing_sheets:
        raise ParserError("Missing required sheet(s): %s" % ", ".join(missing_sheets))

    require_columns(workbook["Boundary"].columns, BOUNDARY_COLUMNS, "Boundary sheet")
    require_columns(workbook["Units"].columns, UNIT_COLUMNS, "Units sheet")
    require_columns(workbook["Flow"].columns, FLOW_COLUMNS, "Flow sheet")
    if "Constraints" in workbook:
        require_columns(workbook["Constraints"].columns, CONSTRAINT_COLUMNS, "Constraints sheet")

    data: Dict[str, Any] = {
        "boundary": _records(workbook["Boundary"]),
        "units": _records(workbook["Units"]),
        "flow_edges": _records(workbook["Flow"]),
        "constraints": _records(workbook["Constraints"]) if "Constraints" in workbook else [],
    }

    optional_mapping = {
        "Groups": "system_groups",
        "Proximity": "proximity_relationships",
        "Roads": "roads",
        "Drains": "drains",
        "SiteZones": "site_zones",
        "ExistingStructures": "existing_structures",
        "Corridors": "corridors",
        "GroupRelationships": "group_relationships",
        "EngineeringRules": "engineering_rules",
    }
    for sheet_name, section_name in optional_mapping.items():
        if sheet_name in workbook:
            data[section_name] = _records(workbook[sheet_name])

    if "OptimizationSettings" in workbook:
        data["optimization_settings"] = _key_value_records(workbook["OptimizationSettings"])
    if "Metadata" in workbook:
        data["metadata"] = _key_value_records(workbook["Metadata"])
    if "Project" in workbook:
        project = _key_value_records(workbook["Project"])
        data["plant_type"] = project.get("plant_type", "wtp")
        data["layout_id"] = project.get("layout_id", project.get("project_name", "parsed_layout"))
        data.setdefault("metadata", {}).update({key: value for key, value in project.items() if key not in ("plant_type", "layout_id")})

    return parse_project_data(data)


def _records(frame: "pd.DataFrame"):
    cleaned = frame.where(pd.notna(frame), None)
    return cleaned.to_dict(orient="records")


def _key_value_records(frame: "pd.DataFrame") -> Dict[str, Any]:
    if frame.empty:
        return {}
    lower_columns = {str(column).strip().lower(): column for column in frame.columns}
    if "key" not in lower_columns or "value" not in lower_columns:
        raise ParserError("Key/value sheet missing required columns: key, value")
    key_column = lower_columns["key"]
    value_column = lower_columns["value"]
    values: Dict[str, Any] = {}
    for _, row in frame.iterrows():
        key = row.get(key_column)
        if pd.isna(key):
            continue
        value = row.get(value_column)
        values[str(key).strip()] = None if pd.isna(value) else value
    return values
