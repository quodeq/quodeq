"""The ``unmapped_findings`` side of the state store."""
from __future__ import annotations

from quodeq.core.events.models import Judgment
from quodeq.data.sqlite._schema import INSERT_UNMAPPED_SQL
from quodeq.data.sqlite.row_mappers import judgment_to_unmapped_row


class UnmappedFindingsMixin:
    """Findings the standard cannot place, kept out of the graded ``findings``.

    Relies on ``self._db()`` and ``self._held`` from ``SQLiteStateStore``.
    """

    def record_unmapped(self, payload: Judgment, reason: str) -> None:
        """Keep one judgment the standard cannot place, out of ``findings``."""
        row = judgment_to_unmapped_row(payload, reason)
        with self._db() as conn:
            conn.execute(INSERT_UNMAPPED_SQL, row)
            if self._held is None:
                conn.commit()

    def projected_dimensions(self) -> set[str]:
        """Every dimension this run has findings for, placed or unmapped (lower-cased)."""
        with self._db() as conn:
            rows = conn.execute(
                "SELECT lower(dimension) FROM findings UNION "
                "SELECT lower(dimension) FROM unmapped_findings"
            ).fetchall()
        return {r[0] for r in rows if r[0]}
