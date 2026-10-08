# Generalized Plant AutoLayout Engine

The application is a preliminary plant layout assistant. It accepts WTP and basic petrochemical projects through JSON, Excel, or the Streamlit editor. It generates candidate unit placements, checks geometry and engineering relationships, ranks layouts, and exports JSON, PNG, PDF, and interactive HTML.

## Pipeline

```text
JSON/XLSX/UI -> parser -> Layout -> plant profile -> candidate generator
             -> geometry/constraints -> scoring -> optimizer
             -> routed visualizations -> exports
```

The package name remains `wtp_autolayout` for compatibility. Shared algorithms do not require a separate engine for each plant type. `wtp_autolayout/profiles/base.py` supplies plant defaults. The WTP profile selects the established WTP safety and adjacency heuristics; the petrochemical profile selects only generic geometry, group, flow, and user-defined pairwise rules. Petrochemical regulatory distances are not inferred.

## Data Model

`Layout` carries `plant_type`, ordered `boundary`, `units`, `system_groups`, `flow_graph`, `proximity_relationships`, placements, infrastructure, violations, statistics, and metadata. `EngineeringUnit.system_group` is a group ID. `SystemGroup.preferred_radius` is optional and controls how tightly a group is encouraged to cluster. Flow is process connectivity; proximity is a spatial requirement; groups are logical systems; `process_order` is generation order.

`SpatialRelationship` uses footprint-to-footprint distance in the site coordinate units:

| Type | Meaning |
| --- | --- |
| `min_distance` | Actual gap must be at least `distance`. |
| `max_distance` | Actual gap must be no greater than `distance`. |
| `target_distance` | Deviations above or below `distance` are penalized. A hard target requires equality within 0.000001 coordinate units. |
| `preferred_near` | Soft preference for a gap no greater than `distance`. |

Hard violations add at least 100 penalty points and fail feasibility. Soft penalties equal deviation times the relationship weight. Duplicate pair/type rules and contradictory minimum/maximum bounds are rejected. Distances should be specified in a projected coordinate system with consistent linear units.

## Boundary Input

The UI takes Easting and Northing. The parser also accepts optional `boundary_id`, `coordinate_system`, `elevation`, and `vertex_order`. If every row has `vertex_order`, that order is preserved and a Shapely polygon validates it. If no row has it, duplicate points are rejected, centroid/polar-angle sorting orders ordinary convex perimeter points, and Shapely verifies the result. A repeated closing point is removed; Shapely closes the polygon. An unordered concave set is ambiguous, so the parser requests explicit `vertex_order`. Partly ordered, self-intersecting, collinear, or zero-area boundaries fail with parser errors.

## Candidate Generation

The generator first validates units and existing placements, then samples points inside the site boundary. It uses process order and group anchors, with WTP cluster anchors supplied through the WTP profile. It samples near already placed units with explicit relationships during early attempts, then falls back to general sampling. Every proposed footprint must fit the boundary, avoid overlap and required clearance conflicts, avoid supplied `metadata.exclusion_zones`, and satisfy hard pairwise rules against already placed units. `FIT`, `SHRINK`, and `BALANCED` retain their existing sampling behavior; `BALANCED` also uses process-order bias. Candidate generation never mutates the input layout.

## Constraints And Scoring

Geometry constraints cover validity, containment, overlap, and clearance. WTP adds its existing sludge, chemical, residential, process adjacency, and gravity checks. Every project evaluates explicit proximity rules and straight-line process-flow crossing checks. Crossings between edges sharing a unit are ignored. The UI shows the actual and required footprint distances, pass/fail state, and penalty for each pair.

The layout score is `clamp(65 - total_penalty + reward_total, 0, 100)`. The engineering base is 65 and the reward cap is 35. Each plant profile owns its objective weights and scoring thresholds. WTP weights are pipe efficiency 9, gravity 5, cluster 4, group arrangement 5, proximity 5, flow crossing 3, compactness 2, and expansion 2. Petrochemical weights are pipe efficiency 8, gravity 0, cluster 0, group arrangement 9, proximity 9, flow crossing 5, compactness 2, and expansion 2. If configured weights exceed 35, every effective weight is multiplied by the same `35 / configured_total` factor. Individual objectives are never silently truncated. Both profiles use the same scoring engine. Hard invalid layouts cannot outrank a feasible layout through reward points alone.

`ScoringResult` contains hard/soft counts, penalty by constraint and severity, reward by objective, total score, and hard-feasibility status. Each objective reports a raw metric, normalized value, configured weight, effective weight, weighted contribution, penalty, and explanation. The shared weight scale is also reported. When requested, the score and reward breakdown are stored in `Layout.statistics.metadata.score_breakdown`. The optimizer uses these scores without changing its ranked, local search, or simulated annealing algorithms. Local search accepts improving feasible moves. Annealing may accept worse feasible moves according to temperature, but retains the best feasible result.

Group preferences are `strongly_clustered`, `loosely_clustered`, or `neutral`. Neutral groups receive no compactness reward; loose groups tolerate greater separation. WTP hydraulic and sludge groups are strongly clustered, while its chemical group is neutral. Petrochemical groups default to loose or neutral preferences. There is no automatic inter-group separation rule. Explicit pairwise relationships control required separation. Duplicate pair/type relationships and conflicting minimum/maximum distances are rejected; conflicting hard targets are rejected too. Proximity diagnostics report the pair, rule, required and actual footprint gap, deviation, classification, satisfaction, and penalty. A preferred-near relationship is always soft.

## Flow Topology And Display Routing

Topology uses straight centroid-to-centroid process connections to detect interior crossings and collinear overlaps. Ordinary shared unit endpoints and endpoint-only touches are excluded. Structured crossing events expose both flow IDs, type, and location; the older `flow_crossings()` pair API remains available. This topology metric remains independent of display routing, so a detoured line cannot hide a poor placement score.

`FlowRouter` uses a bounded, deterministic orthogonal grid search around unit footprints and the site boundary. Unrelated unit footprints and exclusion zones are obstacles, expanded by configurable routing clearance. It first seeks a route avoiding earlier display routes, then retries without that restriction. Grid lines are capped to keep the search finite. When no clear path exists, it reports an explicit straight-line fallback with `FALLBACK` or `BLOCKED` status; a route-level exception is reported as `FAILED` without crashing rendering. Route diagnostics include straight and routed lengths, detour ratio, bend count, obstacle conflicts, display-route crossings, and fallback count. The routing is preliminary visual planning, not detailed piping or hydraulic routing.

Routing is performed after optimization for display and reporting. Scoring uses straight-line topology and does not run the display router on every neighbor. Pairwise constraints and topology checks still add work during scoring as plant size grows.

## Scenarios And Outputs

The Results page can save named runs and compare two to five scenarios side by side. Each snapshot retains plant type, profile, settings, seed, algorithm, candidate count, iterations, layout, score breakdown, violations, proximity diagnostics, topology crossings, routing metrics, runtime, and output paths. The comparison table shows tradeoffs and does not declare a universal best run. A higher score may still have longer routes or different proximity outcomes. Each UI run gets a unique output directory.

Layout JSON retains existing fields and adds score and engineering diagnostics in `statistics.metadata`; optimization JSON includes the same diagnostics in its metadata. The PDF provides a concise engineering summary, objective table, proximity checks, crossings, route summary, runtime to report generation, and limitations. Runtime in final layout JSON is measured after export; PDF runtime is measured when the report is created. The PNG and Plotly views show preliminary display routes.

With a fixed seed, algorithm, candidate count, iterations, input, and software environment, scores, placements, and geometry diagnostics should repeat. Wall-clock runtime and PDF generation timestamps naturally differ. Floating-point or dependency changes across platforms can also affect exact values.

Matplotlib generates PNG/PDF drawings. Plotly generates the interactive HTML and UI view, with zoom, pan, hover details, and layer toggling. The UI can show clearance buffers and pairwise proximity lines. Roads and drains remain visible.

## Input Formats

JSON requires `boundary`, `units`, and `flow_edges` (the flow list may be empty). `plant_type` defaults to `wtp`. `system_groups` and `proximity_relationships` are optional. Example:

```json
{
  "layout_id": "concept_01",
  "plant_type": "petrochemical",
  "boundary": [
    {"easting": 0, "northing": 0},
    {"easting": 100, "northing": 0},
    {"easting": 100, "northing": 80},
    {"easting": 0, "northing": 80}
  ],
  "system_groups": [{"group_id": "process", "name": "Main Process", "preferred_radius": 40}],
  "units": [
    {"unit_id": "u1", "name": "Feed", "category": "process", "shape_type": "rectangle", "width": 10, "length": 8, "system_group": "process"},
    {"unit_id": "u2", "name": "Skid", "category": "process", "shape_type": "rectangle", "width": 12, "length": 8, "system_group": "process"}
  ],
  "flow_edges": [{"edge_id": "f1", "source_unit_id": "u1", "target_unit_id": "u2", "flow_type": "other"}],
  "proximity_relationships": [{"relationship_id": "r1", "unit_id_a": "u1", "unit_id_b": "u2", "relationship_type": "max_distance", "distance": 30, "classification": "soft", "weight": 1}]
}
```

Excel requires `Boundary`, `Units`, and `Flow`. Optional sheets are `Project` (key/value `plant_type`, `layout_id`, `project_name`), `Groups`, `Proximity`, `Constraints`, `Roads`, `Drains`, `OptimizationSettings`, and `Metadata`. The sample JSON and XLSX files in `sample_data/` show both plant types. Legacy WTP JSON/XLSX files parse unchanged, including `vertex_order`; missing plant type defaults to WTP.

## UI And Commands

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
python -m wtp_autolayout.cli.main --input sample_data/sample_general_wtp_input.json --output outputs/wtp --algorithm simulated_annealing --candidate-count 10 --iterations 100 --seed 42
python -m wtp_autolayout.cli.main --input sample_data/sample_petrochemical_input.xlsx --output outputs/petro --algorithm ranked --candidate-count 5 --seed 42
python -m unittest discover -s tests
python -m compileall wtp_autolayout tests app.py
```

The UI stages are Project Setup, Site Boundary, System Groups, Units, Flow, Proximity, Optimization Settings, and Results. Upload a JSON/XLSX project or load a sample, edit it, then run. Results show score and objective contributions, hard/soft violations, crossing count, pairwise checks, routes, and downloads. CLI outputs include the same layout JSON plus optimization result JSON, PNG, and PDF.

## Limits

The engine does not perform final plant engineering, hydraulic or process simulation, pipe sizing, HAZOP, regulatory compliance verification, detailed pipe routing, structural design, CAD/DXF/BIM export, PDF extraction, or construction drawings. Boundary auto-ordering is intentionally limited to unambiguous convex perimeter sets. Hard target distance is exact and can make random candidate generation impractical; use a soft target or a max/min interval for ordinary design work.

## Fixed Site Features And Project Rules

`Layout.site_zones`, `existing_structures`, `corridors`, and `group_relationships` are optional typed inputs. They do not become movable `EngineeringUnit` objects. `SiteZone` types are `exclusion`, `restricted`, `reserved`, and `expansion`; each has a hard/soft classification, clearance, weight, and provenance. A hard zone blocks a footprint plus unit clearance. A soft zone applies an occupancy-area penalty. An `ExistingStructure` is always fixed and hard, including its clearance. A hard corridor blocks placement within its width and setback; a soft corridor remains usable. Existing `metadata.exclusion_zones` are still treated as hard no-build polygons.

`EngineeringUnit` may set `access_required`, `max_access_distance`, `access_classification`, and `maintenance_clearance`. Access distance is measured from the unit footprint to the nearest width-aware `access`/`road` corridor or legacy road. No default maximum access distance is inferred. A hard access maximum affects feasibility; a soft one contributes a proportional penalty. `maintenance_clearance` increases the unit's isotropic spacing buffer to at least the specified value; it is not a side-specific maintenance-access design.

`GroupRelationship` supports `preferred_near`, `min_distance`, `max_distance`, and `neutral`. The actual distance is the minimum footprint-to-footprint gap across placed members of the two groups. This is separate from unit-pair proximity. Duplicate pair/type rules and conflicting group min/max bounds fail model validation. The `engineering_rules` input table is a convenience adapter with scopes `unit_pair`, `group_pair`, `unit_access`, and `zone_occupancy`; it maps into those typed models before evaluation. Rule IDs and source data remain in layout metadata. Every sample distance is illustrative project input, never a regulatory value.

```json
{
  "site_zones": [{"zone_id": "reserve_1", "name": "Future expansion", "zone_type": "expansion", "classification": "soft", "weight": 0.2, "provenance": "user_entered", "vertices": [{"easting": 70, "northing": 20}, {"easting": 90, "northing": 20}, {"easting": 90, "northing": 40}, {"easting": 70, "northing": 40}]}],
  "existing_structures": [{"structure_id": "fixed_1", "name": "Existing building", "vertices": [{"easting": 5, "northing": 5}, {"easting": 15, "northing": 5}, {"easting": 15, "northing": 15}, {"easting": 5, "northing": 15}]}],
  "corridors": [{"corridor_id": "access_1", "name": "Access", "corridor_type": "access", "width": 5, "classification": "hard", "path": [{"easting": 10, "northing": 10}, {"easting": 80, "northing": 10}]}],
  "group_relationships": [{"relationship_id": "g1", "group_id_a": "process", "group_id_b": "utilities", "relationship_type": "max_distance", "distance": 40, "classification": "soft"}]
}
```

An explicit expansion zone overrides the WTP inferred east/southeast expansion area. The display router avoids hard site features, respects its configurable unit clearance, and mildly prefers designated `routing`/`utility` corridors. It reports full/partial/no corridor use, detour, bends, conflicts, and fallback. This display route never changes topology crossing score. Site occupancy, access, and group diagnostics appear in Layout JSON, PDF, CLI summary, the UI, and scenario comparison. The 65-point base and 35-point reward cap remain; `access` and `group_relationship` quality objectives have zero profile weight unless an engineer explicitly configures a weight override.

### Engineering Boundary

This is preliminary plant-layout decision support. It does not perform detailed piping, hydraulic or process simulation, HAZOP, regulatory certification, structural/electrical/instrumentation design, final CAD/BIM, or construction drawings. User-entered requirements are not automatically verified against a standard.
