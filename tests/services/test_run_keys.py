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
