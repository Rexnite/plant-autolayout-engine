# Final Stabilization Notes

The projects under `scripts/synthetic_projects.py` are deterministic software stress fixtures only. They deliberately mix shapes, groups, flows, pairwise rules, exclusions, fixed structures, access/routing corridors, and expansion zones. Their scores do **not** establish engineering validity.

Baseline: 175 tests passed before editing. Final: **186 tests passed**, `compileall` passed for package, tests, app, and scripts, and 101 Python files parsed with Python 3.9 grammar. Execution used the available bundled Python runtime; an actual Python 3.9 runtime was not runnable on this machine.

## Reproduce

```powershell
python -m unittest discover -s tests
python -m compileall wtp_autolayout tests app.py
python -m scripts.stress_profile --units 25 --candidates 1 --iterations 0 --algorithm ranked --skip-exports --no-memory
python -m scripts.ui_smoke
python -m scripts.verify_demo
```

## Measured scaling

Stage times below are seconds on the local Windows validation machine, seed 42, one candidate, zero iterations, ranked mode, no memory tracing or exports. `optimization` is a separate call that **includes** another generation and scoring pass; it is not additive to the preceding stage measurements. Router timings are preliminary and depend strongly on obstacles and flow count.

| Units | Parse | Generate | Constraints | Score | Optimize | Route | Flows |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 0.001 | 0.021 | 0.008 | 0.008 | 0.029 | 0.049 | 5 |
| 25 | 0.002 | 0.109 | 0.018 | 0.021 | 0.154 | 0.504 | 12 |
| 50 | 0.003 | 0.396 | 0.039 | 0.061 | 0.405 | 4.418 | 25 |
| 75 | 0.003 | 0.974 | 0.055 | 0.086 | 1.348 | 10.163 | 37 |
| 100 | 0.005 | 1.657 | 0.080 | 0.293 | 3.972 | not run | 49 |

The 100-unit routing/export case was intentionally not run: the 75-unit router was already a 10-second non-demo path. The 50-unit fixture completed PNG/JSON/PDF generation; PNG rendering took about 6.5 seconds, JSON 0.004 seconds, PDF 0.014 seconds, and three files totaled about 243 KB. A 25-unit traced full run peaked at about 3 MB of Python-tracked allocations, but `tracemalloc` does not count all native Shapely/Matplotlib allocations, so this is not a process-RSS bound.

For 10 units, generation with 5/10/25 candidates took about 0.125/0.209/0.605 seconds. With one candidate, 30/100/250 local-search iterations took about 0.42/1.26/3.82 seconds after the geometry change; annealing took about 0.44/1.24/6.13 seconds. Longer runs cost more and show normal runtime variance. Scores on the 50+ fixtures fell to zero from many soft preference penalties; this highlights that large synthetic scores are not suitable as engineering quality comparisons.

## Profiled bottlenecks and fixes

1. Grid routing repeatedly sent distant segments through Shapely obstacle tests and rechecked the same undirected edges. Bounded edge caching and bounding-box rejection preserved route metrics. At 25 units, **traced** routing fell from about 28 seconds to 3.5 seconds; without tracing it took about 0.5 seconds.
2. Geometry validation rebuilt footprints and clearance buffers for every unit pair. Per-evaluation reuse and envelope rejection preserved violations. A 10-unit, 30-iteration local search fell from about 1.5 to 0.42 seconds. The public geometry API remains unchanged.
3. Routing and Matplotlib output remain the scaling limits. The router has a 4-64 line-per-axis configuration bound; it does not provide a live meeting guarantee for dense 50+ unit inputs.

## Failure and robustness checks

Automated checks cover: impossible boundary area; too many units; oversized unit; impossible hard minimum and maximum distances; contradictory pairwise and group rules; exclusion trapping; blocked route fallback; disconnected flow; duplicate IDs; malformed and self-intersecting boundary; zero/negative dimensions; missing fields; unknown group; invalid corridor; impossible hard access; optimizer candidate failure; unwritable export parent; shared flow endpoints; non-finite numbers; one candidate; zero iterations; and invalid annealing/router settings. Existing tests also cover touching footprints, rotated footprints, parser formats, scenarios, and exports.

Candidate failure text now names the failed unit, attempt count, site area, approximate placed footprint area, obstacle count, and rejection counts for boundary/site/overlap/clearance/access/hard rules. Proven envelope and total-footprint-area impossibilities are rejected before random retries. Other messages are **diagnostic guidance**, not a mathematical infeasibility certificate. Parser boundary errors retain the legacy `Invalid boundary` prefix and add a recheck action. Expected UI validation failures show concise messages; unexpected failures are logged server-side without a Python traceback on screen.

## Demonstration validation

`scripts/verify_demo.py` ran WTP three times (seed 42, 10 candidates, 100 annealing iterations) in separate output folders. Placements, score **87.92**, zero crossings, proximity/access rows, and routing metrics were identical; runtimes were 1.77, 2.89, and 2.88 seconds. Petrochemical scored **88.21** in 3.04 seconds. Both had zero hard and soft violations and zero routing fallbacks. PNG images opened through Pillow, PDFs through `pypdf` where available, JSON parsed with routing diagnostics present, and interactive HTML was non-empty. Separate folders prevent scenario overwrites.

`scripts/ui_smoke.py` used Streamlit AppTest to visit all input stages, run twice, inspect the nine summary metrics, save two scenarios, and open comparison with no app exception. It also exposed and verified the fix for blank optional cells from visited data tables. AppTest does not substitute for a browser-based visual QA pass on the meeting machine.

## Freeze guidance

- **Demo-ready:** fixed WTP/petro samples, parser, site and constraint checks, explainable scoring, seeded candidate ranking/refinement, scenario comparison, exports, basic UI workflow.
- **Experimental:** obstacle-aware route display, large/dense-project response time, generalized plant preferences, hard-infeasibility diagnostics.
- **Known limits:** preliminary layout only; no hydraulic simulation, detailed pipe sizing, CAD/DXF/BIM, PDF extraction, construction drawings, regulatory rule pack, or complete infeasibility proof.
- **Do not demo as final:** 50+ synthetic layouts, route output as a pipe design, synthetic scores as validation, or petrochemical illustrative distances as regulations.
- **Before showing Balaaji:** use the exact WTP preset, preflight the meeting machine and export folder, visually inspect the interactive result once, and say clearly that hydraulic and regulatory checks remain outside this tool. Python 3.9 syntax is a target, but only the available bundled Python runtime was used for execution here.

## File inventory

Changed: `app.py`; `wtp_autolayout/candidates/generator.py`; `wtp_autolayout/geometry/engine.py`, `routing.py`; `wtp_autolayout/models/common.py`, `coordinate.py`, `placement.py`; `wtp_autolayout/parsers/boundary_ordering.py`, `validation.py`; `wtp_autolayout/optimization/annealing.py`; `wtp_autolayout/scoring/engine.py`.

Added: `tests/test_stabilization.py`; `scripts/synthetic_projects.py`, `stress_profile.py`, `ui_smoke.py`, `verify_demo.py`; `sample_data/demo_presets.json`; `DEMO_CHECKLIST.md`; `STABILIZATION_REPORT.md`.
