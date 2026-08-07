import math
import random
import unittest

from _tree_scene_layout import place_double_tree_pairs, select_large_spruce_indices


class TreeSceneLayoutTests(unittest.TestCase):
    def test_double_tree_pairs_preserve_other_clearances(self):
        original = [(x * 3.0, z * 3.0) for z in range(3) for x in range(4)]
        positions, pairs = place_double_tree_pairs(
            original,
            pair_count=2,
            candidate_count=8,
            distance_min=0.25,
            distance_max=0.45,
            minimum_distance=1.0,
            extent=10.0,
            scene_kind="dense_park",
            buildings=(),
            random_source=random.Random(42),
        )

        paired_edges = {frozenset(tree_id - 1 for tree_id in pair["tree_ids"]) for pair in pairs}
        self.assertEqual(len(pairs), 2)
        self.assertEqual(len(set().union(*paired_edges)), 4)
        for pair in pairs:
            first, second = (tree_id - 1 for tree_id in pair["tree_ids"])
            self.assertAlmostEqual(math.dist(positions[first], positions[second]), pair["distance"])
            self.assertGreaterEqual(pair["distance"], 0.25)
            self.assertLessEqual(pair["distance"], 0.45)
        for first in range(len(positions)):
            for second in range(first + 1, len(positions)):
                if frozenset((first, second)) not in paired_edges:
                    self.assertGreaterEqual(math.dist(positions[first], positions[second]), 1.0)

    def test_large_spruces_do_not_overlap_double_tree_members(self):
        pairs = [
            {"pair_id": 1, "tree_ids": [1, 3], "distance": 0.3},
            {"pair_id": 2, "tree_ids": [2, 5], "distance": 0.4},
        ]
        indices = select_large_spruce_indices(8, pairs, 3, random.Random(42))

        self.assertEqual(len(indices), 3)
        self.assertTrue(indices.isdisjoint({0, 1, 2, 4}))


if __name__ == "__main__":
    unittest.main()
