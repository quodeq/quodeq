"""Unit tests for check_loop_io.py's loop-IO classification."""
import ast
import textwrap

import check_loop_io as cli


def _sites(src: str) -> list[tuple[int, str]]:
    """Scan a snippet the way the ratchet scans a file; return sorted (lineno, callee)."""
    tree = ast.parse(textwrap.dedent(src))
    return sorted((lineno, callee) for _rel, lineno, callee in cli.scan_tree(tree, "x.py"))


def test_read_of_a_loop_invariant_path_is_flagged():
    src = """
    for item in items:
        cfg = settings_path.read_text()
    """
    assert _sites(src) == [(3, "read_text")]


def test_read_of_the_loop_item_is_exempt():
    src = """
    for path in folder.glob("*.json"):
        data = path.read_text()
    """
    assert _sites(src) == []


def test_read_of_a_path_derived_from_the_loop_item_is_exempt():
    src = """
    for run_dir in run_dirs:
        status = run_dir / "status.json"
        data = status.read_text()
    """
    assert _sites(src) == []


def test_name_assigned_in_the_body_from_invariants_is_not_exempt():
    # Binding a name inside the loop does not make it per item; only data
    # flow from the loop target does.
    src = """
    for item in items:
        cfg = base / "settings.json"
        cfg.read_text()
    """
    assert _sites(src) == [(4, "read_text")]


def test_open_helper_on_a_shared_path_is_flagged():
    src = """
    for finding in findings:
        with open_evaluation_db(run_dir) as conn:
            conn.execute("INSERT ...")
    """
    assert _sites(src) == [(3, "open_evaluation_db")]


def test_open_helper_on_the_loop_item_is_exempt():
    src = """
    for run_dir in runs:
        with open_evaluation_db(run_dir) as conn:
            pass
    """
    assert _sites(src) == []


def test_builtin_open_and_sqlite_connect_on_shared_targets_are_flagged():
    src = """
    for row in rows:
        fh = open(log_path, "a")
        conn = sqlite3.connect(db_path)
    """
    assert _sites(src) == [(3, "open"), (4, "connect")]


def test_open_helper_without_arguments_is_flagged():
    src = """
    for key in keys:
        cache = open_score_cache()
    """
    assert _sites(src) == [(3, "open_score_cache")]


def test_emit_is_flagged_even_with_a_per_item_payload():
    src = """
    for finding in findings:
        writer.emit(make_event(finding))
    """
    assert _sites(src) == [(3, "emit")]


def test_get_file_lock_is_flagged_even_on_the_loop_item():
    src = """
    for path in paths:
        with get_file_lock(path):
            pass
    """
    assert _sites(src) == [(3, "get_file_lock")]


def test_while_body_is_scanned():
    src = """
    while not done():
        state = status_path.read_text()
    """
    assert _sites(src) == [(3, "read_text")]


def test_comprehension_element_is_scanned_but_first_iterable_is_not():
    src = """
    rows = [log_path.read_text() for _ in open_index(db).rows()]
    """
    assert _sites(src) == [(2, "read_text")]


def test_second_comprehension_iterable_runs_per_item():
    src = """
    keys = {k for a in outer for k in shared.read_text().split()}
    """
    assert _sites(src) == [(2, "read_text")]


def test_comprehension_over_its_own_item_is_exempt():
    src = """
    texts = [p.read_text() for p in folder.glob("*.md")]
    """
    assert _sites(src) == []


def test_small_literal_loop_is_exempt():
    src = """
    for source in (ours, theirs):
        lines = log_path.read_text()
    """
    assert _sites(src) == []


def test_literal_longer_than_the_limit_is_scanned():
    src = """
    for source in (a, b, c, d):
        lines = log_path.read_text()
    """
    assert _sites(src) == [(3, "read_text")]


def test_nested_function_body_is_not_scanned():
    src = """
    for item in items:
        def later():
            return log_path.read_text()
        callbacks.append(later)
    """
    assert _sites(src) == []


def test_io_outside_any_loop_is_not_flagged():
    src = """
    data = log_path.read_text()
    with open(path) as fh:
        for line in fh:
            parse(line)
    """
    assert _sites(src) == []


def test_unrelated_calls_named_like_io_prefixes_are_not_flagged():
    # `opener`, `read`, `emit_many` are not in the callee set.
    src = """
    for item in items:
        opener(item)
        fh.read()
        writer.emit_many(events)
    """
    assert _sites(src) == []


def test_two_loops_over_the_same_site_key_it_once():
    src = """
    for a in outer:
        for b in inner:
            writer.emit(b)
    """
    assert _sites(src) == [(4, "emit")]


def test_inner_loop_over_shared_files_is_flagged_by_the_outer_loop():
    # Re-reading the same fixed files once per outer item is the repeated
    # read this gate exists for, even though each read is per inner item.
    src = """
    for dim in dims:
        for path in standards_dir.glob("*.json"):
            path.read_text()
    """
    assert _sites(src) == [(4, "read_text")]


def test_violation_key_shape():
    assert cli.violation_key(("src/quodeq/data/x.py", 12, "emit")) == "src/quodeq/data/x.py:12:emit"


def test_async_for_body_is_scanned():
    src = """
    async def pump():
        async for event in stream:
            writer.emit(event)
    """
    assert _sites(src) == [(4, "emit")]


def test_unparseable_file_is_skipped_with_a_warning(tmp_path, capsys):
    bad = tmp_path / "broken.py"
    bad.write_text("def (:\n", encoding="utf-8")

    assert cli._scan_file(bad) == set()
    assert "skipping" in capsys.readouterr().err
