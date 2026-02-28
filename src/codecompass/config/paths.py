import re
from dataclasses import dataclass
from pathlib import Path


def available_versions(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    pattern = re.compile(r"^v\d+$")
    versions = [d.name for d in root.iterdir() if d.is_dir() and pattern.match(d.name)]
    return sorted(versions, key=lambda v: int(v[1:]))


def _default_version(root: Path) -> str:
    versions = available_versions(root)
    return versions[0] if versions else "v1"


@dataclass(frozen=True)
class ConfigPaths:
    root: Path
    version: str
    evaluators_dir: Path
    practices_dir: Path
    dimensions_dir: Path
    prompts_dir: Path
    env_file: Path
    gitignore_file: Path

    @property
    def vroot(self) -> Path:
        return self.root / self.version

    @classmethod
    def from_root(cls, root: Path, version: str | None = None) -> "ConfigPaths":
        v = version or _default_version(root)
        vroot = root / v
        return cls(
            root=root,
            version=v,
            evaluators_dir=vroot / "evaluators",
            practices_dir=vroot / "practices",
            dimensions_dir=vroot / "dimensions",
            prompts_dir=vroot / "prompts",
            env_file=root / ".codecompass.env",
            gitignore_file=root / ".gitignore",
        )


def _looks_like_project_root(root: Path) -> bool:
    for v in available_versions(root):
        vroot = root / v
        if (
            (vroot / "prompts").is_dir()
            and (vroot / "evaluators").is_dir()
            and (vroot / "practices").is_dir()
            and (vroot / "dimensions").is_dir()
        ):
            return True
    return False


def default_paths(version: str | None = None) -> ConfigPaths:
    module_path = Path(__file__).resolve()
    for root in module_path.parent.parents:
        if _looks_like_project_root(root):
            return ConfigPaths.from_root(root, version=version)

    root = module_path.parents[3]
    return ConfigPaths.from_root(root, version=version)
