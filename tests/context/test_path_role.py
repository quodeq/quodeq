import pytest

from quodeq.context.path_role import NON_PROD_ROLES, Role, path_role


@pytest.mark.parametrize("path", [
    "src/quodeq/api/server.py",
    "lib/main.go",
    "app/components/Button.tsx",
    "internal/auth/oauth.go",
    "src/index.js",
])
def test_production_paths_default_to_prod(path):
    assert path_role(path) is Role.PROD


@pytest.mark.parametrize("path", [
    "tests/test_server.py",
    "tests/api/test_routes.py",
    "src/__tests__/Button.test.jsx",
    "internal/auth/oauth_test.go",
    "components/Button.test.tsx",
    "components/Button.spec.ts",
    "src/MyClassTest.java",
    "src/MyClassSpec.kt",
])
def test_test_paths_classified_as_test(path):
    assert path_role(path) is Role.TEST


@pytest.mark.parametrize("path", [
    "tests/fixtures/sample.json",
    "tests/fixtures/nested/data.txt",
    "internal/parser/testdata/golden.txt",
    "src/__fixtures__/users.json",
    "src/components/__tests__/__fixtures__/data.json",
])
def test_fixture_paths_classified_as_test_fixture(path):
    assert path_role(path) is Role.TEST_FIXTURE


def test_fixture_pattern_wins_over_tests_pattern():
    """`tests/fixtures/**` is listed before `tests/**`, so fixtures don't get
    misclassified as TEST."""
    assert path_role("tests/fixtures/foo.json") is Role.TEST_FIXTURE


@pytest.mark.parametrize("path,expected", [
    ("packaging/macos/launcher.sh", Role.PACKAGING),
    ("Dockerfile", Role.PACKAGING),
    ("docker/Dockerfile.dev", Role.PACKAGING),
    (".github/workflows/ci.yml", Role.PACKAGING),
    ("scripts/release.sh", Role.TOOL),
    ("tools/codegen.py", Role.TOOL),
    ("docs/architecture.md", Role.DOC),
    ("README.md", Role.DOC),
    ("pyproject.toml", Role.CONFIG),
    ("config.yaml", Role.CONFIG),
    ("dist/bundle.js", Role.BUILD),
    ("build/output.bin", Role.BUILD),
])
def test_special_directories(path, expected):
    assert path_role(path) is expected


def test_none_returns_prod():
    assert path_role(None) is Role.PROD


def test_empty_string_returns_prod():
    assert path_role("") is Role.PROD


def test_windows_separators_are_normalized():
    assert path_role("tests\\fixtures\\sample.json") is Role.TEST_FIXTURE
    assert path_role("src\\index.js") is Role.PROD


def test_leading_slash_is_stripped():
    assert path_role("/tests/test_foo.py") is Role.TEST


def test_non_prod_roles_set_excludes_prod():
    assert Role.PROD not in NON_PROD_ROLES
    # Every other role is in the set.
    for role in Role:
        if role is not Role.PROD:
            assert role in NON_PROD_ROLES
