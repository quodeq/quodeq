from quodeq.engine.standards import load_dimension, load_asvs_l1, load_cisq


def test_load_maintainability_dimension():
    dim = load_dimension("maintainability")
    assert dim["id"] == "maintainability"
    assert "sub_characteristics" in dim
    # New grouped structure: sub_characteristics are objects with name + requirements
    sc = dim["sub_characteristics"][0]
    assert isinstance(sc, dict)
    assert "name" in sc
    assert "requirements" in sc
    assert len(sc["requirements"]) > 0
    assert all("cwe" in r for r in sc["requirements"])
    assert all("id" in r for r in sc["requirements"])
    assert all("text" in r for r in sc["requirements"])


def test_all_dimensions_have_grouped_sub_characteristics():
    for dim_id in ["maintainability", "reliability", "security", "performance", "flexibility", "usability"]:
        dim = load_dimension(dim_id)
        assert dim["id"] == dim_id
        assert len(dim["sub_characteristics"]) > 0
        for sc in dim["sub_characteristics"]:
            assert isinstance(sc, dict), f"{dim_id}: sub_characteristic should be a dict"
            assert "name" in sc, f"{dim_id}: sub_characteristic missing 'name'"
            assert "requirements" in sc, f"{dim_id}/{sc.get('name')}: missing 'requirements'"
            assert len(sc["requirements"]) > 0, f"{dim_id}/{sc['name']}: empty requirements"


def test_load_asvs_l1():
    asvs = load_asvs_l1()
    assert asvs["level"] == 1
    # ASVS L1 has ~60+ requirements; threshold prevents accidental truncation
    _MIN_ASVS_L1_REQUIREMENTS = 50
    assert len(asvs["requirements"]) > _MIN_ASVS_L1_REQUIREMENTS
    assert all("id" in r for r in asvs["requirements"])


def test_load_cisq_maintainability():
    cisq = load_cisq("maintainability")
    assert len(cisq["cwes"]) > 0
    # New structure includes requirement text
    assert all("requirement" in c for c in cisq["cwes"])


def test_load_cisq_all_characteristics():
    # Each CISQ characteristic must have at least this many CWE entries;
    # guards against accidental truncation of the standards data.
    _MIN_CWES_PER_CHARACTERISTIC = 12
    for char in ["maintainability", "reliability", "security", "performance"]:
        cisq = load_cisq(char)
        assert len(cisq["cwes"]) >= _MIN_CWES_PER_CHARACTERISTIC, f"{char}: expected ≥{_MIN_CWES_PER_CHARACTERISTIC} CWEs, got {len(cisq['cwes'])}"
        for cwe in cisq["cwes"]:
            assert "id" in cwe
            assert "name" in cwe
            assert "requirement" in cwe
