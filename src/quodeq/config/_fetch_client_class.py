"""Thread-safe HTTP fetcher with circuit breaker and retry.

QUODEQ_CIRCUIT_THRESHOLD consecutive failures open the circuit; after
QUODEQ_CIRCUIT_RESET_S seconds one probe request goes out, and its success
closes the circuit while its failure opens it for another cooldown.
QUODEQ_CIRCUIT_RESET_S=0 means the circuit never blocks: every call after the
threshold is a probe.
"""
from __future__ import annotations

import logging
import random
import ssl as _ssl
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from quodeq.shared.constants import ENV_TRUTHY, SCHEME_HTTP, SCHEME_HTTPS
from quodeq.shared.env import env_float, env_int
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.ssrf import is_private_address as _is_private_hostname

_logger = logging.getLogger(__name__)

# Ceiling on a single response body. ``timeout`` bounds how LONG a transfer may
# run; without a byte bound, a hostile or broken endpoint on a fast link still
# streams enough within that window to exhaust memory. Sized far above any real
# payload this client fetches (standards documents, release metadata).
_DEFAULT_MAX_BODY_BYTES = 10 * 1024 * 1024

# The timeout FetchClient uses when a caller does not pick one. Public: also
# used by _fetch_client.get_fetch_client()'s own default, which forwards it
# unchanged to this constructor.
DEFAULT_FETCH_CLIENT_TIMEOUT_S = 15
_DEFAULT_CIRCUIT_THRESHOLD = 5  # consecutive failures before the circuit breaker trips
_DEFAULT_RETRY_BACKOFF_S = 0.5  # QUODEQ_RETRY_BACKOFF_S fallback
_DEFAULT_CIRCUIT_RESET_S = 60.0  # QUODEQ_CIRCUIT_RESET_S fallback


class BlockedRedirect(urllib.error.URLError):
    """A 3xx pointed at a target the private-address policy refuses."""


class _RedirectGuard(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target before urllib follows it.

    The pre-flight check in :meth:`FetchClient.fetch` only sees the URL the
    caller asked for; a public host answering 302 to 169.254.169.254 or
    localhost would otherwise be followed with the body handed back.
    """

    def __init__(self, allow_private: bool) -> None:
        super().__init__()
        self._allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913 - urllib's signature
        target = urlparse(newurl)
        hostname = target.hostname or ""
        if target.scheme not in (SCHEME_HTTP, SCHEME_HTTPS) or (
            hostname and not self._allow_private and _is_private_hostname(hostname)
        ):
            _logger.warning("Blocked redirect to %s://%s", target.scheme, hostname)
            raise BlockedRedirect(f"redirect to blocked target {target.scheme}://{hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class FetchClient:
    """Thread-safe HTTP fetcher with circuit breaker (trips after repeated failures)."""

    def _record_success(self) -> None:
        """Reset the failure counter on a successful fetch; closes an open circuit."""
        with self._lock:
            was_open = self._opened_at is not None
            self._failures = 0
            self._opened_at = None
        if was_open:
            _logger.info("Circuit closed")

    def _record_failure(self, exc: Exception) -> None:
        """Increment failures and log; trips circuit breaker at threshold."""
        with self._lock:
            self._failures += 1
            count = self._failures
            if count >= self._CIRCUIT_THRESHOLD:
                self._opened_at = time.monotonic()
        if count >= self._CIRCUIT_THRESHOLD:
            _logger.warning("Circuit opened after %d failures: %s", count, exc)
        else:
            _logger.debug("Fetch failure %d/%d: %s", count, self._CIRCUIT_THRESHOLD, exc)

    def _is_circuit_open(self) -> bool:
        """Return True while the circuit is open and its cooldown has not passed.

        Once the cooldown has passed, one caller gets False (the half-open
        probe) and the cooldown restarts, so concurrent callers stay blocked
        until the probe's outcome closes or re-opens the circuit.
        """
        with self._lock:
            if self._opened_at is None:
                return False
            now = time.monotonic()
            if now - self._opened_at < self._CIRCUIT_RESET_S:
                return True
            self._opened_at = now
            return False

    def __init__(
        self, timeout_s: int = DEFAULT_FETCH_CLIENT_TIMEOUT_S,
        allow_private: bool | None = None, env: dict[str, str] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None
        self._timeout = timeout_s
        self._env = env
        _e = resolve_env(self._env)
        self._CIRCUIT_THRESHOLD = env_int("QUODEQ_CIRCUIT_THRESHOLD", _DEFAULT_CIRCUIT_THRESHOLD, minimum=1, env=_e)
        self._MAX_RETRIES = env_int("QUODEQ_MAX_RETRIES", 2, minimum=0, env=_e)
        self._CIRCUIT_RESET_S = env_float("QUODEQ_CIRCUIT_RESET_S", _DEFAULT_CIRCUIT_RESET_S, minimum=0.0, env=_e)
        self._RETRY_BACKOFF_S = env_float("QUODEQ_RETRY_BACKOFF_S", _DEFAULT_RETRY_BACKOFF_S, minimum=0.0, env=_e)
        self._MAX_BODY_BYTES = env_int("QUODEQ_MAX_RESPONSE_BYTES", _DEFAULT_MAX_BODY_BYTES, minimum=1, env=_e)
        if allow_private is not None:
            self._allow_private: bool = allow_private
        else:
            self._allow_private = _e.get("QUODEQ_ALLOW_PRIVATE_URLS") == ENV_TRUTHY

    def fetch(self, url: str, headers: dict | None = None) -> str | None:
        """Fetch *url* and return body text, or None on failure.

        Validates URL scheme (http/https only) and blocks requests to
        private/internal addresses unless QUODEQ_ALLOW_PRIVATE_URLS=1.
        """
        parsed = urlparse(url)
        if parsed.scheme not in (SCHEME_HTTP, SCHEME_HTTPS):
            _logger.warning("Blocked fetch with disallowed scheme: %s", parsed.scheme)
            return None
        hostname = parsed.hostname or ""
        if hostname and _is_private_hostname(hostname) and not self._allow_private:
            _logger.warning("Blocked fetch to private/internal address: %s", hostname)
            return None

        if self._is_circuit_open():
            return None

        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_ssl.create_default_context()),
            _RedirectGuard(self._allow_private),
        )
        last_exc: Exception | None = None
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                if hostname and not self._allow_private and _is_private_hostname(hostname):
                    _logger.warning("Blocked fetch after DNS re-check: %s", hostname)
                    return None
                req = urllib.request.Request(url, headers=headers or {})
                with opener.open(req, timeout=self._timeout) as r:
                    # One byte over the cap is enough to prove it was exceeded,
                    # and stops the read there rather than buffering the rest.
                    body = r.read(self._MAX_BODY_BYTES + 1)
                if len(body) > self._MAX_BODY_BYTES:
                    # Deterministic property of the endpoint: a retry would only
                    # re-download the cap, so fail now rather than looping.
                    _logger.warning(
                        "Blocked fetch: response body exceeds %d bytes: %s",
                        self._MAX_BODY_BYTES, url,
                    )
                    self._record_failure(ValueError("response body over size cap"))
                    return None
                self._record_success()
                return body.decode("utf-8", errors="replace")
            except BlockedRedirect as exc:
                # Policy, not transport: the endpoint will redirect the same
                # way again, so a retry only repeats the blocked hop.
                self._record_failure(exc)
                return None
            except (urllib.error.URLError, OSError, ValueError) as exc:
                last_exc = exc
                if attempt < self._MAX_RETRIES:
                    _logger.debug("Fetch retry %d/%d after: %s", attempt + 1, self._MAX_RETRIES, exc)
                    time.sleep(self._RETRY_BACKOFF_S * (2 ** attempt) + random.uniform(0, self._RETRY_BACKOFF_S))

        if last_exc is not None:
            self._record_failure(last_exc)
        return None
