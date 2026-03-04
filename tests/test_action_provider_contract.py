from codecompass.action_provider import ActionProvider
from codecompass.action_provider_fs import FilesystemActionProvider


def test_action_provider_contract_methods():
    """Verify ActionProvider Protocol declares all expected methods."""
    for name in [
        "list_projects",
        "get_dashboard",
        "get_accumulated",
        "get_dimension_eval",
        "get_run_plan",
        "get_violations",
        "start_evaluation",
        "get_evaluation_status",
        "browse_repo",
    ]:
        assert hasattr(ActionProvider, name), f"Missing method: {name}"


def test_filesystem_provider_satisfies_protocol():
    """Verify FilesystemActionProvider is a structural subtype of ActionProvider."""
    assert isinstance(FilesystemActionProvider(), ActionProvider)
