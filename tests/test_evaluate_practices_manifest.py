from codecompass.evaluate.lib.manifest import manifest_exists


def test_manifest_exists_false(tmp_path):
    assert manifest_exists(str(tmp_path)) is False
