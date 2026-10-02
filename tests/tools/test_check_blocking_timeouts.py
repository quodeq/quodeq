"""Unit tests for check_blocking_timeouts.py's AST scanner."""
import ast

import check_blocking_timeouts as cbt


def _kinds(src: str, rel: str = "src/quodeq/x.py") -> list[tuple[int, str]]:
    """Scan a source snippet the way the ratchet scans a file; return (lineno, kind)."""
    return [(lineno, kind) for _rel, lineno, kind in cbt._scan_tree(ast.parse(src), rel)]


# -- subprocess-run -----------------------------------------------------

def test_subprocess_run_without_timeout_is_flagged():
    assert _kinds("subprocess.run(['ls'])\n") == [(1, "subprocess-run")]


def test_subprocess_run_with_timeout_is_not_flagged():
    assert _kinds("subprocess.run(['ls'], timeout=5)\n") == []


def test_subprocess_check_call_without_timeout_is_flagged():
    assert _kinds("subprocess.check_call(['ls'])\n") == [(1, "subprocess-run")]


def test_subprocess_check_output_with_timeout_is_not_flagged():
    assert _kinds("subprocess.check_output(['ls'], timeout=5)\n") == []


def test_bare_run_imported_from_subprocess_is_flagged():
    src = "from subprocess import run\nrun(['ls'])\n"
    assert _kinds(src) == [(2, "subprocess-run")]


def test_bare_run_imported_with_timeout_is_not_flagged():
    src = "from subprocess import run\nrun(['ls'], timeout=5)\n"
    assert _kinds(src) == []


def test_popen_construction_is_never_flagged():
    assert _kinds("subprocess.Popen(['ls'])\n") == []


# -- subprocess-wait ------------------------------------------------------

def test_bare_wait_after_kill_on_a_popen_assignment_is_flagged():
    src = (
        "def f():\n"
        "    proc = subprocess.Popen(['ls'])\n"
        "    try:\n"
        "        proc.wait(timeout=5)\n"
        "    except subprocess.TimeoutExpired:\n"
        "        proc.kill()\n"
        "        proc.wait()\n"
    )
    assert _kinds(src) == [(7, "subprocess-wait")]


def test_wait_with_timeout_on_a_popen_assignment_is_not_flagged():
    src = (
        "def f():\n"
        "    proc = subprocess.Popen(['ls'])\n"
        "    proc.wait(timeout=5)\n"
    )
    assert _kinds(src) == []


def test_communicate_without_timeout_on_a_popen_assignment_is_flagged():
    src = (
        "def f():\n"
        "    proc = subprocess.Popen(['ls'])\n"
        "    proc.communicate()\n"
    )
    assert _kinds(src) == [(3, "subprocess-wait")]


def test_wait_through_a_spawn_named_call_is_flagged():
    # Mirrors assistant/adapters/cli.py: the
    # receiver comes from a call whose OWN name spells "spawn", not a
    # literal subprocess.Popen(...) expression.
    src = (
        "def f(session):\n"
        "    proc = session.spawn_fn(['ls'])\n"
        "    proc.wait()\n"
    )
    assert _kinds(src) == [(3, "subprocess-wait")]


def test_wait_through_a_spawn_aliased_callable_is_flagged():
    # Mirrors data/copilot_models.py: `spawn` is bound to
    # `process_factory or asyncio.create_subprocess_exec`, then called.
    src = (
        "def f(process_factory):\n"
        "    spawn = process_factory or asyncio.create_subprocess_exec\n"
        "    process = spawn()\n"
        "    process.wait()\n"
    )
    assert _kinds(src) == [(4, "subprocess-wait")]


def test_wait_on_a_popen_annotated_parameter_is_flagged():
    src = (
        "def f(proc: subprocess.Popen) -> None:\n"
        "    proc.wait()\n"
    )
    assert _kinds(src) == [(2, "subprocess-wait")]


def test_wait_on_a_popen_annotated_parameter_stored_on_self_is_flagged():
    src = (
        "class C:\n"
        "    def start(self, proc: subprocess.Popen) -> None:\n"
        "        self._proc = proc\n"
        "        self._proc.wait()\n"
    )
    assert _kinds(src) == [(4, "subprocess-wait")]


def test_wait_wrapped_in_asyncio_wait_for_is_not_flagged():
    src = (
        "async def f():\n"
        "    process = await asyncio.create_subprocess_exec('ls')\n"
        "    process.terminate()\n"
        "    await asyncio.wait_for(process.wait(), 5)\n"
    )
    assert _kinds(src) == []


def test_threading_event_wait_is_not_flagged():
    src = (
        "def f():\n"
        "    e = threading.Event()\n"
        "    e.wait()\n"
    )
    assert _kinds(src) == []


def test_threading_condition_wait_with_no_bound_receiver_is_not_flagged():
    # No local assignment ties `self._cond` to anything Popen-like in this
    # function, so it is never a candidate.
    src = (
        "def f(self):\n"
        "    self._cond.wait()\n"
    )
    assert _kinds(src) == []


def test_allowlisted_post_kill_reap_is_not_reported():
    # Reproduce the real git_cli.py:246 site (proc.wait() right after
    # proc.kill()) at its actual line number and relpath; the tool's
    # ALLOWLIST must suppress it.
    src = "\n" * 242 + (
        "def f():\n"          # line 243
        "    proc = subprocess.Popen([])\n"  # line 244
        "    proc.kill()\n"   # line 245
        "    proc.wait()\n"   # line 246
    )
    assert _kinds(src, rel="src/quodeq/data/git_cli.py") == []


# -- http-no-timeout ------------------------------------------------------

def test_httpx_get_without_timeout_is_flagged():
    assert _kinds("httpx.get(url)\n") == [(1, "http-no-timeout")]


def test_httpx_get_with_timeout_is_not_flagged():
    assert _kinds("httpx.get(url, timeout=5)\n") == []


def test_httpx_client_construction_without_timeout_is_flagged():
    assert _kinds("httpx.Client()\n") == [(1, "http-no-timeout")]


def test_httpx_async_client_with_timeout_is_not_flagged():
    assert _kinds("httpx.AsyncClient(timeout=5)\n") == []


def test_bare_httpx_get_imported_is_flagged():
    src = "from httpx import get\nget(url)\n"
    assert _kinds(src) == [(2, "http-no-timeout")]


def test_urlopen_without_timeout_is_flagged():
    assert _kinds("urllib.request.urlopen(url)\n") == [(1, "http-no-timeout")]


def test_urlopen_with_timeout_keyword_is_not_flagged():
    assert _kinds("urllib.request.urlopen(url, timeout=5)\n") == []


def test_urlopen_with_third_positional_timeout_is_not_flagged():
    assert _kinds("urllib.request.urlopen(url, None, 5)\n") == []


def test_bare_urlopen_imported_is_flagged():
    src = "from urllib.request import urlopen\nurlopen(url)\n"
    assert _kinds(src) == [(2, "http-no-timeout")]


def test_openai_construction_without_timeout_is_flagged():
    assert _kinds("openai.OpenAI()\n") == [(1, "http-no-timeout")]


def test_openai_construction_with_timeout_is_not_flagged():
    assert _kinds("openai.OpenAI(timeout=5)\n") == []


def test_bare_openai_imported_is_flagged():
    src = "from openai import OpenAI\nOpenAI()\n"
    assert _kinds(src) == [(2, "http-no-timeout")]


def test_kwargs_spread_with_no_literal_timeout_is_flagged():
    # A **kwargs spread is not given the benefit of the doubt: without a
    # literal `timeout=` keyword this is flagged like any other call.
    assert _kinds("httpx.get(url, **opts)\n") == [(1, "http-no-timeout")]


def test_openai_construction_via_kwargs_spread_is_allowlisted():
    # openai.OpenAI(**_client_kwargs(...)) at its real site
    # (llm_bridge/embeddings.py:88): timeout is always set by
    # _client_kwargs(), verified and allowlisted rather than exempted by a
    # blanket **kwargs rule.
    src = "\n" * 87 + "openai.OpenAI(**client_kwargs)\n"  # line 88
    assert _kinds(src, rel="src/quodeq/llm_bridge/embeddings.py") == []


def test_rules_module_scans_without_the_allowlist():
    import _blocking_timeouts_rules as rules

    src = "import subprocess\nsubprocess.run(['ls'])\n"
    assert rules.scan_tree(ast.parse(src), "x.py") == [("x.py", 2, rules.KIND_SUBPROCESS_RUN)]


def test_cli_module_stays_under_the_file_cap():
    from pathlib import Path

    import check_sizes

    cli = Path(cbt.__file__)
    assert len(cli.read_text().splitlines()) <= check_sizes.MAX_FILE_LINES
