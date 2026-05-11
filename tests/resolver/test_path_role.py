import pytest

from quodeq.resolver.path_role import classify_path_role


@pytest.mark.parametrize(
    "path,expected",
    [
        # composition roots: app/main/cli entry points
        ("src/quodeq/api/app.py", "composition_root"),
        ("app.py", "composition_root"),
        ("src/foo/main.py", "composition_root"),
        ("src/foo/cli.py", "composition_root"),
        ("src/foo/__main__.py", "composition_root"),
        # tests
        ("tests/api/test_app.py", "test"),
        ("tests/test_smoke.py", "test"),
        ("src/foo/_test_helpers.py", "test"),
        # generated / vendored
        ("src/foo/proto_pb2.py", "generated"),
        ("vendor/third_party/lib.py", "vendored"),
        ("node_modules/foo/index.js", "vendored"),
        # migrations
        ("migrations/0001_initial.py", "migration"),
        ("alembic/versions/abc_add_users.py", "migration"),
        # other
        ("src/foo/utils.py", "other"),
        ("src/foo/models/user.py", "other"),
    ],
)
def test_classify_path_role(path: str, expected: str) -> None:
    assert classify_path_role(path) == expected
