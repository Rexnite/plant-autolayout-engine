"""Tests for Phase 2 input parsers."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from wtp_autolayout.models import FlowType, Layout, LayoutMode, ShapeType
from wtp_autolayout.parsers import ParserError, parse_excel_file, parse_json_file, parse_json_text


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JSON = ROOT / "sample_data" / "sample_wtp_input.json"
SAMPLE_XLSX = ROOT / "sample_data" / "sample_wtp_input.xlsx"


def load_sample_data():
    return json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))


class TestParsers(unittest.TestCase):
    def test_json_parser_returns_layout(self) -> None:
        layout = parse_json_file(str(SAMPLE_JSON))

        self.assertIsInstance(layout, Layout)
        self.assertEqual(layout.boundary.boundary_id, "B-SAMPLE-001")

    def test_excel_parser_returns_layout(self) -> None:
        layout = parse_excel_file(str(SAMPLE_XLSX))

        self.assertIsInstance(layout, Layout)
        self.assertEqual(layout.boundary.boundary_id, "B-SAMPLE-001")

    def test_boundary_vertices_sorted_by_vertex_order(self) -> None:
        data = load_sample_data()
        data["boundary"] = list(reversed(data["boundary"]))

        layout = parse_json_text(json.dumps(data))

        self.assertEqual(layout.boundary.vertices[0].easting, 0.0)
        self.assertEqual(layout.boundary.vertices[1].easting, 180.0)
        self.assertEqual(layout.boundary.vertices[-1].northing, 140.0)

    def test_invalid_enum_raises_parser_error(self) -> None:
        data = load_sample_data()
        data["units"][0]["category"] = "not_a_category"

        with self.assertRaises(ParserError):
            parse_json_text(json.dumps(data))

    def test_missing_required_columns_raises_parser_error(self) -> None:
        data = load_sample_data()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad_input.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame(data["boundary"]).drop(columns=["easting"]).to_excel(
                    writer, sheet_name="Boundary", index=False
                )
                pd.DataFrame(data["units"]).to_excel(writer, sheet_name="Units", index=False)
                pd.DataFrame(data["flow_edges"]).to_excel(writer, sheet_name="Flow", index=False)
                pd.DataFrame(data["constraints"]).to_excel(writer, sheet_name="Constraints", index=False)

            with self.assertRaises(ParserError):
                parse_excel_file(str(path))

    def test_unknown_flow_unit_raises_parser_error(self) -> None:
        data = load_sample_data()
        data["flow_edges"][0]["target_unit_id"] = "missing_unit"

        with self.assertRaises(ParserError):
            parse_json_text(json.dumps(data))

    def test_parsed_layout_contains_core_sections(self) -> None:
        layout = parse_json_file(str(SAMPLE_JSON))

        self.assertEqual(len(layout.units), 10)
        self.assertEqual(len(layout.boundary.vertices), 5)
        self.assertIsNotNone(layout.flow_graph)
        self.assertEqual(len(layout.flow_graph.edges), 8)
        self.assertEqual(len(layout.constraints), 6)
        self.assertEqual(layout.units[3].shape_type, ShapeType.CIRCLE)
        self.assertEqual(layout.flow_graph.edges[0].flow_type, FlowType.PROCESS_WATER)

    def test_sample_json_and_sample_xlsx_both_parse_successfully(self) -> None:
        json_layout = parse_json_file(str(SAMPLE_JSON))
        excel_layout = parse_excel_file(str(SAMPLE_XLSX))

        self.assertEqual(len(json_layout.units), len(excel_layout.units))
        self.assertEqual(len(json_layout.flow_graph.edges), len(excel_layout.flow_graph.edges))
        self.assertEqual(len(json_layout.constraints), len(excel_layout.constraints))

    def test_boundary_with_fewer_than_three_vertices_raises_parser_error(self) -> None:
        data = copy.deepcopy(load_sample_data())
        data["boundary"] = data["boundary"][:2]

        with self.assertRaises(ParserError):
            parse_json_text(json.dumps(data))

    def test_placement_referencing_unknown_unit_id_raises_parser_error(self) -> None:
        data = load_sample_data()
        data["placements"] = [
            {
                "placement_id": "P-BAD-001",
                "unit_id": "missing_unit",
                "easting": 10.0,
                "northing": 20.0,
            }
        ]

        with self.assertRaises(ParserError):
            parse_json_text(json.dumps(data))

    def test_optimization_settings_layout_mode_sets_layout_mode(self) -> None:
        data = load_sample_data()
        data["optimization_settings"]["layout_mode"] = "balanced"

        layout = parse_json_text(json.dumps(data))

        self.assertEqual(layout.layout_mode, LayoutMode.BALANCED)

    def test_invalid_layout_mode_raises_parser_error(self) -> None:
        data = load_sample_data()
        data["optimization_settings"]["layout_mode"] = "turbo"

        with self.assertRaises(ParserError):
            parse_json_text(json.dumps(data))


if __name__ == "__main__":
    unittest.main()
