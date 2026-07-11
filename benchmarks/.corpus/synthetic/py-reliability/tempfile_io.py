def read_config(path: str) -> str:
    handle = open(path)
    data = handle.read()
    return data
