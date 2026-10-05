"""Shared fixtures for tests/api/test_routes_shared_read*.py siblings.

``shared_clone_fixture`` (a published clone) lives in tests/api/conftest.py;
``empty_shared_clone_fixture`` here is the cloned-but-never-published twin.
"""
from __future__ import annotations

import time

import pytest

from quodeq.api.app import create_app
from quodeq.data.fs.shared_repo import ensure_shared_clone
from quodeq.services.shared_settings import SharedSettings, write_settings
from tests.api.conftest import _make_origin


def wait_shared_warmup_idle(timeout_s: float = 10.0) -> None:
    """Block until the shared warm-up has no project queued or in flight.

    A cold shared card stays off the listing, and a cold shared Overview
    answers pending, until the clone's worker has warmed the project; tests
    that read the settled state wait here first.
    """
    from quodeq.services.shared_listing import shared_warmup

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        snapshot = shared_warmup.snapshot()
        if snapshot is None or not snapshot["active"]:
            return
        time.sleep(0.02)
    raise AssertionError("shared warm-up did not settle in time")


def get_shared_settled(client, path: str):
    """GET *path* on a shared Overview mirror; a pending answer waits for the warm-up and asks again."""
    resp = client.get(path)
    if resp.status_code != 202:
        return resp
    wait_shared_warmup_idle()
    return client.get(path)


def list_shared_settled(client, path: str = "/api/shared/projects") -> dict:
    """GET *path*; when the server is still warming cards it has not listed yet, wait and re-list.

    The re-list drops the query string (a forced refresh must not run twice)
    and keeps the first answer's ``stale`` flag, which is what the refresh
    tests assert on.
    """
    resp = client.get(path)
    assert resp.status_code == 200
    body = resp.get_json()
    if not body.get("warmup", {}).get("active"):
        return body
    wait_shared_warmup_idle()
    resp = client.get(path.split("?")[0])
    assert resp.status_code == 200
    return {**resp.get_json(), **{k: v for k, v in body.items() if k == "stale"}}


@pytest.fixture()
def app():
    return create_app(test_config={"TESTING": True})


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture()
def empty_shared_clone_fixture(tmp_path):
    """A cloned-but-never-published shared repo (audit A1's "empty" case).

    The clone exists for real (a real `git clone` of a real local bare
    origin) but nothing has ever been published into it, so read_state
    reports "empty" rather than "missing". Mirrors shared_clone_fixture
    minus the publish_project step.
    """
    url = _make_origin(tmp_path)
    assert ensure_shared_clone(url) is not None
    write_settings(SharedSettings(url=url))
    return url
