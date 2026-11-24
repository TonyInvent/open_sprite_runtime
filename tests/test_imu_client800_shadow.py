"""No-hardware checks for the exclusive-backend zero-gain qualification runner."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import run_imu_client800_shadow as runner


class ShadowTests(unittest.TestCase):
    def test_can_command_has_no_actuation_path(self):
        command = runner.can_command(Path("/tmp/test"), Path("/tmp/state.sock"), 123, 120)
        self.assertIn("ZERO_GAIN_NATIVE_SHADOW", command)
        self.assertIn("--all-motors-disabled-confirmed", command)
        self.assertNotIn("--policy-actuation", command)
        self.assertNotIn("--measured-pose-hold", command)
        self.assertNotIn("--extended-policy-actuation-acknowledgement", command)

    def test_exclusive_producer_commands(self):
        can = runner.producer_command("openimu", 150, Path("/tmp/imu.csv"), "spriteimu0")
        spi = runner.producer_command("icm-spi", 150, Path("/tmp/imu.csv"), gpio=["gpiochip0", "123"])
        self.assertIn("capture-canfd", can)
        self.assertNotIn("/dev/spidev0.0", can)
        self.assertIn("/dev/spidev0.0", spi)
        self.assertNotIn("capture-canfd", spi)
        for name in (None, "kcan1", "kcan2", "kcan3", "kcan4"):
            with self.assertRaises(ValueError):
                runner.producer_command("openimu", 150, Path("/tmp/imu.csv"), name)

    def test_fixture_preserves_header_not_recorded_sensors(self):
        original = b"SPCHN001" + struct.pack("<I", 2) + b"parameters" + bytes([7]) * (2 * 72 * 8)
        header, data = runner.fixture(original, 500)
        self.assertEqual(header[12:], b"parameters")
        self.assertEqual(struct.unpack_from("<I", header, 8)[0], 500)
        self.assertEqual(data[len(header):], bytes(500 * 72 * 8))
        with self.assertRaises(ValueError):
            runner.fixture(original, 6001)

    def test_openimu_clock_wrap_and_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "imu.csv"
            heading = "kernel_rx_ns,read_ns,estimated_sample_ns,sensor_tick_us\n"
            path.write_text(heading + "1000000000,1000100000,1000000000,65000\n"
                            "1001250000,1001350000,1001250000,714\n")
            result = runner.openimu_report(path, .00125)
            self.assertTrue(result["completed"])
            self.assertEqual(result["sensor_delta_median_us"], 1250)
            self.assertFalse(runner.openimu_report(path, 150)["completed"])
            path.write_text(heading + "1000000000,1000100000,1000000000,65000\n"
                            "1001250000,1001350000,1001250000,65000\n")
            self.assertFalse(runner.openimu_report(path, .00125)["completed"])


if __name__ == "__main__":
    unittest.main()
