"""Unit tests for the retry_with_backoff decorator."""

import logging
from unittest.mock import MagicMock, call

import pytest

from makita_dr.retry import retry_with_backoff


class TestRetryWithBackoff:
    """Tests for retry_with_backoff decorator."""

    def test_succeeds_on_first_attempt(self):
        """Function that succeeds immediately should not retry."""
        sleep = MagicMock()
        func = MagicMock(return_value="ok")

        @retry_with_backoff(sleep_func=sleep)
        def action():
            return func()

        assert action() == "ok"
        func.assert_called_once()
        sleep.assert_not_called()

    def test_retries_on_connection_error(self):
        """Should retry on ConnectionError and succeed when it clears."""
        sleep = MagicMock()
        func = MagicMock(side_effect=[ConnectionError("down"), "ok"])

        @retry_with_backoff(sleep_func=sleep)
        def action():
            return func()

        assert action() == "ok"
        assert func.call_count == 2
        sleep.assert_called_once_with(1.0)  # base_delay * 2^0

    def test_retries_on_timeout_error(self):
        """Should retry on TimeoutError."""
        sleep = MagicMock()
        func = MagicMock(side_effect=[TimeoutError("timeout"), "ok"])

        @retry_with_backoff(sleep_func=sleep)
        def action():
            return func()

        assert action() == "ok"
        assert func.call_count == 2

    def test_exponential_backoff_delays(self):
        """Delays should follow base_delay * 2^attempt pattern."""
        sleep = MagicMock()
        func = MagicMock(
            side_effect=[
                ConnectionError("1"),
                ConnectionError("2"),
                ConnectionError("3"),
                "ok",
            ]
        )

        @retry_with_backoff(max_retries=3, base_delay=1.0, sleep_func=sleep)
        def action():
            return func()

        assert action() == "ok"
        assert func.call_count == 4
        sleep.assert_has_calls([call(1.0), call(2.0), call(4.0)])

    def test_raises_after_max_retries_exhausted(self):
        """Should re-raise the last exception after all retries fail."""
        sleep = MagicMock()
        func = MagicMock(side_effect=ConnectionError("still down"))

        @retry_with_backoff(max_retries=3, sleep_func=sleep)
        def action():
            return func()

        with pytest.raises(ConnectionError, match="still down"):
            action()

        # 1 initial + 3 retries = 4 total attempts
        assert func.call_count == 4
        assert sleep.call_count == 3

    def test_does_not_catch_unrelated_exceptions(self):
        """Exceptions not in the exceptions tuple should propagate immediately."""
        sleep = MagicMock()
        func = MagicMock(side_effect=ValueError("bad input"))

        @retry_with_backoff(sleep_func=sleep)
        def action():
            return func()

        with pytest.raises(ValueError, match="bad input"):
            action()

        func.assert_called_once()
        sleep.assert_not_called()

    def test_custom_exceptions(self):
        """Should retry on custom exception types when specified."""
        sleep = MagicMock()

        class ServiceUnavailable(Exception):
            pass

        func = MagicMock(side_effect=[ServiceUnavailable("503"), "ok"])

        @retry_with_backoff(exceptions=(ServiceUnavailable,), sleep_func=sleep)
        def action():
            return func()

        assert action() == "ok"
        assert func.call_count == 2

    def test_custom_base_delay(self):
        """Should respect a custom base delay."""
        sleep = MagicMock()
        func = MagicMock(side_effect=[ConnectionError("err"), "ok"])

        @retry_with_backoff(base_delay=0.5, sleep_func=sleep)
        def action():
            return func()

        action()
        sleep.assert_called_once_with(0.5)  # 0.5 * 2^0

    def test_max_retries_zero_no_retry(self):
        """With max_retries=0, should not retry at all."""
        sleep = MagicMock()
        func = MagicMock(side_effect=ConnectionError("fail"))

        @retry_with_backoff(max_retries=0, sleep_func=sleep)
        def action():
            return func()

        with pytest.raises(ConnectionError):
            action()

        func.assert_called_once()
        sleep.assert_not_called()

    def test_preserves_function_name(self):
        """Decorated function should preserve the original function name."""

        @retry_with_backoff()
        def my_api_call():
            pass

        assert my_api_call.__name__ == "my_api_call"

    def test_passes_args_and_kwargs(self):
        """Should forward positional and keyword arguments to the wrapped function."""
        sleep = MagicMock()
        func = MagicMock(return_value="result")

        @retry_with_backoff(sleep_func=sleep)
        def action(a, b, key=None):
            return func(a, b, key=key)

        assert action(1, 2, key="val") == "result"
        func.assert_called_once_with(1, 2, key="val")

    def test_logs_retry_attempts(self, caplog):
        """Should log warning messages on each retry attempt."""
        sleep = MagicMock()
        func = MagicMock(side_effect=[ConnectionError("down"), "ok"])

        @retry_with_backoff(sleep_func=sleep)
        def my_func():
            return func()

        with caplog.at_level(logging.WARNING):
            my_func()

        assert "Attempt 1/4 for my_func failed" in caplog.text
        assert "Retrying in 1.0s" in caplog.text

    def test_logs_error_on_final_failure(self, caplog):
        """Should log error when all retries are exhausted."""
        sleep = MagicMock()
        func = MagicMock(side_effect=ConnectionError("down"))

        @retry_with_backoff(max_retries=1, sleep_func=sleep)
        def my_func():
            return func()

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ConnectionError):
                my_func()

        assert "All 2 attempts for my_func exhausted" in caplog.text
