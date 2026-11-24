"""Offline selector and dedicated-adapter tests; no CAN/SPI access."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from openimu_interface import find_openimu, require_active
from xbox_imu_session import ACK, CLIENT800, arguments, legacy_command, admission_directory, no_running_runtime


class SelectorTests(unittest.TestCase):
    def test_default_openimu(self):
        args = arguments(["--check"])
        self.assertEqual(args.imu, "openimu")
        self.assertEqual(args.action, "--check")
        self.assertEqual(args.snapshot_client_hz, 200)

    def test_both_800_backends_use_same_candidate(self):
        for backend in ("openimu", "icm-spi"):
            args = arguments([ACK, "--imu", backend, "--snapshot-client-hz", "800"])
            self.assertEqual(admission_directory(args), CLIENT800)
            if backend == "icm-spi":
                self.assertEqual(Path(legacy_command(args)[1]).parent, CLIENT800)

    def test_client800_does_not_claim_viewer_changes(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                arguments(["--imu-only", "--snapshot-client-hz", "800"])

    def test_powered_is_explicit(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for bad in [[], [ACK, "--check"], ["--imu-only", "--preflight-only"],
                        ["--check", "--imu", "unknown"], [ACK, "--duration", "40"]]:
                with self.assertRaises(SystemExit):
                    arguments(bad)

    def test_spi_delegates_unchanged_entry(self):
        args = arguments([ACK, "--imu", "icm-spi"])
        self.assertEqual(legacy_command(args), ["bash", "/home/tony/open_sprite_runtime/"
                         "run_sprite0825_xbox_native_turn120_on_253.sh", ACK])

    def test_zero_gain_and_read_only_are_distinct(self):
        self.assertEqual(arguments(["--preflight-only"]).action, "--preflight-only")
        self.assertEqual(arguments(["--imu-only", "--duration", "120"]).duration, 120)

    def test_viewer_never_enables_motor_path(self):
        self.assertTrue(arguments(["--imu-only", "--view"]).view)
        with contextlib.redirect_stderr(io.StringIO()):
            for bad in [[ACK, "--view"], ["--preflight-only", "--view"],
                        ["--check", "--view"], ["--imu-only", "--view", "--imu", "icm-spi"]]:
                with self.assertRaises(SystemExit):
                    arguments(bad)

    def test_spi_rejects_openimu_options(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for extra in [["--imu-only"], ["--check", "--imu-can-interface", "kcan5"]]:
                with self.assertRaises(SystemExit):
                    arguments(["--imu", "icm-spi", *extra])

    def test_refuse_active_native_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe = root / "sprite_can_xbox120"
            exe.touch()
            pid = root / "999999"
            pid.mkdir()
            (pid / "exe").symlink_to(exe)
            with self.assertRaisesRegex(RuntimeError, "existing runtime"):
                no_running_runtime(root)


class InterfaceTests(unittest.TestCase):
    def test_motor_buses_rejected_before_discovery(self):
        for name in ("kcan1", "kcan2", "kcan3", "kcan4"):
            with self.assertRaisesRegex(ValueError, "never a motor bus"):
                find_openimu(name, Path("/does/not/exist"))

    def test_link_validation(self):
        good = dict(flags=["UP"], mtu=72, linkinfo=dict(info_data=dict(
            bittiming=dict(bitrate=1000000), data_bittiming=dict(bitrate=5000000), state="ERROR-ACTIVE")))
        require_active(good)
        for field, value in [("mtu", 16), ("flags", [])]:
            bad = dict(good, **{field: value})
            with self.assertRaises(ValueError):
                require_active(bad)
        for field, value in [("state", "BUS-OFF"), ("bittiming", {"bitrate": 500000}),
                             ("data_bittiming", {"bitrate": 1000000})]:
            bad = json.loads(json.dumps(good))
            bad["linkinfo"]["info_data"][field] = value
            with self.assertRaises(ValueError):
                require_active(bad)

    def test_dedicated_pcan_discovery_and_ambiguity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            net = root / "net"
            net.mkdir()
            for name, vendor, product in [("kcan1", "395e", "0020"), ("kcan5", "0c72", "0012")]:
                usb = root / (name + "-usb")
                device = usb / "interface"
                device.mkdir(parents=True)
                (usb / "idVendor").write_text(vendor)
                (usb / "idProduct").write_text(product)
                entry = net / name
                entry.mkdir()
                (entry / "type").write_text("280")
                (entry / "device").symlink_to(device, target_is_directory=True)
            self.assertEqual(find_openimu(net=net)["interface"], "kcan5")
            self.assertEqual(find_openimu("kcan5", net)["backend"], "canfd")
            with self.assertRaises(ValueError):
                find_openimu("can0", net)
            entry = net / "kcan6"
            entry.mkdir()
            (entry / "type").write_text("280")
            (entry / "device").symlink_to(root / "kcan5-usb/interface", target_is_directory=True)
            with self.assertRaises(ValueError):
                find_openimu(net=net)


if __name__ == "__main__":
    unittest.main()
