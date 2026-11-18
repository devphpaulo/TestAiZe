import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from testplayer.bugs_store import BugsStore
from testplayer.bugs_coordinator import coordinated, RecoveryPending
from testplayer.bugs_store import MigrationError


class BugsStoreTests(unittest.TestCase):
    def test_failed_migration_rolls_back_and_can_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = BugsStore(Path(temporary))
            with patch('testplayer.bugs_store.SCHEMA', ('CREATE TABLE incomplete(id)', 'INVALID SQL')):
                with self.assertRaises(MigrationError):
                    store.initialize()
            with store.connect() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='incomplete'").fetchone())
            store.initialize()
            # The migration and every connection release their handles on failure.
            store.path.rename(store.path.with_suffix('.moved'))

    def test_repeated_initialization_and_unknown_recovery_block_mutations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = BugsStore(root)
            store.initialize()
            store.initialize()
            with store.connect() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
                db.execute("INSERT INTO bug_operations VALUES ('op','unknown','{}','intent','now','now')")
            with self.assertRaises(RecoveryPending):
                with coordinated(root):
                    self.fail('must not accept a mutation without recovery')
