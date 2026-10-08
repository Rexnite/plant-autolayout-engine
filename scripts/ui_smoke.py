"""Exercise the Streamlit demo workflow with its bundled AppTest harness."""

import logging
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
STAGES = ("Project Setup", "Site Boundary", "Site Features", "System Groups", "Units",
          "Flow", "Proximity", "Corridors / Roads", "Optimization Settings")


def check(app, label):
    if app.exception or app.error:
        raise AssertionError("%s: %s %s" % (
            label, [item.message for item in app.exception], [item.value for item in app.error]))


def click(app, label):
    for button in app.button:
        if button.label == label:
            button.click().run()
            return
    raise AssertionError("Button not found: %s" % label)


def main():
    logging.disable(logging.WARNING)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    check(app, "launch")
    for stage in STAGES:
        app.radio[0].set_value(stage).run()
        check(app, stage)
    click(app, "Run AutoLayout")
    check(app, "first result")
    if app.radio[0].value != "Results" or len(app.metric) < 9:
        raise AssertionError("Results summary is missing")
    first_score = app.session_state.run_result.optimization_result.best_score_result.score
    click(app, "Save current run as scenario")
    check(app, "first scenario")
    app.radio[0].set_value("Optimization Settings").run()
    app.number_input[0].set_value(43).run()
    click(app, "Run AutoLayout")
    check(app, "second result")
    app.text_input[0].set_value("Scenario 2").run()
    click(app, "Save current run as scenario")
    check(app, "second scenario")
    if len(app.session_state.saved_scenarios) != 2:
        raise AssertionError("Two distinct scenarios were not saved")
    app.multiselect[0].set_value(["Scenario 1", "Scenario 2"]).run()
    check(app, "comparison")
    print("Streamlit stages, two runs, result metrics, scenario saving and comparison: PASS. "
          "First score %.2f." % first_score)


if __name__ == "__main__":
    main()
