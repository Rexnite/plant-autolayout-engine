"""Deterministic software stress fixtures, not engineering-valid plant designs."""

import math
import random


def synthetic_project(unit_count, seed=42):
    if unit_count < 2:
        raise ValueError("unit_count must be at least 2")
    rng = random.Random(seed)
    side = max(180.0, math.sqrt(unit_count) * 58.0)

    def rectangle(x0, y0, x1, y1):
        return [{"easting": x, "northing": y} for x, y in
                ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]

    groups = ("hydraulic", "sludge", "chemical", "support")
    units = []
    for index in range(unit_count):
        group = groups[index % len(groups)]
        is_circle = index % 5 == 0
        unit = {"unit_id": "U-%03d" % index, "name": "%s unit %s" % (group, index),
                "category": {"hydraulic": "process", "sludge": "sludge",
                             "chemical": "chemical", "support": "utility"}[group],
                "shape_type": "circle" if is_circle else "rectangle",
                "required_clearance": 1.0, "system_group": group,
                "process_order": index + 1,
                "access_required": group == "chemical",
                "max_access_distance": side,
                "access_classification": "soft"}
        if is_circle:
            unit["diameter"] = rng.uniform(6.0, 10.0)
        else:
            unit["width"] = rng.uniform(6.0, 10.0)
            unit["length"] = rng.uniform(6.0, 10.0)
        units.append(unit)

    flows = [{"edge_id": "F-%03d" % index,
              "source_unit_id": units[index]["unit_id"],
              "target_unit_id": units[index + 1]["unit_id"],
              "flow_type": "process_water"}
             for index in range(min(unit_count - 1, max(4, unit_count // 2)))]
    return {
        "layout_id": "synthetic_%s_seed_%s" % (unit_count, seed),
        "plant_type": "petrochemical",
        "metadata": {"synthetic_stress_fixture": True, "seed": seed,
                     "warning": "Software stress input only; not an engineering design"},
        "boundary": rectangle(0, 0, side, side),
        "system_groups": [{"group_id": group, "name": group.title()} for group in groups],
        "units": units,
        "flow_edges": flows,
        "proximity_relationships": [
            {"relationship_id": "P-1", "unit_id_a": "U-000", "unit_id_b": "U-001",
             "relationship_type": "preferred_near", "distance": 35,
             "classification": "soft"}],
        "group_relationships": [
            {"relationship_id": "G-1", "group_id_a": "sludge", "group_id_b": "support",
             "relationship_type": "min_distance", "distance": 10,
             "classification": "soft"}],
        "site_zones": [
            {"zone_id": "excluded", "name": "Synthetic exclusion", "zone_type": "exclusion",
             "classification": "hard", "vertices": rectangle(side * .02, side * .75,
                                                              side * .12, side * .90)},
            {"zone_id": "expansion", "name": "Synthetic expansion", "zone_type": "expansion",
             "classification": "soft", "vertices": rectangle(side * .80, side * .80,
                                                              side * .95, side * .95)}],
        "existing_structures": [
            {"structure_id": "fixed", "name": "Synthetic fixed structure",
             "vertices": rectangle(side * .02, side * .02, side * .10, side * .10)}],
        "corridors": [
            {"corridor_id": "access", "name": "Synthetic access", "corridor_type": "access",
             "width": 5, "classification": "soft",
             "path": [{"easting": side * .15, "northing": side * .10},
                      {"easting": side * .85, "northing": side * .10}]},
            {"corridor_id": "routing", "name": "Synthetic routing", "corridor_type": "routing",
             "width": 4, "classification": "soft",
             "path": [{"easting": side * .20, "northing": side * .50},
                      {"easting": side * .80, "northing": side * .50}]}],
    }
