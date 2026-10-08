"""Re-run fixed demo presets and validate reproducibility and exported files."""

import json
from pathlib import Path

from PIL import Image

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from wtp_autolayout.cli.runner import run_pipeline
from wtp_autolayout.visualization import PlotlyLayoutRenderer


ROOT = Path(__file__).resolve().parents[1]
PRESETS = json.loads((ROOT / "sample_data" / "demo_presets.json").read_text(encoding="utf-8"))


def fingerprint(run):
    diagnostics = run.layout.statistics.metadata["diagnostics"]
    return {
        "placements": [(item.unit_id, item.centroid.easting, item.centroid.northing,
                        item.centroid.elevation, item.rotation) for item in run.layout.placements],
        "score": run.optimization_result.best_score_result.score,
        "crossings": diagnostics["crossings"],
        "proximity": diagnostics["proximity"],
        "access": diagnostics["access"],
        "routing": diagnostics["routing"],
    }


def validate_exports(run):
    files = run.exported_files
    for key in ("png", "pdf", "layout_json", "optimization_json"):
        path = Path(files[key])
        if not path.is_file() or path.stat().st_size == 0:
            raise AssertionError("Missing or empty %s export: %s" % (key, path))
    with Image.open(files["png"]) as image:
        image.verify()
    if PdfReader is not None:
        if not PdfReader(files["pdf"]).pages:
            raise AssertionError("PDF has no readable pages")
    else:
        pdf = Path(files["pdf"]).read_bytes()
        if not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-128:]:
            raise AssertionError("PDF does not have valid start/end markers")
    exported = json.loads(Path(files["layout_json"]).read_text(encoding="utf-8"))
    if not exported.get("statistics", {}).get("metadata", {}).get("diagnostics", {}).get("routing"):
        raise AssertionError("Layout JSON is missing routing diagnostics")
    json.loads(Path(files["optimization_json"]).read_text(encoding="utf-8"))
    html = Path(run.output_dir) / "interactive_layout.html"
    PlotlyLayoutRenderer().export_html(run.layout, html)
    if html.stat().st_size == 0:
        raise AssertionError("Interactive HTML export is empty")


def run_preset(key, suffix):
    preset = PRESETS[key]
    run = run_pipeline(ROOT / preset["input"], ROOT / "outputs" / "demo_verification" / suffix,
                       algorithm=preset["algorithm"], candidate_count=preset["candidate_count"],
                       iterations=preset["iterations"], seed=preset["seed"],
                       layout_mode=preset["layout_mode"])
    validate_exports(run)
    score = run.optimization_result.best_score_result
    diagnostics = run.layout.statistics.metadata["diagnostics"]
    print("%s: score %.2f, hard %s, soft %s, crossings %s, routing fallback %s, %.2fs" % (
        suffix, score.score, score.hard_violation_count, score.soft_violation_count,
        len(diagnostics["crossings"]), diagnostics["routing"]["fallback_count"],
        run.timings["total_runtime"]))
    return run


def main():
    runs = [run_preset("wtp", "wtp_%02d" % index) for index in range(1, 4)]
    if not all(fingerprint(run) == fingerprint(runs[0]) for run in runs[1:]):
        raise AssertionError("WTP preset is not reproducible across three runs")
    print("WTP engineering fingerprint identical across three runs (runtime excluded).")
    run_preset("petrochemical", "petrochemical_01")


if __name__ == "__main__":
    main()
