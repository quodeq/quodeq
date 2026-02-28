from codecompass.evaluate.lib.compatibility import env_bool


def test_env_bool_defaults_false():
    assert env_bool("MISSING") is False
