"""Offline sensor-to-body attitude checks; no viewer, CAN, or SPI access."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
from open_sprite_runtime.imu import ImuMount, matrix_to_quaternion_wxyz, quaternion_wxyz_to_matrix
from view_openimu import body_attitude


class ViewerAttitudeTests(unittest.TestCase):
    def test_mount_and_both_rotation_directions(self):
        mount = ImuMount.sprite0825_rear_pelvis().sensor_to_body_matrix
        for axis in range(3):
            for angle in (-.7, -.1, 0, .1, .7):
                expected = np.zeros(4)
                expected[0] = np.cos(angle/2)
                expected[axis+1] = np.sin(angle/2)
                body_rotation = quaternion_wxyz_to_matrix(expected)
                sensor = matrix_to_quaternion_wxyz(body_rotation @ mount)
                observed = body_attitude(sensor)
                np.testing.assert_allclose(quaternion_wxyz_to_matrix(observed), body_rotation, atol=1e-12)

    def test_existing_tilt_not_levelled(self):
        body = np.array([.98, .1, .15, -.07])
        body /= np.linalg.norm(body)
        rotation = quaternion_wxyz_to_matrix(body)
        mount = ImuMount.sprite0825_rear_pelvis().sensor_to_body_matrix
        observed = body_attitude(matrix_to_quaternion_wxyz(rotation @ mount))
        self.assertGreater(np.linalg.norm(observed[1:]), .1)
        np.testing.assert_allclose(quaternion_wxyz_to_matrix(observed), rotation, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
