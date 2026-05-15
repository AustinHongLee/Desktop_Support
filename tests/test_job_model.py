from __future__ import annotations

import unittest
from datetime import datetime

from launcher.core.job_model import JobEvent, JobResult


class JobModelTests(unittest.TestCase):
    def test_timeout_and_cancelled_results_are_not_ok_even_with_zero_code(self) -> None:
        now = datetime.now()

        for event_type in ("timeout", "cancelled"):
            result = JobResult(
                action_id="test",
                return_code=0,
                started_at=now,
                finished_at=now,
                events=(JobEvent(event_type),),
            )
            self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
