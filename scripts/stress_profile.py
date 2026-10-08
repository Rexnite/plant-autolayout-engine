"""Bounded, repeatable stage timings for synthetic software stress projects."""

import argparse
import cProfile
import io
import pstats
import tempfile
import time
import tracemalloc
from pathlib import Path

from scripts.synthetic_projects import synthetic_project
from wtp_autolayout.candidates import CandidateGenerator
from wtp_autolayout.export import JSONExporter, PDFExporter
from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.geometry.routing import FlowRouter
from wtp_autolayout.optimization import Optimizer
from wtp_autolayout.parsers.json_parser import parse_project_data
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.scoring import ScoringEngine
from wtp_autolayout.visualization import LayoutRenderer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=int, default=10)
    parser.add_argument("--candidates", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--algorithm", choices=("ranked", "local_search", "simulated_annealing"),
                        default="ranked")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--profile-routing", action="store_true")
    parser.add_argument("--skip-exports", action="store_true")
    parser.add_argument("--skip-routing", action="store_true")
    parser.add_argument("--no-memory", action="store_true")
    args = parser.parse_args()
    timings = {}

    def stage(name, operation):
        start = time.perf_counter()
        result = operation()
        timings[name] = round(time.perf_counter() - start, 3)
        return result

    if not args.no_memory:
        tracemalloc.start()
    data = synthetic_project(args.units, args.seed)
    layout = stage("parse", lambda: parse_project_data(data))
    geometry = GeometryEngine()
    constraints = get_plant_profile(layout.plant_type).constraint_engine()
    scoring = ScoringEngine(constraint_engine=constraints)
    generator = CandidateGenerator(geometry_engine=geometry, random_seed=args.seed,
                                   max_attempts_per_unit=500)
    candidates = stage("candidate_generation", lambda: generator.generate_many(
        layout, count=args.candidates))
    candidate = candidates[0]
    violations = stage("constraints", lambda: constraints.evaluate(candidate))
    scored = stage("scoring", lambda: scoring.score_layout(candidate))
    optimizer = Optimizer(generator, scoring, geometry_engine=geometry, random_seed=args.seed,
                          initial_candidate_count=args.candidates, max_iterations=args.iterations,
                          algorithm=args.algorithm)
    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()
    optimized = stage("optimization", lambda: optimizer.optimize(layout))
    if args.profile:
        profiler.disable()
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("cumtime").print_stats(20)
        print(stream.getvalue())
    best = optimized.best_layout
    if args.profile_routing:
        routing_profiler = cProfile.Profile()
        routing_profiler.enable()
    route = stage("routing", lambda: FlowRouter().route_with_diagnostics(best).to_dict()) if not args.skip_routing else {
        "routes": [], "fallback_count": 0, "routed_length": 0, "route_crossings": 0}
    if args.profile_routing:
        routing_profiler.disable()
        stream = io.StringIO()
        pstats.Stats(routing_profiler, stream=stream).sort_stats("cumtime").print_stats(20)
        print(stream.getvalue())
    if not args.skip_exports:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            stage("visualization", lambda: LayoutRenderer().save_png(best, path / "layout.png"))
            stage("json_export", lambda: JSONExporter().export_layout(best, path / "layout.json"))
            stage("pdf_export", lambda: PDFExporter().export_layout_report(
                best, path / "layout.pdf", include_image=False))
            timings["output_kb"] = round(sum(item.stat().st_size for item in path.iterdir()) / 1024, 1)
    peak = 0
    if not args.no_memory:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    print({"units": args.units, "candidates": args.candidates, "iterations": args.iterations,
           "algorithm": args.algorithm, "score": round(scored.score, 3),
           "violations": len(violations), "route_count": len(route["routes"]),
           "fallbacks": route["fallback_count"], "routed_length": round(route["routed_length"], 2),
           "route_crossings": route["route_crossings"], "peak_python_mb": round(peak / 1048576, 1),
           "timings_s": timings})


if __name__ == "__main__":
    main()
