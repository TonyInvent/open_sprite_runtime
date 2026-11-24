"""Numeric regression checks for offline comparison; no hardware access."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from analyze_dual_openimu_spi import body, integral_summary, tilt


class ComparisonTests(unittest.TestCase):
    def test_body_mount(self):
        np.testing.assert_equal(body(np.array([[1., 2., 3.]])), [[-3., -2., -1.]])

    def test_return_motion_is_not_hidden_by_net_zero(self):
        result = integral_summary(np.array([0., 1., 2., 3., 4.]), np.array([0., 1., 0., -1., 0.]))
        self.assertAlmostEqual(result["net_deg"], 0.)
        self.assertAlmostEqual(result["positive_deg"], np.rad2deg(1.))
        self.assertAlmostEqual(result["negative_deg"], -np.rad2deg(1.))
        self.assertAlmostEqual(result["excursion_deg"], np.rad2deg(1.))

    def test_actual_time_intervals(self):
        result = integral_summary(np.array([0., .01, .03]), np.array([2., 2., 2.]))
        self.assertAlmostEqual(result["net_deg"], np.rad2deg(.06))

    def test_static_tilt(self):
        result = tilt(np.array([[0., 0., 9.80665]]))
        self.assertEqual(result["roll_deg"], 0.)
        self.assertEqual(result["pitch_deg"], 0.)


if __name__ == "__main__":
    unittest.main()
