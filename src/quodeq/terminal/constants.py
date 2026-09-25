"""Terminal session limits shared by the PTY backends and the API socket layer."""
PTY_READ_MAX_BYTES = 65536  # one read() chunk; 64 KiB keeps latency low without starving the socket
PTY_DEFAULT_COLS = 80  # VT100 default width
PTY_DEFAULT_ROWS = 24  # VT100 default height
