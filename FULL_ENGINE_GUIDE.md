# WTP AutoLayout Engine - Full System Guide

This guide explains how the WTP AutoLayout Engine is organized, how the full pipeline runs, what each engine does, and which algorithms are used.

The system is a Python-based engineering layout assistant for preliminary Water Treatment Plant layout generation. It accepts structured project inputs, generates candidate unit placements, checks engineering constraints, scores layouts, optimizes them with lightweight search algorithms, and exports visual and data outputs.

It is not a final construction drawing tool. It does not perform hydraulic simulation, CAD/DXF generation, BIM/IFC export, PDF extraction, or detailed construction documentation.

## 1. Quick Start

### Run The Streamlit Launcher UI

From PowerShell:

```powershell
cd path\to\plant-autolayout-engine
.\launch_wtp_ui.bat
```

Then open:

```text
http://localhost:8501
```

Or run Streamlit through the active Python environment:

```powershell
python -m streamlit run app.py
```

### Run The CLI

```powershell
cd path\to\plant-autolayout-engine
python -m wtp_autolayout.cli.main --input sample_data/sample_wtp_input.json --output outputs --algorithm simulated_annealing --candidate-count 10 --iterations 100 --seed 42 --verbose
```

## 2. Full Pipeline Overview

The complete system pipeline is:

```text
Input JSON/XLSX
  -> Parser
  -> Engineering Data Model
  -> Candidate Generator
  -> Geometry Engine
  -> Constraint Engine
  -> Scoring Engine
  -> Optimization Engine
  -> Visualization Engine
  -> Export Engine
  -> CLI or Streamlit UI output
```

In practical terms:

1. The user provides a JSON or Excel project input.
2. The parser converts it into a `Layout` object.
3. The candidate generator creates initial unit placements.
4. Geometry checks ensure footprints are inside the boundary, non-overlapping, and clearance-safe.
5. Constraint checks create `Violation` objects.
6. Scoring converts violations and engineering objectives into a layout score.
7. The optimizer ranks and optionally refines candidates.
8. The renderer creates PNG and interactive HTML views.
9. The exporter writes JSON, PNG, PDF, and optimization result files.
10. The CLI or Streamlit UI presents the result.

## 3. Project Structure

```text
wtp_autolayout/
  models/          Core engineering data model
  parsers/         JSON and Excel input parsing
  geometry/        Shapely geometry conversion and validation
  constraints/     Constraint registry and rule evaluation
  scoring/         Penalty and multi-objective reward scoring
  knowledge/       WTP engineering clusters and relationships
  candidates/      Initial candidate layout generation
  optimization/    Ranked, local search, and simulated annealing optimization
  visualization/   Matplotlib and Plotly renderers
  export/          JSON, PNG, and PDF exporters
  cli/             End-to-end command line runner

sample_data/       Example JSON and Excel project inputs
references/        Reference PDFs and archive drawings
outputs/           Generated results
tests/             Unit tests
app.py             Streamlit launcher UI
launch_wtp_ui.bat  Windows UI launcher
```

## 4. Core Data Model

The data model lives in `wtp_autolayout/models/`.

Important classes:

- `Coordinate`: easting, northing, optional elevation, optional coordinate system.
- `Boundary`: site polygon as ordered coordinates.
- `EngineeringUnit`: physical WTP unit, such as clarifier, filter, chemical house, sludge sump.
- `Placement`: proposed location and rotation for a unit.
- `FlowEdge`: connection from one unit to another.
- `FlowGraph`: list of units and directed flow edges.
- `Constraint`: input-level constraint definition.
- `Violation`: evaluated rule failure.
- `Road`: optional access road path.
- `Drain`: optional drainage path.
- `LayoutStatistics`: numerical summary fields.
- `Layout`: complete project or candidate layout.
- `OptimizationResult`: data model result object.

Important enums:

- `UnitCategory`
- `ShapeType`
- `HazardLevel`
- `ConstraintType`
- `ConstraintClassification`
- `Severity`
- `FlowType`
- `LayoutMode`
- `OptimizationStatus`

Validation built into the data model:

- IDs are required.
- Boundary must have at least 3 vertices.
- Width, length, and diameter must be positive when supplied.
- Rectangles and squares require width and length.
- Circles require diameter.
- Flow source and target cannot be the same.
- Weights, penalties, and clearances must be non-negative.
- Nested fields such as placements, roads, drains, and boundaries validate expected object types.

## 5. Parser Engine

The parser layer lives in `wtp_autolayout/parsers/`.

Supported input formats:

- JSON
- Excel `.xlsx`

### JSON Parser

Main functions:

```python
from wtp_autolayout.parsers import parse_json_file, parse_json_text
```

Expected JSON sections:

- `boundary`
- `units`
- `flow_edges`
- optional `placements`
- optional `roads`
- optional `drains`
- optional `constraints`
- optional `optimization_settings`
- optional `metadata`

The parser:

- sorts boundary vertices by `vertex_order`
- maps strings into enums
- validates missing fields
- validates unit IDs
- validates flow references
- preserves optimization settings in metadata
- maps `optimization_settings.layout_mode` to `LayoutMode`

### Excel Parser

Main function:

```python
from wtp_autolayout.parsers import parse_excel_file
```

Required sheets:

- `Boundary`
- `Units`
- `Flow`
- `Constraints`

Optional sheets:

- `Roads`
- `Drains`
- `OptimizationSettings`
- `Metadata`

Excel is read with `pandas` and `openpyxl`, then converted into the same internal dictionary structure used by the JSON parser.

## 6. Geometry Engine

The geometry engine lives in `wtp_autolayout/geometry/`.

Dependency:

- `shapely`

Main class:

```python
from wtp_autolayout.geometry import GeometryEngine
```

### Shape Conversion

The engine converts:

- `Boundary` to Shapely `Polygon`
- rectangle units to rotated polygons
- square units to rotated polygons
- circular units to buffered Shapely circles
- clearance zones to buffered polygons

### Geometry Checks

The engine checks:

- boundary validity
- unit geometry validity
- inside-boundary containment
- overlaps
- distances
- clearance violations
- duplicate placements
- missing placements

Overlap logic:

- Equal geometries count as overlap.
- Positive-area intersections count as overlap.
- Touching boundaries do not count as overlap.

Clearance logic:

- Clearance violation requires positive-area intersection.
- Touching clearance boundaries do not count as violations.
- A footprint entering another unit clearance zone is a violation.

### `validate_layout_geometry()`

Returns a `LayoutGeometryValidationResult` with:

- `inside_boundary_violations`
- `overlap_violations`
- `clearance_violations`
- `invalid_geometry_errors`

This function does not mutate the layout.

## 7. Constraint Engine

The constraint engine lives in `wtp_autolayout/constraints/`.

Main class:

```python
from wtp_autolayout.constraints import ConstraintEngine, default_wtp_engine
```

The default WTP engine registers:

- `GeometryValidityConstraint`
- `BoundaryContainmentConstraint`
- `OverlapConstraint`
- `MinimumClearanceConstraint`
- `SludgeIsolationConstraint`
- `ChemicalSafetyConstraint`
- `ResidentialSeparationConstraint`
- `ProcessAdjacencyConstraint`
- `GravityFlowConstraint`

### Constraint Evaluation API

```python
engine = default_wtp_engine()
violations = engine.evaluate(layout)
```

Available methods:

- `evaluate(layout)`: enabled constraints only
- `evaluate_enabled(layout)`: enabled constraints only
- `evaluate_all(layout)`: enabled and disabled constraints

The engine uses an evaluation context so geometry validation is cached during one evaluation pass. This avoids recomputing `GeometryEngine.validate_layout_geometry()` once per geometry-backed constraint.

### Hard Geometry Constraints

Hard constraints use very large penalties to ensure infeasible layouts are not preferred:

- Boundary containment: `C-001`
- Overlap: `C-002`
- Minimum clearance: `C-003`
- Geometry validity: `C-004`

Each hard geometry violation has a penalty of `1_000_000.0`.

### Soft Engineering Constraints

Soft constraints use proportional penalties:

- Sludge isolation: sludge should be away from admin, residential, and clear-water units.
- Chemical safety: chemical units should be away from occupied units.
- Residential separation: occupied units should be separated from sludge and chemical units.
- Process adjacency: connected flow units should not be too far apart.
- Gravity flow: gravity-required flow should not rise from source to target.

## 8. Engineering Knowledge Base

The knowledge base lives in `wtp_autolayout/knowledge/`.

It centralizes WTP engineering heuristics so the candidate generator and scorer do not hard-code every unit relationship in separate places.

### Clusters

Hydraulic cluster:

- cascade aerator
- inlet channel / parshall flume
- distribution chamber
- flash mixer
- drop chamber
- clarifier
- filters

Sludge cluster:

- sludge sump
- sludge thickener
- centrifuge
- disposal

Chemical cluster:

- chemical house
- chlorine system

Clear-water cluster:

- clear water reservoir
- pump house

### Relationship Helpers

```python
from wtp_autolayout.knowledge import get_cluster, get_relationship

get_cluster("flash mixer")
get_relationship("flash mixer", "drop chamber")
```

Available functions:

- `get_cluster(unit_type)`
- `get_relationship(unit_a, unit_b)`
- `get_preferred_distance()`
- `get_separation_rule()`

Important relationships:

- flash mixer -> drop chamber: preferred adjacency
- drop chamber -> clarifier: preferred adjacency
- clear water reservoir -> pump house: preferred adjacency
- sludge cluster away from admin/residential
- chemical house needs pipe accessibility, not forced adjacency

## 9. Scoring Engine

The scoring engine lives in `wtp_autolayout/scoring/`.

Main class:

```python
from wtp_autolayout.scoring import ScoringEngine
```

### Version 1 Penalty Scoring

The older penalty-only method still exists:

```python
result = scoring_engine.score_violations(violations)
```

Formula:

```text
score = max(0, 100 - total_penalty)
```

This path is kept for backward compatibility.

### Version 2 Multi-Objective Engineering Scoring

The normal layout scoring path is:

```python
result = scoring_engine.score_layout(layout)
```

This evaluates constraints, then applies engineering rewards.

Current formula:

```text
score = clamp(ENGINEERING_BASE_SCORE - total_penalty + reward_total, 0, 100)
```

Where:

```text
ENGINEERING_BASE_SCORE = 65.0
MAX_ENGINEERING_REWARD = 35.0
```

So a merely feasible layout starts around 65, and a high-quality feasible layout can climb toward 100.

### Penalty Components

The scoring engine separates:

- hard penalty
- soft penalty
- total penalty
- hard violation count
- soft violation count
- penalty by constraint
- penalty by severity

### Engineering Reward Objectives

Implemented in `EngineeringObjectiveCalculator`.

#### 1. Hydraulic Transfer Efficiency

Function:

```python
calculate_pipe_efficiency()
```

Rewards shorter flow transfer distances between connected process units. Flow edge weights influence the weighted average.

#### 2. Gravity Reward

Function:

```python
calculate_gravity_reward()
```

Rewards gravity-preferred flow edges where:

```text
source elevation >= target elevation
```

If elevations are missing, the edge is ignored for this objective.

#### 3. Cluster Arrangement Reward

Function:

```python
calculate_cluster_reward()
```

Rewards:

- preferred adjacency pairs
- related units in the same engineering cluster
- connected flow units that are reasonably close

#### 4. Compactness Reward

Function:

```python
calculate_compactness_reward()
```

Rewards a compact bounding envelope of placed unit centroids relative to boundary area.

#### 5. Expansion Allowance Reward

Function:

```python
calculate_expansion_reward()
```

Rewards preserving free land and avoiding occupation of a future expansion reserve.

If `layout.metadata["expansion_zones"]` exists, that is used. Otherwise, the engine assumes a default east/southeast reserve band based on the reference layouts.

### Default Reward Weights

From `scoring/rewards.py`:

```text
pipe_efficiency: 12.0
gravity: 8.0
cluster: 10.0
compactness: 8.0
expansion: 4.0
```

The total reward is capped at `35.0`.

## 10. Candidate Generator

The candidate generator lives in `wtp_autolayout/candidates/`.

Main class:

```python
from wtp_autolayout.candidates import CandidateGenerator
```

Purpose:

- Create initial feasible placements for all units.
- Preserve valid existing placements unless `replace_existing=True`.
- Avoid boundary, overlap, and clearance failures.
- Produce one or many candidate layouts.

### Input Validation

The generator rejects:

- layouts with no units
- duplicate unit IDs
- placements that reference unknown unit IDs
- duplicate existing placements for the same unit

### Unit Ordering

Units are placed in process order first:

```text
units with process_order -> sorted by process_order
units without process_order -> original order
```

This helps upstream process units get placed before downstream units.

### Layout Modes

Candidate point selection supports:

- `FIT`: broad random placement within boundary bounds
- `SHRINK`: gaussian placement near site center
- `BALANCED`: process-order-biased placement across the boundary

### Cluster-Aware Placement

Before placing individual units, the generator calculates cluster anchors:

```text
hydraulic: near central process band
sludge: lower-left / separated zone
chemical: upper-left / pipe-accessible zone
clear_water: upper-right / clear-water zone
```

For the first 70 percent of placement attempts, the generator samples near the relevant cluster anchor. For the remaining attempts, it falls back to the general layout strategy. This preserves engineering preference without making generation brittle.

### Geometry Feasibility

Every proposed placement must pass:

- valid unit geometry
- inside boundary
- no overlap with already placed units
- no clearance violation with already placed units

If no valid placement is found after `max_attempts_per_unit`, candidate generation fails.

## 11. Optimization Engine

The optimization engine lives in `wtp_autolayout/optimization/`.

Main class:

```python
from wtp_autolayout.optimization import Optimizer
```

Supported algorithms:

- `ranked`
- `local_search`
- `simulated_annealing`

The optimizer does not use OR-Tools or mathematical programming. It uses standard-library random sampling and lightweight local refinement.

### Algorithm 1: Ranked Candidates

Process:

1. Generate `N` candidate layouts.
2. Score each candidate with `ScoringEngine`.
3. Sort by score descending.
4. Return the best layout and ranked candidate list.

This is the fastest mode and performs no refinement.

### Algorithm 2: Local Search

Process:

1. Start from the best initial candidate.
2. Randomly select one unit placement.
3. Propose a small x/y move.
4. Optionally change rotation for rectangles and squares.
5. Reject if geometry becomes invalid.
6. Score the proposal.
7. Accept only if score improves.
8. Repeat for `max_iterations`.

This is greedy hill-climbing. It is stable and simple, but can get stuck in local optima.

### Algorithm 3: Simulated Annealing

Process:

1. Start from the best initial candidate.
2. Randomly propose a neighbor layout.
3. Reject hard-constraint-invalid proposals.
4. Score the proposal.
5. Always accept score improvements.
6. Sometimes accept worse layouts using:

```text
accept_probability = exp(delta / temperature)
delta = new_score - current_score
```

7. Reduce temperature each iteration:

```text
temperature = temperature * cooling_rate
```

Defaults:

```text
initial_temperature = 10.0
cooling_rate = 0.95
```

Simulated annealing can escape small local traps, but it is still a lightweight heuristic optimizer.

### Feasibility Handling

The optimizer:

- prefers hard-constraint-feasible layouts
- rejects hard-invalid local-search and annealing proposals
- returns `SUCCESSFUL`, `PARTIAL`, or `FAILED`

Status logic:

- `SUCCESSFUL`: best candidate passes hard constraints
- `PARTIAL`: candidates exist but best still has hard violations
- `FAILED`: no candidates could be generated

## 12. Visualization Engine

The visualization engine lives in `wtp_autolayout/visualization/`.

There are two renderers:

- `LayoutRenderer`: static Matplotlib renderer
- `PlotlyLayoutRenderer`: interactive Plotly renderer

### Matplotlib Renderer

Used for PNG and PDF reports.

Draws:

- boundary polygon
- unit footprints
- labels
- process flow arrows
- optional clearance buffers
- violations
- roads
- drains
- legend
- north arrow
- equal aspect ratio

### Plotly Renderer

Used for interactive browser visualization.

Supports:

- zoom
- pan
- legend layer toggles
- hover metadata
- HTML export

Unit hover metadata includes:

- ID
- name
- category
- dimensions
- coordinates
- elevation
- clearance
- cluster

Pipe hover metadata includes:

- source
- destination
- length
- pipe type
- gravity preference

## 13. Export Engine

The export engine lives in `wtp_autolayout/export/`.

Exporters:

- `JSONExporter`
- `ImageExporter`
- `PDFExporter`

### JSON Export

Creates:

- `optimized_layout.json`
- `optimization_result.json`

Uses existing `to_dict()` methods and clean JSON serialization.

### PNG Export

Wraps the Matplotlib renderer:

```python
ImageExporter().export_png(layout, "outputs/optimized_layout.png")
```

### PDF Export

Creates a simple engineering report with:

- title
- generation timestamp
- layout ID
- score
- unit count
- placement count
- violation count
- violation summary table
- optional embedded layout image

The PDF exporter uses `reportlab`.

## 14. CLI Runner

The CLI lives in `wtp_autolayout/cli/`.

Main entrypoint:

```bash
python -m wtp_autolayout.cli.main
```

Core runner:

```python
from wtp_autolayout.cli.runner import run_pipeline
```

The runner:

1. Detects input extension.
2. Parses JSON or XLSX.
3. Builds geometry, constraint, scoring, candidate, and optimizer objects.
4. Generates ranked candidates.
5. Runs selected optimization algorithm.
6. Scores and updates the best layout.
7. Exports PNG, JSON, and PDF if enabled.
8. Records timing.
9. Returns `CLIRunResult`.

CLI arguments:

```text
--input
--output
--algorithm ranked|local_search|simulated_annealing
--layout-mode FIT|SHRINK|BALANCED
--candidate-count
--iterations
--seed
--no-pdf
--no-png
--no-json
--verbose
```

## 15. Streamlit Launcher UI

The launcher is `app.py`.

Start it with:

```powershell
.\launch_wtp_ui.bat
```

or:

```powershell
python -m streamlit run app.py
```

The UI supports:

- sample JSON run
- sample Excel run
- upload JSON/XLSX
- table-editor input mode
- boundary editing table
- unit editing table
- flow editing table
- algorithm settings
- candidate count
- iterations
- seed
- interactive Plotly result
- PDF download
- PNG download
- JSON download
- HTML download

The UI uses the CLI runner internally, so it exercises the same engine path as command-line execution.

## 16. Input Data Details

### Boundary

Each boundary row needs:

- `boundary_id`
- `coordinate_system`
- `easting`
- `northing`
- optional `elevation`
- `vertex_order`

Boundary vertices are sorted by `vertex_order`.

### Units

Each unit needs:

- `unit_id`
- `name`
- `category`
- `shape_type`
- dimensions
- `required_clearance`
- `system_group`
- `hazard_level`
- optional `process_order`

Dimension rules:

- Rectangle: width and length
- Square: equal width and length
- Circle: diameter

### Flow

Each flow edge needs:

- `edge_id`
- `source_unit_id`
- `target_unit_id`
- `flow_type`
- `gravity_required`
- `weight`

Flow references must point to existing unit IDs.

### Constraints

Each constraint row includes:

- `constraint_id`
- `name`
- `constraint_type`
- `classification`
- `severity`
- `weight`
- `enabled`
- `description`

## 17. Outputs

Typical output directory:

```text
outputs/
  optimized_layout.png
  optimized_layout.pdf
  optimized_layout.json
  optimization_result.json
  optimized_layout.html
```

Depending on CLI flags or UI downloads, some files may be disabled or omitted.

## 18. Tests And Validation

Run all tests:

```powershell
python -m unittest discover -s tests
```

Compile check:

```powershell
python -m compileall wtp_autolayout tests app.py
```

Current test coverage includes:

- data model validation
- parser behavior
- geometry creation and validation
- constraints
- scoring and multi-objective rewards
- knowledge base rules
- candidate generation
- optimization algorithms
- visualization and export
- CLI execution

## 19. Reference Drawing Insights Used

The archived L&T reference PDFs were used only as engineering references, not as parsed inputs.

Observed layout patterns:

- Hydraulic/process units form a strong process train.
- Clarifiers and filters are grouped in a process band.
- Sludge facilities are grouped separately and offset from occupied/clean-water areas.
- Chemical facilities require pipe accessibility but not forced adjacency.
- Clear-water reservoir and pump house belong together.
- Roads and access corridors matter visually and operationally.
- Future expansion zones should remain available instead of being consumed by compact placement.

These observations informed:

- engineering clusters
- preferred relationships
- cluster-aware candidate generation
- expansion reward scoring
- road/drain visualization

## 20. Known Limitations

The system is still a preliminary engineering layout assistant.

Known limitations:

- no CAD/DXF export
- no BIM/IFC export
- no hydraulic simulation
- no pipe sizing calculation
- no earthwork calculation
- no structural design
- no electrical or instrumentation design
- no PDF extraction or automatic drawing digitization
- no final construction drawing generation
- no regulatory approval workflow

## 21. How To Extend The System

Recommended future improvements:

1. Add real site constraints such as exclusion zones, existing buildings, canals, and terrain corridors.
2. Add pipe route estimation instead of centroid-to-centroid distance.
3. Add hydraulic head-loss calculations.
4. Add road-access constraints and maintenance access scoring.
5. Add expansion-zone input in JSON/Excel schema.
6. Add CAD/DXF export.
7. Add richer Streamlit table-to-project editing and validation.
8. Add scenario comparison reports.
9. Add deterministic grid or packing heuristics for large WTPs.
10. Add proper georeferenced coordinate support if GIS integration is required.

## 22. Mental Model

Think of the engine in three layers:

### Layer 1: Is It Valid?

Handled by:

- data model validation
- parser validation
- geometry engine
- hard constraints

This layer prevents impossible layouts.

### Layer 2: Is It Engineering-Sensible?

Handled by:

- engineering constraints
- knowledge base
- scoring rewards
- cluster-aware generation

This layer distinguishes two feasible layouts.

### Layer 3: Can We Improve It?

Handled by:

- ranked candidate generation
- local search
- simulated annealing

This layer searches for a better-scoring layout without changing the underlying engineering rules.

That separation is the main architecture: data and rules stay stable, while generation and optimization can improve over time.
