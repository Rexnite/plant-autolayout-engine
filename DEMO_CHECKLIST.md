# Plant AutoLayout Demonstration Checklist

This is a preliminary layout study, not a construction or regulatory design. Use the fixed presets in `sample_data/demo_presets.json`; do not change their seed or settings during the live run.

## Before the meeting

1. From the project root, launch `streamlit run app.py` and open the local URL it prints. If `streamlit` is not on PATH, use the configured Python environment: `python -m streamlit run app.py`.
2. Run `python -m scripts.verify_demo` once. Confirm three identical WTP engineering fingerprints and a successful petrochemical export.
3. Keep `sample_data/sample_general_wtp_input.json` and `sample_data/sample_petrochemical_input.json` available. Confirm `outputs/` is writable.

## Live script

1. Select **Water Treatment Plant** and **Load template** in the sidebar.
2. Open **Project Setup** and explain the plant profile and project name.
3. Open **Site Boundary** and inspect the four site vertices and polygon preview.
4. Open **Site Features** and show the exclusion, existing workshop, and future expansion area.
5. Open **System Groups** and explain hydraulic, sludge, and chemical groups.
6. Open **Units** and **Flow** to show unit dimensions and process links.
7. Open **Proximity** and **Corridors / Roads** to show footprint-distance rules and access/routing paths.
8. Open **Optimization Settings**: `simulated_annealing`, balanced, 10 candidates, 100 iterations, seed 42. Click **Run AutoLayout**.
9. On **Results**, lead with score, hard/soft violations, proximity, crossings, access, expansion, route fallbacks, and runtime. Then explain candidate generation and annealing using the objective/penalty tables.
10. Inspect the interactive layout and the route table. Routing is a preliminary obstacle-aware display route, not detailed pipe design.
11. Save as **Scenario 1**. Return to settings, change seed to 43, rerun, save as **Scenario 2**, and select both in comparison.
12. Download PDF, PNG, JSON, and interactive HTML. Keep the two scenario output directories separate.
13. Load **Petrochemical Plant** and repeat the short run. State explicitly that petrochemical distances are illustrative user-defined inputs, not regulatory criteria.
14. Close with limitations below before discussing any real project decision.

## Expected result

- WTP preset: approximately 2-3 seconds on the validation machine; score **87.92**, **0 hard**, **0 soft**, **0 crossings**, **0 routing fallbacks**. Runtime varies; engineering outputs were identical in three runs.
- Petrochemical preset: approximately 3 seconds; score **88.21**, **0 hard**, **0 soft**, **0 crossings**, **0 routing fallbacks**.
- Scores are software-study indicators, not certifications. See `STABILIZATION_REPORT.md` for scaling limits.

## Troubleshooting

- If Streamlit is missing, install `requirements.txt` into the active Python environment, then run `python -m streamlit run app.py`.
- If the default port is busy, run `python -m streamlit run app.py --server.port 8502`.
- If the run reports no feasible placement, read its diagnostic guidance for the failed unit, site area, blockers, clearance, relationships, and access. Reduce unit size/clearance or relax user-entered hard rules after engineering review.
- If exports fail, check that `outputs/` exists or is writable. Do not rerun into a scenario folder that must be preserved.
- If the page behaves unexpectedly, refresh, reload the template, and inspect the server log. Do not conceal unresolved errors during the demonstration.

## Freeze labels

**Demo-ready:** sample parsing, site/unit inputs, constraint and score explanation, seeded candidate generation, WTP demo optimization, scenario comparison, PNG/PDF/JSON/HTML outputs.

**Experimental:** obstacle-aware routing, large-project performance, generalized petrochemical preferences.

**Known limits:** no hydraulic simulation, no CAD/DXF/BIM export, no PDF extraction, no final construction drawings, no complete infeasibility proof.

**Do not demo as final engineering:** detailed pipe routing, regulatory petrochemical clearances, hydraulic performance, or 50+ unit stress fixtures as production-ready design.
