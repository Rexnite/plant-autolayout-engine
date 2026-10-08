"""End-to-end CLI runner for the final integration phase."""

import copy
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from wtp_autolayout.candidates import CandidateGenerator
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.export import ImageExporter, JSONExporter, PDFExporter
from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.geometry.flow_topology import flow_crossing_diagnostics
from wtp_autolayout.geometry.routing import FlowRouter
from wtp_autolayout.constraints.spatial import proximity_results
from wtp_autolayout.constraints.site import access_results, group_relationship_results, site_results
from wtp_autolayout.models import Layout, LayoutMode, OptimizationStatus
from wtp_autolayout.optimization import CandidateResult, OptimizationRunResult, Optimizer
from wtp_autolayout.optimization.annealing import refine_simulated_annealing
from wtp_autolayout.optimization.local_search import refine_local_search
from wtp_autolayout.parsers import parse_excel_file, parse_json_file
from wtp_autolayout.scoring import ScoringEngine


@dataclass
class CLIRunResult:
    """Structured result returned by the CLI runner."""

    layout: Layout
    optimization_result: OptimizationRunResult
    output_dir: str
    exported_files: Dict[str, str] = field(default_factory=dict)
    timings: Dict[str, float] = field(default_factory=dict)
    boundary_area: Optional[float] = None


def run_pipeline(
    input_path,
    output_dir,
    algorithm: str = "simulated_annealing",
    layout_mode: LayoutMode = LayoutMode.BALANCED,
    candidate_count: int = 10,
    iterations: int = 100,
    seed: Optional[int] = None,
    export_pdf: bool = True,
    export_png: bool = True,
    export_json: bool = True,
    verbose: bool = False,
) -> CLIRunResult:
    """Execute the full input-to-output engineering pipeline."""
    total_start = time.perf_counter()
    timings: Dict[str, float] = {}
    exported_files: Dict[str, str] = {}

    input_file = Path(input_path)
    if not input_file.exists():
        raise RuntimeError("Input file not found: %s" % input_file)
    if candidate_count <= 0:
        raise RuntimeError("candidate-count must be positive")
    if iterations < 0:
        raise RuntimeError("iterations must be non-negative")

    selected_mode = _coerce_layout_mode(layout_mode)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    _progress(verbose, "Loading project...")
    parse_start = time.perf_counter()
    layout = _load_project(input_file)
    timings["parsing"] = time.perf_counter() - parse_start

    geometry_engine = GeometryEngine()
    profile = get_plant_profile(layout.plant_type)
    constraint_engine = profile.constraint_engine()
    settings = layout.metadata.get("optimization_settings", {})
    scoring_engine = ScoringEngine(constraint_engine=constraint_engine,
                                   reward_weight_overrides=settings.get("objective_weights", {})
                                   if isinstance(settings, dict) else {})
    candidate_generator = CandidateGenerator(
        geometry_engine=geometry_engine,
        scoring_engine=scoring_engine,
        random_seed=seed,
        max_attempts_per_unit=3000,
    )
    optimizer = Optimizer(
        candidate_generator=candidate_generator,
        scoring_engine=scoring_engine,
        geometry_engine=geometry_engine,
        random_seed=seed,
        initial_candidate_count=candidate_count,
        max_iterations=iterations,
        mode=selected_mode,
        algorithm=algorithm,
    )

    _progress(verbose, "Generating candidates...")
    generation_start = time.perf_counter()
    ranked_result = optimizer.generate_ranked_candidates(layout, count=candidate_count, mode=selected_mode)
    timings["candidate_generation"] = time.perf_counter() - generation_start
    if not ranked_result.candidate_results:
        raise RuntimeError("Optimization failed: no candidates were generated")

    _progress(verbose, "Optimizing...")
    optimization_start = time.perf_counter()
    optimization_result = _optimize_from_ranked_candidates(
        ranked_result=ranked_result,
        algorithm=algorithm,
        iterations=iterations,
        scoring_engine=scoring_engine,
        geometry_engine=geometry_engine,
        seed=seed,
        mode=selected_mode,
    )
    timings["optimization"] = time.perf_counter() - optimization_start
    if optimization_result.best_layout is None or optimization_result.best_score_result is None:
        raise RuntimeError("Optimization failed")

    best_layout = copy.deepcopy(optimization_result.best_layout)
    scoring_engine.score_layout(best_layout, update_layout=True)
    optimization_result.best_layout = best_layout
    diagnostics = {"plant_type": best_layout.plant_type.value,
                   "active_profile": profile.display_name,
                   "optimization_settings": {"algorithm": algorithm, "layout_mode": selected_mode.value,
                                             "candidate_count": candidate_count, "iterations": iterations,
                                             "seed": seed},
                   "crossings": [event.to_dict() for event in flow_crossing_diagnostics(best_layout)],
                   "proximity": proximity_results(best_layout),
                   "site": site_results(best_layout),
                   "access": access_results(best_layout),
                   "group_relationships": group_relationship_results(best_layout),
                   "routing": FlowRouter(geometry_engine).route_with_diagnostics(best_layout).to_dict(),
                   "warnings": ["Preliminary layout only; not a regulatory or detailed piping design."]}
    best_layout.statistics.metadata["diagnostics"] = diagnostics
    optimization_result.metadata["diagnostics"] = diagnostics

    render_start = time.perf_counter()
    if export_png:
        _progress(verbose, "Rendering PNG...")
        exported_files["png"] = ImageExporter().export_png(
            best_layout,
            output_path / "optimized_layout.png",
            title="Optimized %s Layout" % profile.display_name,
        )
    timings["rendering"] = time.perf_counter() - render_start

    # Exports need a non-empty runtime even though final export time is not known yet.
    best_layout.statistics.runtime = time.perf_counter() - total_start
    export_start = time.perf_counter()
    json_exporter = JSONExporter()
    if export_json:
        _progress(verbose, "Exporting JSON...")
        exported_files["layout_json"] = json_exporter.export_layout(
            best_layout,
            output_path / "optimized_layout.json",
        )
        exported_files["optimization_json"] = json_exporter.export_optimization_result(
            optimization_result,
            output_path / "optimization_result.json",
        )
    if export_pdf:
        _progress(verbose, "Exporting PDF...")
        exported_files["pdf"] = PDFExporter().export_layout_report(
            best_layout,
            output_path / "optimized_layout.pdf",
            title="Optimized %s Layout Report" % profile.display_name,
            include_image=True,
        )
    timings["export"] = time.perf_counter() - export_start
    timings["total_runtime"] = time.perf_counter() - total_start
    best_layout.statistics.runtime = timings["total_runtime"]
    if export_json:
        # Refresh the serialized snapshot with the measured end-to-end runtime.
        json_exporter.export_layout(best_layout, exported_files["layout_json"])
        json_exporter.export_optimization_result(optimization_result, exported_files["optimization_json"])

    boundary_area = _boundary_area(geometry_engine, best_layout)
    return CLIRunResult(
        layout=best_layout,
        optimization_result=optimization_result,
        output_dir=str(output_path),
        exported_files=exported_files,
        timings=timings,
        boundary_area=boundary_area,
    )


def _load_project(input_file: Path) -> Layout:
    extension = input_file.suffix.lower()
    if extension == ".json":
        return parse_json_file(str(input_file))
    if extension in (".xlsx", ".xlsm"):
        return parse_excel_file(str(input_file))
    raise RuntimeError("Unsupported extension: %s" % (extension or "<none>"))


def _optimize_from_ranked_candidates(
    ranked_result: OptimizationRunResult,
    algorithm: str,
    iterations: int,
    scoring_engine: ScoringEngine,
    geometry_engine: GeometryEngine,
    seed: Optional[int],
    mode: LayoutMode,
) -> OptimizationRunResult:
    if algorithm == "ranked":
        ranked_result.metadata.update({"algorithm": "ranked", "mode": mode.value})
        return ranked_result
    if algorithm not in ("local_search", "simulated_annealing"):
        raise RuntimeError("Unsupported optimization algorithm: %s" % algorithm)

    initial = _best_feasible(ranked_result.candidate_results) or ranked_result.candidate_results[0]
    rng = random.Random(seed)
    if algorithm == "local_search":
        best_layout, best_score, completed_iterations = refine_local_search(
            initial,
            scoring_engine,
            geometry_engine,
            rng,
            iterations,
        )
    else:
        best_layout, best_score, completed_iterations = refine_simulated_annealing(
            initial,
            scoring_engine,
            geometry_engine,
            rng,
            iterations,
        )

    candidate_results = _rerank(
        [CandidateResult(layout=best_layout, scoring_result=best_score, rank=0)]
        + ranked_result.candidate_results
    )
    return OptimizationRunResult(
        best_layout=candidate_results[0].layout,
        best_score_result=candidate_results[0].scoring_result,
        candidate_results=candidate_results,
        algorithm=algorithm,
        iterations=completed_iterations,
        runtime_seconds=ranked_result.runtime_seconds,
        status=_status(candidate_results),
        metadata={
            "algorithm": algorithm,
            "mode": mode.value,
            "initial_candidate_count": len(ranked_result.candidate_results),
            "max_iterations": iterations,
        },
    )


def _rerank(candidate_results):
    ranked = sorted(candidate_results,
                    key=lambda item: (item.scoring_result.passed_hard_constraints,
                                      item.scoring_result.score), reverse=True)
    return [
        CandidateResult(layout=result.layout, scoring_result=result.scoring_result, rank=index)
        for index, result in enumerate(ranked, start=1)
    ]


def _best_feasible(candidate_results):
    for result in candidate_results:
        if result.scoring_result.passed_hard_constraints:
            return result
    return None


def _status(candidate_results):
    if not candidate_results:
        return OptimizationStatus.FAILED
    if candidate_results[0].scoring_result.passed_hard_constraints:
        return OptimizationStatus.SUCCESSFUL
    return OptimizationStatus.PARTIAL


def _coerce_layout_mode(value) -> LayoutMode:
    if isinstance(value, LayoutMode):
        return value
    text = str(value).strip()
    try:
        return LayoutMode[text.upper()]
    except KeyError:
        try:
            return LayoutMode(text.lower())
        except ValueError:
            raise RuntimeError("Unsupported layout mode: %s" % value)


def _boundary_area(geometry_engine: GeometryEngine, layout: Layout) -> Optional[float]:
    try:
        return float(geometry_engine.boundary_to_polygon(layout.boundary).area)
    except Exception:
        return None


def _progress(verbose: bool, message: str) -> None:
    if verbose:
        print(message)
