from __future__ import annotations

import os
import unittest
from datetime import timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QFrame, QTabWidget  # noqa: E402

from launcher.core.job_model import JobEvent, JobResult  # noqa: E402
from launcher.ui.job_monitor import JobMonitor  # noqa: E402


class JobMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_job_monitor_uses_status_hero_and_tab_counts(self) -> None:
        monitor = JobMonitor("PDF 拆頁")

        hero = monitor.findChild(QFrame, "JobHero")
        tabs = monitor.findChild(QTabWidget, "JobTabs")

        self.assertIsNotNone(hero)
        self.assertIsNotNone(tabs)
        assert tabs is not None
        monitor.append_event(JobEvent(type="message", message="開始處理"))
        monitor.append_event(JobEvent(type="artifact", message="輸出檔案", data={"path": "out.pdf"}))
        monitor.append_event(JobEvent(type="error", message="失敗"))

        self.assertEqual(tabs.tabText(0), "全部 3")
        self.assertEqual(tabs.tabText(1), "錯誤 1")
        self.assertEqual(tabs.tabText(2), "產出 1")
        self.assertEqual(tabs.currentIndex(), 1)
        self.assertEqual(monitor._status.text(), "已有錯誤")

    def test_progress_event_updates_progress_bar(self) -> None:
        monitor = JobMonitor("批次處理")

        monitor.append_event(JobEvent(type="progress", message="第 3 頁 / 10 頁", data={"current": 3, "total": 10}))

        self.assertEqual(monitor._progress.maximum(), 10)
        self.assertEqual(monitor._progress.value(), 3)
        self.assertEqual(monitor._progress.format(), "3 / 10")
        self.assertEqual(monitor._substatus.text(), "第 3 頁 / 10 頁")

    def test_finish_updates_final_state(self) -> None:
        monitor = JobMonitor("批次處理")
        finished_at = monitor._started_at + timedelta(seconds=3)
        result = JobResult(
            action_id="test.action",
            return_code=0,
            started_at=monitor._started_at,
            finished_at=finished_at,
            events=(),
        )

        monitor.finish(result)

        self.assertEqual(monitor._status.text(), "完成")
        self.assertFalse(monitor._cancel_button.isEnabled())
        self.assertEqual(monitor._progress.value(), 100)
        self.assertIn("完成", monitor._substatus.text())


if __name__ == "__main__":
    unittest.main()
