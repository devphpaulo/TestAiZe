import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from testplayer.automation_recorder import RecorderError, RecorderManager
from testplayer.automation_environment import AutomationRuntime


class RecorderManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "server.js").write_text("", encoding="utf-8")
        self.manager = RecorderManager(self.root, runtime=AutomationRuntime(True, sys.executable, 'C:/tools/playwright/test.js'), start_timeout=0.15, idle_timeout=0.1)
        self.addCleanup(self.manager.shutdown)

    def worker(self, output="PLAYWRIGHT_RECORDER_READY http://127.0.0.1:51234\n"):
        worker = Mock()
        worker.stdout = io.StringIO(output)
        worker.stdin = io.StringIO()
        worker.poll.return_value = None
        worker.pid = 12345
        return worker

    def test_idle_and_missing_runtime_do_not_spawn(self):
        self.assertEqual(self.manager.status(), {"state": "idle"})
        self.manager.runtime = AutomationRuntime(message='Node.js não encontrado.')
        with patch("testplayer.automation_recorder.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(RecorderError, "Node"):
                self.manager.start("http://127.0.0.1:5000", "a")
            spawn.assert_not_called()

    def test_start_is_idempotent_and_shutdown_is_graceful(self):
        worker = self.worker()
        with patch("testplayer.automation_recorder.subprocess.Popen", return_value=worker) as spawn, patch.object(self.manager, "_healthy", return_value=True):
            first = self.manager.start("http://127.0.0.1:5000", "a")
            self.assertEqual(first, self.manager.start("http://127.0.0.1:5000", "a"))
            self.assertEqual(first["state"], "ready")
            self.assertEqual(spawn.call_count, 1)
            self.assertFalse(spawn.call_args.kwargs.get("shell", False))
            self.manager.stop("old-page")
            worker.wait.assert_not_called()
            worker.stdin = Mock()
            self.manager.stop("a")
            worker.stdin.write.assert_called_with("shutdown\n")
            self.assertEqual(self.manager.stop(), {"state": "idle"})

    def test_invalid_readiness_or_timeout_cleans_partial_process(self):
        for output in ("", "PLAYWRIGHT_RECORDER_READY http://example.test:80\n"):
            worker = self.worker(output)
            with patch("testplayer.automation_recorder.subprocess.Popen", return_value=worker):
                with self.assertRaises(RecorderError):
                    self.manager.start("http://127.0.0.1:5000", "a")
                self.assertEqual(self.manager.status(), {"state": "idle"})
                worker.wait.assert_called()

    def test_dead_worker_and_expired_owner_are_cleaned(self):
        worker = self.worker()
        with patch("testplayer.automation_recorder.subprocess.Popen", return_value=worker), patch.object(self.manager, "_healthy", return_value=True):
            self.manager.start("http://127.0.0.1:5000", "a")
            self.manager._last_seen -= 1
            self.manager.reap_idle()
            self.assertEqual(self.manager.status(), {"state": "idle"})
            worker.wait.assert_called()

    def test_exited_worker_cannot_report_ready(self):
        worker = self.worker()
        with patch("testplayer.automation_recorder.subprocess.Popen", return_value=worker), patch.object(self.manager, "_healthy", return_value=True):
            self.manager.start("http://localhost:5000", "a")
            worker.poll.return_value = 1
            self.assertEqual(self.manager.status("a"), {"state": "idle"})

    def test_readiness_timeout_stops_and_reaps_process(self):
        from queue import Empty
        worker = self.worker()
        with patch("testplayer.automation_recorder.subprocess.Popen", return_value=worker), patch("testplayer.automation_recorder.queue.Queue") as queue:
            queue.return_value.get.side_effect = Empty
            with self.assertRaisesRegex(RecorderError, "demorou"):
                self.manager.start("http://localhost:5000", "a")
            worker.wait.assert_called()
            self.assertEqual(self.manager.status(), {"state": "idle"})
