import json
import tempfile
import unittest
from pathlib import Path

import rewards_earn


class MonthlyStateTests(unittest.TestCase):
    def test_daily_monthly_search_requires_24_hours(self):
        self.assertTrue(rewards_earn.is_monthly_daily_search(
            "Bing has your Halloween answers Search on your desktop for 5 out of 10 days."
        ))
        self.assertEqual(rewards_earn.parse_monthly_daily_progress("(1/5 days complete)"), (1, 5))

    def test_daily_monthly_search_progress_must_advance(self):
        self.assertTrue(rewards_earn.monthly_daily_progress_advanced("(1/5 days complete)", "(2/5 days complete)"))
        self.assertFalse(rewards_earn.monthly_daily_progress_advanced("(1/5 days complete)", "(1/5 days complete)"))

    def test_recognizes_current_six_task_punchcard(self):
        href = "https://rewards.bing.com/earn/quest/WW_pcparent_HalloweenQuestROWOct26_punchcard"
        self.assertTrue(rewards_earn.is_monthly_strategy("50/100 0/6 个任务", href))

    def test_monthly_state_keeps_fixed_four_week_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_path = rewards_earn._monthly_state_path
            try:
                rewards_earn._monthly_state_path = lambda: str(Path(temp_dir) / "monthly_state.json")
                rewards_earn._write_monthly_state(1, weekly_scanned=2, weekly_locked=1)
                state = json.loads((Path(temp_dir) / "monthly_state.json").read_text(encoding="utf-8"))
            finally:
                rewards_earn._monthly_state_path = old_path

        self.assertEqual(state["weekly_done"], 1)
        self.assertEqual(state["weekly_total"], 4)
        self.assertEqual(state["weekly_scanned"], 2)
        self.assertEqual(state["weekly_locked"], 1)


if __name__ == "__main__":
    unittest.main()
