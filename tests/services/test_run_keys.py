from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.services.run_keys import read_run_key_sets


def test_reads_dismiss_and_class_keys(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    with open_evaluation_db(run_dir) as conn:
        conn.execute(
            "INSERT INTO findings (practice_id, dimension, requirement, verdict, "
            "severity, file, line, dedup_key) VALUES "
            "('P1','security','R1','violation','major','a.py',1,'k1'),"
            "('P2','security','R2','dismissed','minor','b.py',2,'k2')"
        )
        conn.commit()

    dismiss, cls = read_run_key_sets(run_dir)
    assert ("R1", "a.py", 1) in dismiss
    assert ("R2", "b.py", 2) in dismiss          # dismissed rows still contribute keys
    assert ("security", "P1", "a.py") in cls
    assert ("security", "P2", "b.py") in cls


def test_missing_db_is_empty(tmp_path):
    assert read_run_key_sets(tmp_path / "nope") == (set(), set())


def _seed_rows(run_dir, rows):
    with open_evaluation_db(run_dir) as conn:
        conn.executemany(
            "INSERT INTO findings (practice_id, dimension, requirement, verdict, "
            "severity, file, line, snippet, dedup_key) VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()


def _row(i, snippet="x = 1"):
    return ("P1", "security", "R1", "violation", "major", f"f{i}.py", i, snippet, f"k{i}")


def test_unchanged_db_does_not_rehash_the_findings(tmp_path, monkeypatch):
    # The project list and every scores call re-read the key sets of each
    # run that is not cached; hashing every snippet again per request was
    # 1.1s of a 3.2s list rebuild. An unchanged evaluation.db must be served
    # from the in-process memo without touching finding_dismiss_keys.
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    _seed_rows(run_dir, [_row(1), _row(2)])
    first = read_run_key_sets(run_dir)

    from quodeq.data.sqlite import findings_queries

    def _boom(**kw):
        raise AssertionError("key sets were recomputed for an unchanged db")

    monkeypatch.setattr(findings_queries, "finding_dismiss_keys", _boom)
    assert read_run_key_sets(run_dir) == first


def test_changed_db_recomputes_the_key_sets(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    _seed_rows(run_dir, [_row(1)])
    before = read_run_key_sets(run_dir)
    # Enough rows to grow the file, so mtime and size both move.
    _seed_rows(run_dir, [_row(i, snippet="y" * 200) for i in range(2, 300)])
    after = read_run_key_sets(run_dir)
    assert ("R1", "f1.py", 1) in before[0] and ("R1", "f299.py", 299) not in before[0]
    assert ("R1", "f299.py", 299) in after[0]
    assert ("security", "P1", "f299.py") in after[1]


def test_returned_key_sets_are_independent_copies(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    _seed_rows(run_dir, [_row(1)])
    dismiss, cls = read_run_key_sets(run_dir)
    dismiss.add(("Rx", "z.py", 99))
    cls.clear()
    again = read_run_key_sets(run_dir)
    assert ("Rx", "z.py", 99) not in again[0]
    assert ("security", "P1", "f1.py") in again[1]
