import unittest
from unittest.mock import patch

from contentstudio import login_throttle


class LoginThrottleTest(unittest.TestCase):
    def setUp(self) -> None:
        login_throttle._failures.clear()

    def tearDown(self) -> None:
        login_throttle._failures.clear()

    def test_account_limit_blocks_before_more_password_checks_and_expires(self) -> None:
        with patch.object(login_throttle.time, "monotonic", return_value=100.0):
            for _ in range(login_throttle.MAX_ACCOUNT_FAILURES):
                self.assertTrue(login_throttle.login_allowed("192.0.2.1", "a@example.test"))
                login_throttle.login_failed("192.0.2.1", "a@example.test")
            self.assertFalse(login_throttle.login_allowed("192.0.2.1", "a@example.test"))
        with patch.object(login_throttle.time, "monotonic", return_value=161.0):
            self.assertTrue(login_throttle.login_allowed("192.0.2.1", "a@example.test"))

    def test_peer_limit_bounds_many_account_names(self) -> None:
        with patch.object(login_throttle.time, "monotonic", return_value=100.0):
            for index in range(login_throttle.MAX_PEER_FAILURES):
                login_throttle.login_failed("192.0.2.2", f"user-{index}@example.test")
            self.assertFalse(login_throttle.login_allowed("192.0.2.2", "new@example.test"))
            self.assertTrue(login_throttle.login_allowed("192.0.2.3", "new@example.test"))


if __name__ == "__main__":
    unittest.main()
