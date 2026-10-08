"""Default scoring weights for WTP constraints."""

DEFAULT_CONSTRAINT_WEIGHTS = {
    "C-001": 1.0,  # boundary containment
    "C-004": 1.0,  # geometry validity
    "C-002": 1.0,  # overlap
    "C-003": 1.0,  # clearance
    "C-009": 1.0,  # sludge isolation
    "C-010": 1.0,  # chemical safety
    "C-011": 1.0,  # residential separation
    "C-005": 1.0,  # process adjacency
    "C-006": 1.0,  # gravity flow
}

DEFAULT_HARD_CONSTRAINT_IDS = {"C-001", "C-002", "C-003", "C-004"}
