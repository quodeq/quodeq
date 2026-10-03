"""The Grade vocabulary, the numeric label tuple and the pinned text ladder."""
from quodeq.core.scoring.constants import GRADE_LADDER, Grade
from quodeq.core.scoring.params import GRADE_LABELS


def test_ladder_order_is_pinned():
    # GRADE_LADDER is the qualitative ("text mode") ladder, worst to best, and
    # is NOT the Grade label set: drop_grade() and the weighted-grade
    # aggregation index into it, so its order and content are the contract.
    assert GRADE_LADDER == ["Insufficient", "Developing", "Proficient", "Exemplary"]


def test_grade_labels_are_the_enum():
    assert GRADE_LABELS == (Grade.EXEMPLARY, Grade.GOOD, Grade.ADEQUATE, Grade.POOR)
    assert set(GRADE_LABELS) <= {g.value for g in Grade}


def test_members_are_their_label_strings():
    assert Grade.INSUFFICIENT == "Insufficient"
    assert Grade("Exemplary") is Grade.EXEMPLARY
