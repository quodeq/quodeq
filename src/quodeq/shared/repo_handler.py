"""Re-export shim — canonical location is quodeq.data.fs.repo_handler."""
from quodeq.data.fs.repo_handler import is_valid_repo_url, prepare_repository

__all__ = ["is_valid_repo_url", "prepare_repository"]
