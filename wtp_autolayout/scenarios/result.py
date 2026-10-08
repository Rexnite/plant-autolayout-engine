"""Serializable engineering scenario snapshots; comparisons do not rank runs."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from wtp_autolayout.constraints.spatial import proximity_results
from wtp_autolayout.constraints.site import access_results, group_relationship_results, site_results
from wtp_autolayout.geometry.flow_topology import flow_crossing_diagnostics
from wtp_autolayout.geometry.routing import FlowRouter
from wtp_autolayout.models import Layout
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.scoring.result import ScoringResult


@dataclass
class ScenarioResult:
    name: str
    plant_type: str
    input_project_data: Dict[str, Any]
    optimization_settings: Dict[str, Any]
    seed: int
    candidate_count: int
    iterations: int
    algorithm: str
    layout: Layout
    score_result: ScoringResult
    metrics: Dict[str, Any] = field(default_factory=dict)
    runtime_seconds: float = 0.0
    output_files: Dict[str, str] = field(default_factory=dict)
    active_profile: str = ""
    output_directory: str = ""

    @classmethod
    def from_run(cls, name, input_project_data, run, seed, candidate_count, iterations, algorithm):
        layout = run.layout
        score = run.optimization_result.best_score_result
        relationships = proximity_results(layout)
        routing = FlowRouter().route_with_diagnostics(layout).to_dict()
        crossings = [event.to_dict() for event in flow_crossing_diagnostics(layout)]
        site = site_results(layout)
        access = access_results(layout)
        groups = group_relationship_results(layout)
        diagnostics = layout.statistics.metadata.get("diagnostics", {}) if layout.statistics else {}
        settings = dict(diagnostics.get("optimization_settings", {}))
        if not settings:
            settings = dict(input_project_data.get("optimization_settings", {}))
        metrics = {"score": score.score, "hard_violations": score.hard_violation_count,
                   "soft_violations": score.soft_violation_count,
                   "reward_breakdown": dict(score.reward_by_objective),
                   "score_breakdown": score.to_dict(),
                   "flow_crossings": len(crossings), "crossing_diagnostics": crossings,
                   "proximity_satisfied": sum(bool(row["passed"]) for row in relationships),
                   "proximity_total": len(relationships), "proximity_results": relationships,
                   "group_arrangement_score": score.objective_breakdown.get("group_arrangement").normalized_metric
                   if "group_arrangement" in score.objective_breakdown else 0.0,
                   "routed_flow_length": routing["routed_length"],
                   "routing_fallbacks": routing["fallback_count"], "route_metrics": routing,
                   "site_exclusion_violations": sum(row["classification"] == "hard" for row in site),
                   "expansion_occupancy": sum(row["occupied_area"] for row in site
                                              if row["feature_type"] == "expansion"),
                   "access_satisfied": sum(row["satisfied"] for row in access),
                   "access_total": len(access),
                   "group_relationship_satisfied": sum(row["satisfied"] for row in groups),
                   "group_relationship_total": len(groups),
                   "corridor_routing_used": routing.get("corridor_used_count", 0),
                   "site_results": site, "access_results": access, "group_relationship_results": groups}
        return cls(name, layout.plant_type.value, dict(input_project_data),
                   settings, seed,
                   candidate_count, iterations, algorithm, layout, score,
                   metrics, run.timings.get("total_runtime", 0.0), dict(run.exported_files),
                   diagnostics.get("active_profile", get_plant_profile(layout.plant_type).display_name),
                   getattr(run, "output_dir", ""))

    def to_dict(self):
        return {"name": self.name, "plant_type": self.plant_type,
                "input_project_data": self.input_project_data,
                "optimization_settings": self.optimization_settings,
                "seed": self.seed, "candidate_count": self.candidate_count,
                "iterations": self.iterations, "algorithm": self.algorithm,
                "layout": self.layout.to_dict(), "score_result": self.score_result.to_dict(),
                "metrics": self.metrics, "runtime_seconds": self.runtime_seconds,
                "output_files": self.output_files, "active_profile": self.active_profile,
                "output_directory": self.output_directory}

    @classmethod
    def from_dict(cls, data):
        return cls(data["name"], data["plant_type"], dict(data["input_project_data"]),
                   dict(data["optimization_settings"]), data["seed"], data["candidate_count"],
                   data["iterations"], data["algorithm"], Layout.from_dict(data["layout"]),
                   ScoringResult.from_dict(data["score_result"]), dict(data.get("metrics", {})),
                   data.get("runtime_seconds", 0.0), dict(data.get("output_files", {})),
                   data.get("active_profile", ""), data.get("output_directory", ""))


def compare_scenarios(scenarios: List[ScenarioResult]) -> List[Dict[str, Any]]:
    if not 2 <= len(scenarios) <= 5:
        raise ValueError("Compare between 2 and 5 scenarios")
    return [{"Scenario": item.name, "Plant": item.plant_type,
             "Profile": item.active_profile,
             "Algorithm": item.algorithm, "Seed": item.seed,
             "Candidates": item.candidate_count, "Iterations": item.iterations,
             "Score": item.metrics["score"],
             "Hard violations": item.metrics["hard_violations"],
             "Soft violations": item.metrics["soft_violations"],
             "Crossings": item.metrics["flow_crossings"],
             "Proximity": "%s/%s" % (item.metrics["proximity_satisfied"], item.metrics["proximity_total"]),
             "Group score": item.metrics["group_arrangement_score"],
             "Routed length": item.metrics["routed_flow_length"],
             "Routing fallbacks": item.metrics.get("routing_fallbacks", item.metrics.get("route_metrics", {}).get("fallback_count", 0)),
             "Site exclusions": item.metrics.get("site_exclusion_violations", 0),
             "Expansion occupied": item.metrics.get("expansion_occupancy", 0.0),
             "Access": "%s/%s" % (item.metrics.get("access_satisfied", 0), item.metrics.get("access_total", 0)),
             "Group rules": "%s/%s" % (item.metrics.get("group_relationship_satisfied", 0),
                                        item.metrics.get("group_relationship_total", 0)),
             "Corridor routes": item.metrics.get("corridor_routing_used", 0),
             "Runtime (s)": item.runtime_seconds} for item in scenarios]
