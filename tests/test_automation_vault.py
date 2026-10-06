import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from testplayer.automation_vault import AutomationVault


class AutomationVaultTests(unittest.TestCase):
    def test_defaults_and_secret_values_never_return_in_listing(self):
        vault = AutomationVault()
        vault.save('PLAYWRIGHT_EMAIL', 'qa@example.test', False)
        vault.save('PLAYWRIGHT_PASSWORD', 'canary-password', True)
        public = vault.entries()
        password = next(entry for entry in public if entry['key'] == 'PLAYWRIGHT_PASSWORD')
        self.assertNotIn('value', password)
        self.assertTrue(password['has_value'])
        self.assertNotIn('canary-password', str(public))
        self.assertEqual(vault.environment()['PLAYWRIGHT_PASSWORD'], 'canary-password')

    def test_arbitrary_keys_are_usable_but_cannot_override_node_runtime(self):
        vault = AutomationVault()
        vault.save('API_TOKEN', 'abc', True)
        self.assertEqual(vault.environment()['API_TOKEN'], 'abc')
        for key in ('NODE_OPTIONS', 'RECORDER_PORT', 'PATH', '__proto__', 'wrong key'):
            with self.assertRaises(ValueError):
                vault.save(key, 'bad', True)

    def test_secret_can_be_kept_and_is_erased_at_shutdown(self):
        vault = AutomationVault()
        vault.save('PLAYWRIGHT_PASSWORD', 'secret', True)
        vault.save('PLAYWRIGHT_PASSWORD', None, True)
        self.assertEqual(vault.environment()['PLAYWRIGHT_PASSWORD'], 'secret')
        vault.clear()
        self.assertFalse(any(vault.environment().values()))
