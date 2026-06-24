"""File download endpoint."""
import os

BASE_DIR = "/srv/data"


def handle_download(request):
    # `file` is read from the inbound HTTP request.
    name = request["file"]
    path = os.path.join(BASE_DIR, name)
    with open(path, "rb") as fh:
        return fh.read()
