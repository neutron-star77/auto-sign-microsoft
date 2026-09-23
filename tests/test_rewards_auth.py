import json
import tempfile
import unittest
from pathlib import Path

import rewards_earn


class RewardsAuthTests(unittest.TestCase):
    def test_auth_wall_urls_are_detected(self):
        self.assertTrue(
            rewards_earn._is_auth_wall_url(
                "https://account.live.com/tou/accrue?mkt=EN-US"
            )
        )
        self.assertTrue(rewards_earn._is_auth_wall_url("https://login.live.com/"))
        self.assertFalse(rewards_earn._is_auth_wall_url("https://rewards.bing.com/earn"))
        self.assertEqual(
            rewards_earn._auth_error("https://account.live.com/tou/accrue").code,
            "TOU_REQUIRED",
        )

    def test_display_url_does_not_expose_query_parameters(self):
        self.assertEqual(
            rewards_earn._display_url(
                "https://account.live.com/tou/accrue?ru=https%3A%2F%2Frewards.bing.com"
            ),
            "https://account.live.com/tou/accrue",
        )

    def test_storage_state_is_structurally_validated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "storage_state.json"
            path.write_text(
                json.dumps({"cookies": [], "origins": []}), encoding="utf-8"
            )
            state = rewards_earn._read_storage_state(path)
            self.assertEqual(state["cookies"], [])
            self.assertEqual(state["origins"], [])

            path.write_text(json.dumps({"cookies": {}}), encoding="utf-8")
            with self.assertRaises(rewards_earn.StorageStateError):
                rewards_earn._read_storage_state(path)


class RewardsAuthAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_rescan_does_not_turn_auth_redirect_into_success(self):
        class AuthRedirectPage:
            url = "https://rewards.bing.com/earn"

            async def goto(self, *_args, **_kwargs):
                self.url = "https://account.live.com/tou/accrue"

            async def wait_for_timeout(self, *_args, **_kwargs):
                return None

        with self.assertRaises(rewards_earn.AuthenticationRequired) as caught:
            await rewards_earn._scan_unfinished(AuthRedirectPage())
        self.assertTrue(str(caught.exception).startswith("TOU_REQUIRED:"))


if __name__ == "__main__":
    unittest.main()
