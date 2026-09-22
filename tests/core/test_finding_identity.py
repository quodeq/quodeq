"""The dismiss identity: fingerprint first, line for snippet-less findings.

Pins ``fold_dismissals`` (how the actions log nets out) and
``DismissedKeys.matches`` (the one membership predicate every surface uses),
plus the run-key intersection the score cache versions on.
"""
from __future__ import annotations

from datetime import datetime, timezone

from quodeq.core.events.models import (
    FindingDismissed,
    FindingDismissedEvent,
    FindingUndismissed,
    FindingUndismissedEvent,
    FindingVerified,
    FindingVerifiedEvent,
)
from quodeq.core.dismissals import DismissedEntry, DismissedKeys, fold_dismissals
from quodeq.core.finding_identity import (
    dismiss_identities,
    finding_dismiss_keys,
    fingerprint,
    snippet_fingerprint,
)

SNIP = "except Exception:\n    pass"
FP = snippet_fingerprint("R1", SNIP)


def _dismiss(req="R1", file="a.py", line=10, fp=None, reason=None):
    return FindingDismissedEvent(payload=FindingDismissed(
        req=req, file=file, line=line, fingerprint=fp, reason=reason))


def _undismiss(req="R1", file="a.py", line=10, fp=None):
    return FindingUndismissedEvent(payload=FindingUndismissed(
        req=req, file=file, line=line, fingerprint=fp))


class TestSnippetFingerprint:
    def test_same_hash_as_the_sarif_fingerprint(self):
        assert snippet_fingerprint("R1", SNIP) == fingerprint("R1", SNIP)

    def test_whitespace_shifts_do_not_change_it(self):
        assert snippet_fingerprint("R1", "  except Exception:\n\n\tpass  ") == FP

    def test_blank_snippet_has_no_fingerprint(self):
        """Unlike fingerprint(), a req-only hash would make every snippet-less
        finding under one requirement share an identity."""
        assert fingerprint("R1", "") is not None
        assert snippet_fingerprint("R1", "") is None
        assert snippet_fingerprint("R1", None) is None
        assert snippet_fingerprint("R1", "  \n ") is None


class TestDismissIdentities:
    def test_req_bearing_finding_is_keyed_on_its_req_only(self):
        assert dismiss_identities("R1", "Modularity") == ("R1",)

    def test_no_req_finding_accepts_principle_and_empty_forms(self):
        assert dismiss_identities(None, "Modularity") == ("Modularity", "")
        assert dismiss_identities("", "") == ("",)

    def test_finding_dismiss_keys_covers_both_shapes_for_every_identity(self):
        keys = finding_dismiss_keys(
            req=None, principle="Modularity", file="a.py", line=7, snippet=SNIP)
        assert keys == {
            ("Modularity", "a.py", 7), ("", "a.py", 7),
            ("Modularity", "a.py", snippet_fingerprint("Modularity", SNIP)),
            ("", "a.py", snippet_fingerprint("", SNIP)),
        }

    def test_finding_dismiss_keys_without_snippet_has_line_keys_only(self):
        assert finding_dismiss_keys(req="R1", principle="P", file="a.py", line="12", snippet="") \
            == {("R1", "a.py", 12)}


class TestFold:
    def test_dismiss_then_undismiss_nets_to_empty(self):
        assert not fold_dismissals([_dismiss(fp=FP), _undismiss(fp=FP)])

    def test_fingerprinted_dismiss_supersedes_the_line_keyed_entry(self):
        """How the backfill upgrades a legacy entry without rewriting the log."""
        state = fold_dismissals([_dismiss(reason="legacy"), _dismiss(fp=FP, reason="legacy")])
        assert state.entries == (DismissedEntry("R1", "a.py", 10, FP),)
        assert state.unresolved_lines == frozenset()

    def test_line_keyed_entry_keeps_reason_and_timestamp(self):
        event = _dismiss(reason="false positive")
        (entry,) = fold_dismissals([event]).entries
        assert entry.reason == "false positive"
        assert entry.dismissed_at == event.timestamp
        assert entry.fingerprint is None

    def test_fingerprinted_undismiss_also_removes_the_line_keyed_twin(self):
        assert not fold_dismissals([_dismiss(), _dismiss(fp=FP), _undismiss(fp=FP)])

    def test_legacy_undismiss_removes_every_entry_at_its_location(self):
        """An older client can only say "restore (req, file, line)"."""
        assert not fold_dismissals([_dismiss(fp=FP), _dismiss(), _undismiss()])

    def test_legacy_undismiss_leaves_other_findings_alone(self):
        state = fold_dismissals([_dismiss(fp=FP), _dismiss(line=20, fp="other"), _undismiss()])
        assert state.entries == (DismissedEntry("R1", "a.py", 20, "other"),)

    def test_other_event_types_are_ignored(self):
        verified = FindingVerifiedEvent(payload=FindingVerified(req="R1", file="a.py", line=10))
        assert fold_dismissals([verified, _dismiss(fp=FP)]).entries == (
            DismissedEntry("R1", "a.py", 10, FP),)

    def test_entries_are_sorted_for_stable_hashing(self):
        a = fold_dismissals([_dismiss(file="b.py", fp=FP), _dismiss(file="a.py", fp=FP)])
        b = fold_dismissals([_dismiss(file="a.py", fp=FP), _dismiss(file="b.py", fp=FP)])
        assert a.version_payload() == b.version_payload()


class TestMatches:
    state = fold_dismissals([_dismiss(fp=FP)])

    def test_matches_the_same_code_at_any_line(self):
        for line in (10, 11, 9999):
            assert self.state.matches(req="R1", file="a.py", line=line, snippet=SNIP)

    def test_different_code_at_the_recorded_line_does_not_match(self):
        assert not self.state.matches(req="R1", file="a.py", line=10, snippet="return x")

    def test_other_file_or_req_does_not_match(self):
        assert not self.state.matches(req="R1", file="b.py", line=10, snippet=SNIP)
        assert not self.state.matches(req="R2", file="a.py", line=10, snippet=SNIP)

    def test_snippet_less_finding_matches_by_line(self):
        assert self.state.matches(req="R1", file="a.py", line=10, snippet=None)
        assert not self.state.matches(req="R1", file="a.py", line=11, snippet=None)

    def test_line_keyed_entry_matches_a_snippet_bearing_finding_by_line(self):
        """Legacy entries the backfill could not resolve keep working."""
        legacy = fold_dismissals([_dismiss()])
        assert legacy.matches(req="R1", file="a.py", line=10, snippet=SNIP)
        assert not legacy.matches(req="R1", file="a.py", line=11, snippet=SNIP)

    def test_line_is_coerced_like_the_keys(self):
        legacy = fold_dismissals([_dismiss()])
        assert legacy.matches(req="R1", file="a.py", line="10", snippet=None)

    def test_no_req_finding_matches_the_principle_form(self):
        by_principle = fold_dismissals([
            _dismiss(req="Modularity", file="b.kt", line=7, fp=snippet_fingerprint("Modularity", SNIP))])
        assert by_principle.matches(req=None, principle="Modularity", file="b.kt", line=99, snippet=SNIP)

    def test_no_req_finding_matches_the_empty_req_form(self):
        by_empty = fold_dismissals([
            _dismiss(req="", file="b.kt", line=7, fp=snippet_fingerprint("", SNIP))])
        assert by_empty.matches(req=None, principle="Modularity", file="b.kt", line=99, snippet=SNIP)

    def test_req_bearing_finding_ignores_the_principle_form(self):
        by_principle = fold_dismissals([_dismiss(req="Modularity", file="b.kt", line=7)])
        assert not by_principle.matches(req="R9", principle="Modularity", file="b.kt", line=7)

    def test_empty_state_matches_nothing(self):
        assert not DismissedKeys().matches(req="R1", file="a.py", line=10, snippet=SNIP)


class TestRunScoping:
    def test_touching_keeps_entries_a_run_can_hide(self):
        moved = finding_dismiss_keys(req="R1", principle="P", file="a.py", line=42, snippet=SNIP)
        state = fold_dismissals([_dismiss(fp=FP), _dismiss(req="R2", file="z.py", line=1, fp="zz")])
        assert state.touching(moved).entries == (DismissedEntry("R1", "a.py", 10, FP),)

    def test_touching_uses_the_line_for_snippet_less_rows(self):
        run_keys = finding_dismiss_keys(req="R1", principle="P", file="a.py", line=10, snippet="")
        assert fold_dismissals([_dismiss(fp=FP)]).touching(run_keys)

    def test_from_line_keys_adopts_the_legacy_set_form(self):
        state = DismissedKeys.from_line_keys({("R1", "a.py", "10")})
        assert state.line_keys() == {("R1", "a.py", 10)}
        assert state.matches(req="R1", file="a.py", line=10, snippet=SNIP)

    def test_version_payload_changes_with_the_fingerprint(self):
        a = fold_dismissals([_dismiss()]).version_payload()
        b = fold_dismissals([_dismiss(fp=FP)]).version_payload()
        assert a != b
        assert b == [["R1", "a.py", 10, FP]]

    def test_entries_at_returns_every_form_recorded_at_a_location(self):
        state = fold_dismissals([_dismiss(fp=FP), _dismiss(fp="other")])
        assert {e.fingerprint for e in state.entries_at("R1", "a.py", 10)} == {FP, "other"}


def test_dismissed_at_is_not_part_of_the_identity():
    now = datetime.now(timezone.utc)
    assert DismissedEntry("R1", "a.py", 10, FP, dismissed_at=now) == DismissedEntry("R1", "a.py", 10, FP)
