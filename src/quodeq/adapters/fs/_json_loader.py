"""Re-export shim — canonical location is quodeq.data.fs._json_loader."""
from quodeq.data.fs._json_loader import get_json_file, list_json_dir, load_json_file

__all__ = ["get_json_file", "list_json_dir", "load_json_file"]
