"""Self-check of the bundle (standard library only):  cd python && python3 -m unittest discover tests"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from thc import Library, move_time, play, trajectories, units  # noqa: E402


class BundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = Library.load()

    def test_every_character_and_move_stays_in_limits(self):
        lib, n = self.lib, 0
        for c in lib.characters:
            for m in lib.moves:
                steps = lib.plan(c, m)
                self.assertTrue(steps[-1].wait_arrival)
                prev = -1.0
                for s in steps:
                    self.assertGreaterEqual(s.t, prev - 1e-9); prev = s.t
                    for j, v in s.goals.items():
                        self.assertLessEqual(abs(v - 0.5), lib.max_dev[j] + 1e-9, (c, m, j))
                        self.assertLessEqual(s.acc[j], lib.acc_cap[j])
                        self.assertLessEqual(s.speed[j], lib.speed_cap[j]); n += 1
        self.assertGreater(n, 10000)

    def test_keyframe_markers_for_props(self):
        for c in self.lib.characters:
            for scene, spec in self.lib.props.items():
                keys = sorted(s.key for s in self.lib.plan(c, scene) if s.key >= 0)
                need = max(v for k, v in spec.items() if k != "type")
                self.assertIn(need, keys, (c, scene))

    def test_custom_keyframes_and_neutral(self):
        neutral = {j: 0.4 for j in self.lib.joints}
        steps = self.lib.plan("curious", [[1, {"j6": 1.5}], [1, {"j6": 0}]], neutral=neutral)
        self.assertTrue(all(abs(v - 0.4) <= self.lib.max_dev[j] + 1e-9 for s in steps for j, v in s.goals.items()))

    def test_player_calls_send_in_order(self):
        sent, clock = [], [0.0]
        play(self.lib.plan("butler", "yes"), lambda g, a, s: sent.append((clock[0], g)),
             sleep=lambda d: clock.__setitem__(0, clock[0] + d), clock=lambda: clock[0])
        self.assertGreater(len(sent), 3)
        self.assertEqual([t for t, _ in sent], sorted(t for t, _ in sent))

    def test_units_and_move_time(self):
        self.assertAlmostEqual(units.acc_to_rad_s2(100), 100 * 100 * 2 * 3.141592653589793 / 4096)
        self.assertGreater(move_time(0.1, 20, 600), move_time(0.1, 150, 600))

    def test_trajectories(self):
        clips = trajectories.load()
        self.assertEqual(len(clips), len(self.lib.characters) * (len(self.lib.moves) + 1))   # + idle
        t, q = next(trajectories.frames("smooth/air_kiss"))
        self.assertEqual(sorted(q), self.lib.joints)


if __name__ == "__main__":
    unittest.main()
