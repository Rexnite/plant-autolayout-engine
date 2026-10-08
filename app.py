"""Streamlit workflow for preliminary plant layout studies."""

import json
import logging
import tempfile
from uuid import uuid4
from pathlib import Path

import pandas as pd
import streamlit as st

from wtp_autolayout.cli.runner import run_pipeline
from wtp_autolayout.candidates import CandidateGenerationError
from wtp_autolayout.constraints.spatial import proximity_results
from wtp_autolayout.constraints.site import access_results, group_relationship_results, site_results
from wtp_autolayout.geometry.flow_topology import flow_crossings
from wtp_autolayout.geometry.routing import FlowRouter
from wtp_autolayout.geometry import GeometryError
from wtp_autolayout.models import Coordinate, PlantType
from wtp_autolayout.parsers import parse_excel_file
from wtp_autolayout.parsers.boundary_ordering import order_boundary
from wtp_autolayout.parsers.json_parser import parse_project_data
from wtp_autolayout.parsers.errors import ParserError
from wtp_autolayout.optimization import OptimizationError
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.scenarios import ScenarioResult, compare_scenarios
from wtp_autolayout.visualization import PlotlyLayoutRenderer


ROOT = Path(__file__).resolve().parent
SAMPLES = {
    "Water Treatment Plant": ROOT / "sample_data" / "sample_general_wtp_input.json",
    "Petrochemical Plant": ROOT / "sample_data" / "sample_petrochemical_input.json",
    "Legacy WTP": ROOT / "sample_data" / "sample_wtp_input.json",
}
STAGES = ("Project Setup", "Site Boundary", "Site Features", "System Groups", "Units", "Flow",
          "Proximity", "Corridors / Roads",
          "Optimization Settings", "Results")


def _records(frame):
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")


def _rows(project, key, columns):
    frame = pd.DataFrame(project.get(key, []))
    for column in columns:
        if column not in frame:
            frame[column] = None
    return frame[list(columns)]


def _geometry_rows(project, key, columns, geometry_key):
    frame = _rows(project, key, columns)
    frame[geometry_key] = frame[geometry_key].apply(
        lambda value: json.dumps(value) if isinstance(value, list) else value)
    return frame


def _project_from_tables(project):
    result = dict(project)
    for key in ("boundary", "system_groups", "units", "flow_edges", "proximity_relationships",
                "site_zones", "existing_structures", "corridors", "group_relationships", "roads",
                "engineering_rules"):
        result[key] = [{field: value for field, value in row.items() if value is not None and value != ""}
                       for row in result.get(key, [])
                       if any(value is not None and value != "" for value in row.values())]
    result.setdefault("constraints", [])
    result.setdefault("metadata", {})
    result.setdefault("plant_type", "wtp")
    return result


def _layout_to_input(layout):
    return {
        "layout_id": layout.layout_id, "plant_type": layout.plant_type.value,
        "boundary": [dict(point.to_dict(), vertex_order=index) for index, point in enumerate(layout.boundary.vertices, 1)],
        "system_groups": [group.to_dict() for group in layout.system_groups],
        "units": [unit.to_dict() for unit in layout.units],
        "flow_edges": [{"edge_id": edge.flow_id, "source_unit_id": edge.source_unit_id,
                        "target_unit_id": edge.target_unit_id, "flow_type": edge.flow_type.value,
                        "gravity_required": edge.gravity_preferred, "weight": edge.weight}
                       for edge in layout.flow_graph.edges] if layout.flow_graph else [],
        "proximity_relationships": [item.to_dict() for item in layout.proximity_relationships],
        "site_zones": [item.to_dict() for item in layout.site_zones],
        "existing_structures": [item.to_dict() for item in layout.existing_structures],
        "corridors": [item.to_dict() for item in layout.corridors],
        "group_relationships": [item.to_dict() for item in layout.group_relationships],
        "constraints": [item.to_dict() for item in layout.constraints],
        "roads": [item.to_dict() for item in layout.roads],
        "drains": [item.to_dict() for item in layout.drains],
        "metadata": dict(layout.metadata),
        "optimization_settings": {"layout_mode": layout.layout_mode.value if layout.layout_mode else "balanced"},
    }


def _boundary_preview(rows):
    from shapely.geometry import Polygon
    points = [Coordinate(float(row["easting"]), float(row["northing"])) for row in rows
              if row.get("easting") is not None and row.get("northing") is not None]
    ordered = order_boundary(points, ordered=bool(rows) and all(row.get("vertex_order") is not None for row in rows))
    return Polygon([(point.easting, point.northing) for point in ordered])


def _load_sample(name):
    st.session_state.project = json.loads(SAMPLES[name].read_text(encoding="utf-8"))
    st.session_state.pop("run_result", None)
    for key in ("boundary_table", "groups_table", "units_table", "flow_table", "proximity_table", "rules_table",
                "zones_table", "structures_table", "corridors_table", "group_rules_table", "roads_table"):
        st.session_state.pop(key, None)


def _setup(project):
    st.subheader("Project")
    project.setdefault("metadata", {})["project_name"] = st.text_input(
        "Project name", project.get("metadata", {}).get("project_name", "Untitled Plant"))
    names = ["Water Treatment Plant", "Petrochemical Plant"]
    current = PlantType(project.get("plant_type", "wtp"))
    choice = st.selectbox("Plant type", names, index=0 if current == PlantType.WTP else 1)
    project["plant_type"] = "wtp" if choice == names[0] else "petrochemical"
    project["layout_id"] = st.text_input("Layout ID", project.get("layout_id", "plant_layout"))
    if st.button("Load suggested groups"):
        project["system_groups"] = [group.to_dict() for group in get_plant_profile(project["plant_type"]).default_groups()]
        st.rerun()
    if st.button("Load suggested units"):
        profile = get_plant_profile(project["plant_type"])
        project["system_groups"] = [group.to_dict() for group in profile.default_groups()]
        project["units"] = [unit.to_dict() for unit in profile.default_units()]
        project["flow_edges"] = []
        project["proximity_relationships"] = []
        st.session_state.pop("units_table", None)
        st.session_state.pop("groups_table", None)
        st.rerun()


def _boundary(project):
    st.subheader("Site Boundary")
    legacy_ordered = bool(project.get("boundary")) and all(
        row.get("vertex_order") is not None for row in project["boundary"])
    frame = _rows(project, "boundary", ("easting", "northing"))
    project["boundary"] = _records(st.data_editor(frame, num_rows="dynamic", use_container_width=True, key="boundary_table"))
    if legacy_ordered:
        project["boundary"] = [dict(row, vertex_order=index) for index, row in enumerate(project["boundary"], 1)]
    try:
        polygon = _boundary_preview(project["boundary"])
        st.success("Valid site polygon | area %.1f | %d vertices" % (polygon.area, len(polygon.exterior.coords) - 1))
        import plotly.graph_objects as go
        x, y = polygon.exterior.xy
        fig = go.Figure(go.Scatter(x=list(x), y=list(y), fill="toself", mode="lines+markers",
                                   line={"color": "#176c80"}, fillcolor="rgba(23,108,128,0.12)"))
        fig.update_layout(xaxis_title="Easting", yaxis_title="Northing", yaxis={"scaleanchor": "x"},
                          margin={"l": 10, "r": 10, "t": 10, "b": 10}, height=400)
        st.plotly_chart(fig, use_container_width=True)
    except (ValueError, TypeError) as error:
        st.error("Boundary: %s" % error)


def _groups(project):
    st.subheader("System Groups")
    current = project.get("system_groups", [])
    count = st.number_input("Total groups", min_value=0, max_value=50, value=len(current), step=1)
    rows = list(current[:count]) + [{"group_id": "", "name": "", "preferred_radius": None}
                                    for _ in range(max(0, count - len(current)))]
    frame = pd.DataFrame(rows, columns=["group_id", "name", "preferred_radius", "preference"])
    project["system_groups"] = _records(st.data_editor(frame, use_container_width=True, key="groups_table"))
    columns = ("relationship_id", "group_id_a", "group_id_b", "relationship_type", "distance", "classification", "weight")
    group_ids = [item.get("group_id") for item in project["system_groups"] if item.get("group_id")]
    st.markdown("**Group relationships**")
    project["group_relationships"] = _records(st.data_editor(_rows(project, "group_relationships", columns),
        num_rows="dynamic", use_container_width=True, key="group_rules_table",
        column_config={"group_id_a": st.column_config.SelectboxColumn(options=group_ids),
                       "group_id_b": st.column_config.SelectboxColumn(options=group_ids),
                       "relationship_type": st.column_config.SelectboxColumn(
                           options=["preferred_near", "min_distance", "max_distance", "neutral"]),
                       "classification": st.column_config.SelectboxColumn(options=["soft", "hard"])}))


def _site_features(project):
    st.subheader("Site Features")
    zone_columns = ("zone_id", "name", "zone_type", "classification", "clearance", "weight", "vertices", "provenance")
    project["site_zones"] = _records(st.data_editor(
        _geometry_rows(project, "site_zones", zone_columns, "vertices"), num_rows="dynamic",
        use_container_width=True, key="zones_table",
        column_config={"zone_type": st.column_config.SelectboxColumn(
            options=["exclusion", "restricted", "reserved", "expansion"]),
                       "classification": st.column_config.SelectboxColumn(options=["hard", "soft"]),
                       "vertices": st.column_config.TextColumn(help="JSON array of {easting, northing} vertices")}))
    st.markdown("**Existing structures**")
    structure_columns = ("structure_id", "name", "clearance", "vertices", "provenance")
    project["existing_structures"] = _records(st.data_editor(
        _geometry_rows(project, "existing_structures", structure_columns, "vertices"),
        num_rows="dynamic", use_container_width=True, key="structures_table",
        column_config={"vertices": st.column_config.TextColumn(help="JSON array of {easting, northing} vertices")}))


def _corridors(project):
    st.subheader("Corridors / Roads")
    columns = ("corridor_id", "name", "corridor_type", "width", "classification", "setback", "path", "provenance")
    project["corridors"] = _records(st.data_editor(
        _geometry_rows(project, "corridors", columns, "path"), num_rows="dynamic",
        use_container_width=True, key="corridors_table",
        column_config={"corridor_type": st.column_config.SelectboxColumn(
            options=["access", "road", "utility", "routing"]),
                       "classification": st.column_config.SelectboxColumn(options=["soft", "hard"]),
                       "path": st.column_config.TextColumn(help="JSON array of {easting, northing} points")}))
    st.markdown("**Legacy roads**")
    road_columns = ("road_id", "road_type", "width", "path")
    project["roads"] = _records(st.data_editor(_geometry_rows(project, "roads", road_columns, "path"),
        num_rows="dynamic", use_container_width=True, key="roads_table"))


def _units(project):
    st.subheader("Engineering Units")
    columns = ("unit_id", "name", "category", "shape_type", "width", "length", "diameter",
               "required_clearance", "system_group", "process_order", "hazard_level",
               "access_required", "max_access_distance", "access_classification", "maintenance_clearance")
    groups = [row["group_id"] for row in project.get("system_groups", []) if row.get("group_id")]
    config = {
        "category": st.column_config.SelectboxColumn(options=["process", "hydraulic", "chemical", "sludge", "utility", "residential", "human_occupancy", "clean_water", "electrical", "infrastructure", "other"]),
        "shape_type": st.column_config.SelectboxColumn(options=["rectangle", "square", "circle"]),
        "system_group": st.column_config.SelectboxColumn(options=groups),
        "access_classification": st.column_config.SelectboxColumn(options=["soft", "hard"]),
    }
    project["units"] = _records(st.data_editor(_rows(project, "units", columns), num_rows="dynamic",
                                               use_container_width=True, column_config=config, key="units_table"))


def _flow(project):
    st.subheader("Process Flow")
    columns = ("edge_id", "source_unit_id", "target_unit_id", "flow_type", "gravity_required", "weight")
    ids = [row["unit_id"] for row in project.get("units", []) if row.get("unit_id")]
    config = {"source_unit_id": st.column_config.SelectboxColumn(options=ids),
              "target_unit_id": st.column_config.SelectboxColumn(options=ids),
              "flow_type": st.column_config.SelectboxColumn(options=["process_water", "sludge", "chemical", "recycle", "drain", "service_water", "backwash", "other"])}
    project["flow_edges"] = _records(st.data_editor(_rows(project, "flow_edges", columns), num_rows="dynamic",
                                                  use_container_width=True, column_config=config, key="flow_table"))


def _proximity(project):
    st.subheader("Proximity / Distance")
    columns = ("relationship_id", "unit_id_a", "unit_id_b", "relationship_type", "distance", "classification", "weight")
    ids = [row["unit_id"] for row in project.get("units", []) if row.get("unit_id")]
    config = {"unit_id_a": st.column_config.SelectboxColumn(options=ids),
              "unit_id_b": st.column_config.SelectboxColumn(options=ids),
              "relationship_type": st.column_config.SelectboxColumn(options=["preferred_near", "target_distance", "max_distance", "min_distance"]),
              "classification": st.column_config.SelectboxColumn(options=["soft", "hard"])}
    project["proximity_relationships"] = _records(st.data_editor(
        _rows(project, "proximity_relationships", columns), num_rows="dynamic", use_container_width=True,
        column_config=config, key="proximity_table"))
    st.markdown("**Engineering rules**")
    rule_columns = ("rule_id", "scope", "subject_a", "subject_b", "rule_type", "distance",
                    "classification", "weight")
    project["engineering_rules"] = _records(st.data_editor(_rows(project, "engineering_rules", rule_columns),
        num_rows="dynamic", use_container_width=True, key="rules_table",
        column_config={"scope": st.column_config.SelectboxColumn(
            options=["unit_pair", "group_pair", "unit_access", "zone_occupancy"]),
                       "classification": st.column_config.SelectboxColumn(options=["soft", "hard"]),
                       "rule_type": st.column_config.SelectboxColumn(
                           options=["min_distance", "max_distance", "target_distance", "preferred_near", "neutral", "avoid"])}))
    st.caption("Distances are footprint to footprint. Preferred near is soft; hard target distance requires an exact match.")


def _settings(project):
    st.subheader("Optimization Settings")
    st.session_state.algorithm = st.selectbox("Algorithm", ["simulated_annealing", "local_search", "ranked"])
    mode = st.selectbox("Layout mode", ["balanced", "fit", "shrink"])
    project.setdefault("optimization_settings", {})["layout_mode"] = mode
    profile_weights = get_plant_profile(project.get("plant_type", "wtp")).objective_weights
    configured = dict(profile_weights)
    configured.update({"access": 0.0, "group_relationship": 0.0})
    configured.update(project["optimization_settings"].get("objective_weights") or {})
    weight_frame = pd.DataFrame([{"Objective": name, "Weight": value}
                                 for name, value in configured.items()])
    with st.expander("Engineering objective weights"):
        edited = st.data_editor(weight_frame, num_rows="dynamic", hide_index=True, use_container_width=True,
                                key="objective_weights_table")
        project["optimization_settings"]["objective_weights"] = {
            str(row["Objective"]): float(row["Weight"])
            for row in _records(edited) if row["Objective"] and row["Weight"] is not None}
    st.session_state.candidate_count = st.slider("Candidate count", 1, 30, 10)
    st.session_state.iterations = st.slider("Iterations", 0, 300, 100)
    st.session_state.seed = st.number_input("Random seed", value=42, step=1)
    if st.button("Run AutoLayout", type="primary"):
        _run(project)


def _run(project):
    try:
        clean = _project_from_tables(project)
        parse_project_data(clean)
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "project.json"
            input_path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
            run_dir = ROOT / "outputs" / ("run_" + uuid4().hex[:10])
            result = run_pipeline(input_path, run_dir,
                                  algorithm=st.session_state.get("algorithm", "simulated_annealing"),
                                  layout_mode=clean.get("optimization_settings", {}).get("layout_mode", "balanced"),
                                  candidate_count=st.session_state.get("candidate_count", 10),
                                  iterations=st.session_state.get("iterations", 100),
                                  seed=int(st.session_state.get("seed", 42)))
        result.exported_files["html"] = PlotlyLayoutRenderer().export_html(result.layout, run_dir / "optimized_layout.html")
        st.session_state.run_result = result
        st.session_state.run_input = clean
        st.session_state.stage_next = "Results"
        st.rerun()
    except (ParserError, CandidateGenerationError, OptimizationError, GeometryError,
            ValueError, OSError, RuntimeError) as error:
        st.error("Cannot run project: %s" % error)
    except Exception:
        logging.exception("Unexpected AutoLayout run failure")
        st.error("An unexpected error stopped this run. Review the server log; no project changes were saved.")


def _results():
    result = st.session_state.get("run_result")
    if result is None:
        st.info("Run a project from Optimization Settings to see results.")
        return
    layout = result.layout
    scoring = result.optimization_result.best_score_result
    diagnostics = layout.statistics.metadata.get("diagnostics", {}) if layout.statistics else {}
    proximity = diagnostics.get("proximity")
    if proximity is None:
        proximity = proximity_results(layout)
    access = diagnostics.get("access")
    if access is None:
        access = access_results(layout)
    site = diagnostics.get("site")
    if site is None:
        site = site_results(layout)
    routing = diagnostics.get("routing") or FlowRouter().route_with_diagnostics(layout).to_dict()
    expansion_occupied = sum(row["occupied_area"] for row in site
                             if row["feature_type"] == "expansion")
    st.subheader("Layout Results")
    metrics = st.columns(4)
    metrics[0].metric("Engineering score", "%.1f / 100" % scoring.score)
    metrics[1].metric("Hard violations", scoring.hard_violation_count)
    metrics[2].metric("Soft violations", scoring.soft_violation_count)
    crossings = diagnostics.get("crossings")
    metrics[3].metric("Flow crossings", len(crossings if crossings is not None else flow_crossings(layout)))
    status = st.columns(5)
    status[0].metric("Proximity", "%s / %s" % (sum(bool(row["passed"]) for row in proximity), len(proximity)))
    status[1].metric("Access", "%s / %s" % (sum(bool(row["satisfied"]) for row in access), len(access)))
    status[2].metric("Expansion", ("N/A" if not any(zone.zone_type.value == "expansion"
                                                    for zone in layout.site_zones) else
                                   "Clear" if expansion_occupied <= 1e-8 else "Occupied"))
    status[3].metric("Routing fallbacks", routing.get("fallback_count", 0))
    status[4].metric("Runtime", "%.1f s" % result.timings.get("total_runtime", 0.0))
    show_clearance = st.checkbox("Clearance zones", value=False)
    show_proximity = st.checkbox("Proximity connections", value=False)
    fig = PlotlyLayoutRenderer(show_clearance=show_clearance).render(layout)
    if show_proximity:
        import plotly.graph_objects as go
        placements = {placement.unit_id: placement for placement in layout.placements}
        for relation in layout.proximity_relationships:
            if relation.unit_id_a in placements and relation.unit_id_b in placements:
                a, b = placements[relation.unit_id_a], placements[relation.unit_id_b]
                fig.add_trace(go.Scatter(x=[a.centroid.easting, b.centroid.easting],
                                         y=[a.centroid.northing, b.centroid.northing], mode="lines",
                                         name="Proximity", legendgroup="Proximity",
                                         line={"color": "#a65224", "dash": "dot"},
                                         hovertext=relation.relationship_id, hoverinfo="text"))
    st.plotly_chart(fig, use_container_width=True)
    left, right = st.columns(2)
    with left:
        st.markdown("**Objective contribution**")
        st.dataframe(pd.DataFrame([{"Objective": key, "Raw": str(item.raw_metric),
                                   "Quality": round(item.normalized_metric, 2),
                                   "Configured": item.configured_weight,
                                   "Effective": round(item.effective_weight, 2),
                                   "Points": round(item.weighted_contribution, 2)}
                                  for key, item in scoring.objective_breakdown.items()]),
                     hide_index=True, use_container_width=True)
        st.caption("Base %.1f - hard %.1f - soft %.1f + rewards %.1f = %.1f. Weight scale %.3f." % (
            scoring.base_score, scoring.hard_penalty, scoring.soft_penalty,
            scoring.reward_total, scoring.score, scoring.weight_scale))
    with right:
        st.markdown("**Penalties**")
        st.dataframe(pd.DataFrame([{"Constraint": key, "Penalty": round(value, 2)} for key, value in
                                   scoring.penalty_by_constraint.items()]), hide_index=True, use_container_width=True)
    st.markdown("**Proximity results**")
    rows = proximity
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.caption("No pairwise requirements set.")
    with st.expander("Site and access checks"):
        groups = diagnostics.get("group_relationships")
        if groups is None:
            groups = group_relationship_results(layout)
        for label, rows in (("Site occupancy", site), ("Access", access), ("Group relationships", groups)):
            st.markdown("**%s**" % label)
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            else:
                st.caption("No checks configured or no conflicts found.")
    st.markdown("**Process routes**")
    st.dataframe(pd.DataFrame([{"Source": route["source_unit_id"], "Target": route["target_unit_id"],
                               "Routed length": round(route["length"], 2), "Flow type": route["flow_type"],
                               "Gravity preferred": route["gravity_preferred"], "Status": route["status"],
                               "Detour": round(route["detour_ratio"], 2), "Bends": route["bends"],
                               "Obstacle conflicts": route["obstacle_conflicts"],
                               "Corridor usage": route["corridor_usage"]}
                              for route in routing["routes"]]), hide_index=True, use_container_width=True)
    with st.expander("Scenario comparison"):
        scenarios = st.session_state.setdefault("saved_scenarios", [])
        name = st.text_input("Scenario name", value="Scenario %s" % (len(scenarios) + 1))
        if st.button("Save current run as scenario"):
            if not name.strip() or any(item.name == name.strip() for item in scenarios):
                st.error("Use a unique scenario name.")
            else:
                run_settings = layout.statistics.metadata.get("diagnostics", {}).get("optimization_settings", {})
                scenarios.append(ScenarioResult.from_run(name.strip(), st.session_state.run_input,
                    result, run_settings.get("seed", 42),
                    run_settings.get("candidate_count", 10),
                    run_settings.get("iterations", 100),
                    run_settings.get("algorithm", "simulated_annealing")))
                st.success("Scenario saved.")
        selected = st.multiselect("Compare saved scenarios", [item.name for item in scenarios],
                                  max_selections=5)
        if len(selected) >= 2:
            chosen = [item for item in scenarios if item.name in selected]
            st.dataframe(pd.DataFrame(compare_scenarios(chosen)), hide_index=True,
                         use_container_width=True)
            for tab, item in zip(st.tabs([entry.name for entry in chosen]), chosen):
                with tab:
                    st.json({"settings": item.optimization_settings,
                             "objectives": {key: value.to_dict() for key, value in
                                            item.score_result.objective_breakdown.items()}})
                    st.plotly_chart(PlotlyLayoutRenderer().render(item.layout), use_container_width=True,
                                    key="scenario_preview_" + item.name)
        elif scenarios:
            st.caption("Select at least two saved scenarios to compare.")
    if layout.violations:
        st.markdown("**Violations**")
        st.dataframe(pd.DataFrame([{"Constraint": v.constraint_id, "Units": ", ".join(v.affected_units),
                                   "Penalty": v.penalty, "Description": v.description} for v in layout.violations]),
                     hide_index=True, use_container_width=True)
    st.markdown("**Download**")
    cols = st.columns(4)
    for index, (label, key) in enumerate((("PDF report", "pdf"), ("PNG layout", "png"),
                                           ("JSON layout", "layout_json"), ("Interactive HTML", "html"))):
        path = result.exported_files.get(key)
        if path and Path(path).exists():
            cols[index].download_button(label, Path(path).read_bytes(), file_name=Path(path).name,
                                        use_container_width=True)


def main():
    st.set_page_config(page_title="Plant AutoLayout Engine", layout="wide")
    st.markdown("""<style>.block-container{max-width:1250px;padding-top:1.2rem}h1{font-size:1.85rem!important;letter-spacing:0}div[data-testid="stMetric"]{border-top:2px solid #176c80;padding-top:.5rem}</style>""", unsafe_allow_html=True)
    if "project" not in st.session_state:
        _load_sample("Water Treatment Plant")
    if "stage_next" in st.session_state:
        st.session_state.stage = st.session_state.pop("stage_next")
    st.title("Plant AutoLayout Engine")
    st.caption("Preliminary plant layout studies from site, unit, process and distance inputs")
    with st.sidebar:
        source = st.selectbox("Project template", list(SAMPLES))
        if st.button("Load template", use_container_width=True):
            _load_sample(source)
            st.rerun()
        upload = st.file_uploader("Open JSON or XLSX", type=["json", "xlsx", "xlsm"])
        if upload is not None and st.button("Use uploaded project", use_container_width=True):
            try:
                if upload.name.lower().endswith(".json"):
                    project = json.loads(upload.getvalue().decode("utf-8"))
                    parse_project_data(project)
                else:
                    with tempfile.TemporaryDirectory() as directory:
                        path = Path(directory) / upload.name
                        path.write_bytes(upload.getvalue())
                        project = _layout_to_input(parse_excel_file(str(path)))
                st.session_state.project = project
                st.session_state.pop("run_result", None)
                for key in ("boundary_table", "groups_table", "units_table", "flow_table", "proximity_table", "rules_table",
                            "zones_table", "structures_table", "corridors_table", "group_rules_table", "roads_table"):
                    st.session_state.pop(key, None)
                st.rerun()
            except (ParserError, ValueError, OSError, RuntimeError) as error:
                st.error("Input error: %s" % error)
            except Exception:
                logging.exception("Unexpected project input failure")
                st.error("The project could not be loaded. Review the server log and check the input file.")
        st.divider()
        stage = st.radio("Workflow", STAGES, key="stage")
    project = st.session_state.project
    if stage == "Project Setup":
        _setup(project)
    elif stage == "Site Boundary":
        _boundary(project)
    elif stage == "Site Features":
        _site_features(project)
    elif stage == "System Groups":
        _groups(project)
    elif stage == "Units":
        _units(project)
    elif stage == "Flow":
        _flow(project)
    elif stage == "Proximity":
        _proximity(project)
    elif stage == "Corridors / Roads":
        _corridors(project)
    elif stage == "Optimization Settings":
        _settings(project)
    else:
        _results()


if __name__ == "__main__":
    main()
