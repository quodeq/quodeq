from codecompass.action_provider import ActionProvider


def test_action_provider_contract_methods():
    provider = ActionProvider()
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
        assert hasattr(provider, name)
