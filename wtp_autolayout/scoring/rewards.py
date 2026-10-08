"""Default reward weights for multi-objective engineering scoring."""

DEFAULT_OBJECTIVE_WEIGHTS = {
    "pipe_efficiency": 9.0,
    "gravity": 5.0,
    "cluster": 4.0,
    "group_arrangement": 5.0,
    "proximity": 5.0,
    "flow_crossing": 3.0,
    "compactness": 2.0,
    "expansion": 2.0,
}


MAX_ENGINEERING_REWARD = 35.0
ENGINEERING_BASE_SCORE = 65.0
