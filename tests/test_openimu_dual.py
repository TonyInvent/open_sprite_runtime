"""Offline checks for the no-display dual-IMU diagnostic."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from dual_openimu_spi import PHASES, producer_commands


class DualImuTests(unittest.TestCase):
    def test_guided_axes_and_bounded_duration(self):
        self.assertEqual([p[0] for p in PHASES],
                         ["still", "pitch", "rest_pitch", "roll", "rest_roll", "yaw", "final_still"])
        self.assertEqual(sum(p[1] for p in PHASES), 56)
        self.assertLess(25 + sum(p[1] for p in PHASES) + 15, 180)

    def test_only_sensor_producers(self):
        commands = producer_commands(Path("/baseline/sprite_icm45686"), Path("/addon/sprite_openimu"),
                                     "kcan5", "gpiochip0", "123", Path("/reports/test"))
        self.assertEqual(commands["openimu"], ["/addon/sprite_openimu", "capture-canfd", "kcan5",
                                              "180", "/reports/test/openimu.csv"])
        self.assertEqual(commands["spi"], ["/baseline/sprite_icm45686", "capture", "/dev/spidev0.0",
                                          "/dev/gpiochip0", "123", "800", "180", "/reports/test/spi.csv",
                                          "X_DOWN_Z_BACK", "CONFIGURE_ICM45686_RAW_NO_CAN"])


if __name__ == "__main__":
    unittest.main()
