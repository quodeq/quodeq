from codecompass.v2.engine.standards import load_dimension, load_asvs_l1, load_cisq


def test_load_maintainability_dimension():
    dim = load_dimension("maintainability")
    assert dim["id"] == "maintainability"
    assert "requirements" in dim
    assert all("cwe" in r for r in dim["requirements"])


def test_load_asvs_l1():
    asvs = load_asvs_l1()
    assert asvs["level"] == 1
    assert len(asvs["requirements"]) > 50
    assert all("id" in r for r in asvs["requirements"])


def test_load_cisq_maintainability():
    cisq = load_cisq("maintainability")
    assert len(cisq["cwes"]) > 0
