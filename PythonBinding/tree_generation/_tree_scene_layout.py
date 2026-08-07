import math


def select_large_spruce_indices(big_tree_count, double_tree_pairs, count, random_source):
    double_tree_members = {
        tree_id - 1 for pair in double_tree_pairs for tree_id in pair["tree_ids"]
    }
    available = [index for index in range(big_tree_count) if index not in double_tree_members]
    return set(random_source.sample(available, count))


def place_double_tree_pairs(
    positions,
    pair_count,
    candidate_count,
    distance_min,
    distance_max,
    minimum_distance,
    extent,
    scene_kind,
    buildings,
    random_source,
):
    positions = list(positions)
    members = random_source.sample(range(candidate_count), pair_count * 2)
    pairs = []
    for pair_index in range(pair_count):
        anchor_index, partner_index = members[pair_index * 2 : pair_index * 2 + 2]
        anchor_x, anchor_z = positions[anchor_index]
        for _ in range(10_000):
            distance = random_source.uniform(distance_min, distance_max)
            angle = random_source.uniform(0.0, math.tau)
            candidate = (anchor_x + math.cos(angle) * distance, anchor_z + math.sin(angle) * distance)
            if scene_kind == "alley":
                inside_scene = -5.7 <= candidate[0] <= 5.7 and 1.6 <= abs(candidate[1]) <= 2.9
            else:
                inside_scene = abs(candidate[0]) <= extent and abs(candidate[1]) <= extent
            outside_buildings = all(
                abs(candidate[0] - x) > width * 0.5 + 0.2
                or abs(candidate[1] - z) > depth * 0.5 + 0.2
                for _, _, x, z, width, _, depth in buildings
            )
            clear_of_other_trees = all(
                index in (anchor_index, partner_index)
                or (candidate[0] - x) ** 2 + (candidate[1] - z) ** 2 >= minimum_distance**2
                for index, (x, z) in enumerate(positions)
            )
            if inside_scene and outside_buildings and clear_of_other_trees:
                positions[partner_index] = candidate
                pairs.append(
                    {
                        "pair_id": pair_index + 1,
                        "tree_ids": [anchor_index + 1, partner_index + 1],
                        "distance": distance,
                    }
                )
                break
        else:
            raise RuntimeError(f"Could not place double-tree pair {pair_index + 1}.")
    return positions, pairs
