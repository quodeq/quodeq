from pathlib import Path

from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer


class _Backend:
    def __init__(self):
        self.puts = []

    def get(self, key):
        return None

    def put(self, key, entry):
        self.puts.append(key)


def test_writer_uses_injected_backend(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n")
    backend = _Backend()
    roots = []

    def factory(root):
        roots.append(root)
        return backend

    spec = CacheWriterSpec(
        cache_root=tmp_path / "cache", src_root=src, standards_dir=None, prompts_dir=None,
        dimension="clean-architecture", model_id="m", language="python",
        backend_factory=factory,
    )
    build_cache_writer(spec)("a.py", [])
    assert roots == [tmp_path / "cache"]
    assert len(backend.puts) == 1
