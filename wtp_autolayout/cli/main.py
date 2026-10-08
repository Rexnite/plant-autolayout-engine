"""Command-line entrypoint for the Plant AutoLayout Engine."""

import argparse
import sys
import traceback

from wtp_autolayout.models import LayoutMode
from wtp_autolayout.geometry.flow_topology import flow_crossings

from .runner import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Plant AutoLayout Engine pipeline.")
    parser.add_argument("--input", required=True, help="Path to a JSON or XLSX plant project file.")
    parser.add_argument("--output", required=True, help="Directory for generated outputs.")
    parser.add_argument(
        "--algorithm",
        choices=("ranked", "local_search", "simulated_annealing"),
        default="simulated_annealing",
        help="Optimization algorithm.",
    )
    parser.add_argument(
        "--layout-mode",
        choices=("FIT", "SHRINK", "BALANCED"),
        default="BALANCED",
        help="Candidate placement mode.",
    )
    parser.add_argument("--candidate-count", type=int, default=10, help="Initial candidate count.")
    parser.add_argument("--iterations", type=int, default=100, help="Refinement iterations.")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed.")
    parser.add_argument("--no-pdf", action="store_true", help="Disable PDF export.")
    parser.add_argument("--no-png", action="store_true", help="Disable PNG export.")
    parser.add_argument("--no-json", action="store_true", help="Disable JSON export.")
    parser.add_argument("--verbose", action="store_true", help="Print progress and tracebacks.")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = run_pipeline(
            input_path=args.input,
            output_dir=args.output,
            algorithm=args.algorithm,
            layout_mode=LayoutMode[args.layout_mode],
            candidate_count=args.candidate_count,
            iterations=args.iterations,
            seed=args.seed,
            export_pdf=not args.no_pdf,
            export_png=not args.no_png,
            export_json=not args.no_json,
            verbose=args.verbose,
        )
    except Exception as error:
        if args.verbose:
            traceback.print_exc()
        else:
            print("Error: %s" % error, file=sys.stderr)
        return 1

    print_summary(result)
    return 0


def print_summary(result) -> None:
    layout = result.layout
    score_result = result.optimization_result.best_score_result
    score = score_result.score if score_result else layout.optimization_score
    hard_violations = score_result.hard_violation_count if score_result else 0
    soft_violations = score_result.soft_violation_count if score_result else 0
    algorithm_name = result.optimization_result.algorithm.replace("_", " ").title()

    print("-" * 48)
    print("Plant AutoLayout Engine")
    print("-" * 48)
    print("Units: %s" % len(layout.units))
    print("Boundary vertices: %s" % len(layout.boundary.vertices))
    print("Generating candidates...")
    print("%s generated." % len(result.optimization_result.candidate_results))
    print("Optimizing...")
    print("Algorithm: %s" % algorithm_name)
    print("Iterations: %s" % result.optimization_result.iterations)
    print("Best Score: %.2f" % (score if score is not None else 0.0))
    print("Violations: %s" % len(layout.violations))
    print("Exporting...")
    print("PNG: %s" % _export_status(result, "png"))
    print("PDF: %s" % _export_status(result, "pdf"))
    print("JSON: %s" % _json_export_status(result))
    print("")
    print("Summary")
    print("Units: %s" % len(layout.units))
    print("Placements: %s" % len(layout.placements))
    print("Boundary Area: %s" % _format_optional_float(result.boundary_area))
    print("Score: %.2f" % (score if score is not None else 0.0))
    print("Hard Violations: %s" % hard_violations)
    print("Soft Violations: %s" % soft_violations)
    print("Plant Type: %s" % layout.plant_type.value)
    print("Flow Crossings: %s" % len(flow_crossings(layout)))
    if score_result:
        print("Score: base %.1f - hard %.2f - soft %.2f + engineering %.2f = %.2f" % (
            score_result.base_score, score_result.hard_penalty, score_result.soft_penalty,
            score_result.reward_total, score_result.score))
        if score_result.weight_scale < 1:
            print("Objective weights scaled by %.3f to meet 35-point cap" % score_result.weight_scale)
        print("Objective Points: %s" % ", ".join("%s=%.2f" % (key, value)
                                                 for key, value in score_result.reward_by_objective.items()))
    diagnostics = layout.statistics.metadata.get("diagnostics", {}) if layout.statistics else {}
    routing = diagnostics.get("routing", {})
    print("Display Routing: %.2f length, %s fallback(s), %s obstacle conflict(s)" % (
        routing.get("routed_length", 0.0), routing.get("fallback_count", 0),
        routing.get("obstacle_conflicts", 0)))
    print("Site: %s occupied feature(s), %s access check(s), %s group rule(s)" % (
        len(diagnostics.get("site", [])), len(diagnostics.get("access", [])),
        len(diagnostics.get("group_relationships", []))))
    print("Runtime: %.3fs" % result.timings.get("total_runtime", 0.0))
    print("")
    print("Timing")
    print("Parsing: %.3fs" % result.timings.get("parsing", 0.0))
    print("Candidate Generation: %.3fs" % result.timings.get("candidate_generation", 0.0))
    print("Optimization: %.3fs" % result.timings.get("optimization", 0.0))
    print("Rendering: %.3fs" % result.timings.get("rendering", 0.0))
    print("Export: %.3fs" % result.timings.get("export", 0.0))
    print("Total Runtime: %.3fs" % result.timings.get("total_runtime", 0.0))
    print("Completed.")
    print("-" * 48)


def _export_status(result, key: str) -> str:
    return "OK" if key in result.exported_files else "disabled"


def _json_export_status(result) -> str:
    return "OK" if "layout_json" in result.exported_files and "optimization_json" in result.exported_files else "disabled"


def _format_optional_float(value) -> str:
    if value is None:
        return "N/A"
    return "%.2f" % value


if __name__ == "__main__":
    raise SystemExit(main())
