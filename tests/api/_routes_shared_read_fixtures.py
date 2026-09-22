"""Shared fixtures for tests/api/test_routes_shared_read*.py siblings.

``shared_clone_fixture`` (a published clone) lives in tests/api/conftest.py;
``empty_shared_clone_fixture`` here is the cloned-but-never-published twin.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app
from quodeq.data.fs.shared_repo import ensure_shared_clone
from quodeq.services.shared_settings import SharedSettings, write_settings
from tests.api.conftest import _make_origin


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
