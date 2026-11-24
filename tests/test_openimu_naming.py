"""Offline persistent-name safeguards; no hardware or root access."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from install_openimu_name import naming_rule, validate_target


class NamingTests(unittest.TestCase):
    def test_rule_is_hardware_and_port_scoped(self):
        rule = naming_rule(dict(usb_port="1-2.3"))
        for required in ('ATTR{type}=="280"', 'ATTRS{idVendor}=="0c72"',
                         'ATTRS{idProduct}=="0012"', 'KERNELS=="1-2.3"', 'NAME:="spriteimu0"'):
            self.assertIn(required, rule)
        self.assertNotIn('DRIVERS=="kcan"', rule)
        self.assertNotIn('RUN', rule)

    def test_reject_rule_injection(self):
        for port in ['*', '1-2.3"', '', '../net']:
            with self.assertRaises(ValueError):
                naming_rule(dict(usb_port=port))

    def test_refuse_live_rename_and_collision(self):
        for old in ('kcan5', 'can3'):
            adapter = dict(interface=old)
            with self.assertRaises(RuntimeError):
                validate_target(adapter, dict(flags=['UP']), False)
            with self.assertRaises(RuntimeError):
                validate_target(adapter, dict(flags=[]), True)
            validate_target(adapter, dict(flags=[]), False)

    def test_existing_stable_name_is_idempotent(self):
        validate_target(dict(interface='spriteimu0'), dict(flags=['UP']), True)


if __name__ == '__main__':
    unittest.main()
