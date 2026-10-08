"""Tests for Phase 8 visualization and Phase 9 export."""

import copy
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from wtp_autolayout.candidates import CandidateGenerator
from wtp_autolayout.constraints import default_wtp_engine
from wtp_autolayout.export import ImageExporter, JSONExporter, PDFExporter
from wtp_autolayout.models import Coordinate, Drain, LayoutMode, Road, Severity, Violation
from wtp_autolayout.parsers import parse_json_file
from wtp_autolayout.scoring import ScoringEngine
from wtp_autolayout.visualization import LayoutRenderer, PlotlyLayoutRenderer


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JSON = ROOT / "sample_data" / "sample_wtp_input.json"


def sample_candidate():
    layout = parse_json_file(str(SAMPLE_JSON))
    candidate = CandidateGenerator(random_seed=1, max_attempts_per_unit=3000).generate(layout, mode=LayoutMode.FIT)
    ScoringEngine(default_wtp_engine()).score_layout(candidate, update_layout=True)
    return candidate


class TestVisualizationExport(unittest.TestCase):
    def test_renderer_returns_matplotlib_figure(self) -> None:
        layout = sample_candidate()
        fig = LayoutRenderer().render(layout, title="Test Layout")

        self.assertIsInstance(fig, Figure)
        plt.close(fig)

    def test_save_png_creates_non_empty_png_file(self) -> None:
        layout = sample_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "layout.png"
            returned = LayoutRenderer().save_png(layout, path)

            self.assertEqual(returned, str(path))
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)

    def test_render_with_output_path_creates_png_and_returns_figure(self) -> None:
        layout = sample_candidate()
        before = copy.deepcopy(layout.to_dict())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "layout.png"
            fig = LayoutRenderer().render(layout, output_path=path, title="Rendered Layout")

            self.assertIsInstance(fig, Figure)
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)
            plt.close(fig)

        self.assertEqual(layout.to_dict(), before)

    def test_render_handles_layout_with_flow_arrows(self) -> None:
        layout = sample_candidate()
        fig = LayoutRenderer(show_flow=True).render(layout)

        self.assertIsInstance(fig, Figure)
        plt.close(fig)

    def test_render_handles_layout_with_violations(self) -> None:
        layout = sample_candidate()
        layout.violations = [
            Violation(
                violation_id="V-001",
                constraint_id="C-009",
                affected_units=["sludge_sump", "admin_building"],
                penalty=5.0,
                severity=Severity.HIGH,
                description="Synthetic violation",
                suggested_action="Move units apart",
            )
        ]

        fig = LayoutRenderer(show_violations=True).render(layout)

        self.assertIsInstance(fig, Figure)
        plt.close(fig)

    def test_plotly_renderer_returns_interactive_figure(self) -> None:
        layout = sample_candidate()
        fig = PlotlyLayoutRenderer(show_flow=True, show_clearance=True).render(layout)

        self.assertGreater(len(fig.data), 0)

    def test_plotly_renderer_exports_html(self) -> None:
        layout = sample_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "interactive" / "layout.html"
            returned = PlotlyLayoutRenderer(show_flow=True).export_html(layout, path)

            self.assertEqual(returned, str(path))
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)

    def test_renderers_handle_roads_and_drains(self) -> None:
        layout = sample_candidate()
        layout.roads = [Road("R-001", path=[Coordinate(0.0, 10.0), Coordinate(120.0, 10.0)], width=6.0)]
        layout.drains = [Drain("D-001", path=[Coordinate(0.0, 20.0), Coordinate(120.0, 20.0)])]

        fig = LayoutRenderer().render(layout)
        plotly_fig = PlotlyLayoutRenderer().render(layout)

        self.assertIsInstance(fig, Figure)
        self.assertGreater(len(plotly_fig.data), 0)
        plt.close(fig)

    def test_json_exporter_exports_layout_json(self) -> None:
        layout = sample_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "layout.json"
            returned = JSONExporter().export_layout(layout, path)

            self.assertEqual(returned, str(path))
            self.assertTrue(path.exists())
            self.assertIn('"layout_id"', path.read_text(encoding="utf-8"))

    def test_pdf_exporter_exports_non_empty_pdf_report(self) -> None:
        layout = sample_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reports" / "layout.pdf"
            returned = PDFExporter().export_layout_report(layout, path, title="Test Report")

            self.assertEqual(returned, str(path))
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)

    def test_image_exporter_exports_png(self) -> None:
        layout = sample_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "images" / "layout.png"
            returned = ImageExporter().export_png(layout, path)

            self.assertEqual(returned, str(path))
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)

    def test_exporters_create_parent_directories(self) -> None:
        layout = sample_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "a" / "b" / "layout.json"
            png_path = Path(temp_dir) / "c" / "d" / "layout.png"
            pdf_path = Path(temp_dir) / "e" / "f" / "layout.pdf"

            JSONExporter().export_layout(layout, json_path)
            ImageExporter().export_png(layout, png_path)
            PDFExporter().export_layout_report(layout, pdf_path, include_image=False)

            self.assertTrue(json_path.exists())
            self.assertTrue(png_path.exists())
            self.assertTrue(pdf_path.exists())

    def test_rendering_skips_missing_placement_flow_edges_gracefully(self) -> None:
        layout = sample_candidate()
        layout.placements = layout.placements[:-1]

        fig = LayoutRenderer(show_flow=True).render(layout)

        self.assertIsInstance(fig, Figure)
        plt.close(fig)

    def test_rendering_and_export_do_not_mutate_input_layout(self) -> None:
        layout = sample_candidate()
        before = copy.deepcopy(layout.to_dict())
        with tempfile.TemporaryDirectory() as temp_dir:
            LayoutRenderer().save_png(layout, Path(temp_dir) / "layout.png")
            JSONExporter().export_layout(layout, Path(temp_dir) / "layout.json")
            PDFExporter().export_layout_report(layout, Path(temp_dir) / "layout.pdf", include_image=False)

        self.assertEqual(layout.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
