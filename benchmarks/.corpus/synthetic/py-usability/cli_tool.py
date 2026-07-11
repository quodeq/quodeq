import sys
import traceback


def main() -> int:
    args = sys.argv[1:]
    source = args[0]
    target = args[1]
    try:
        with open(source) as handle:
            data = handle.read()
        with open(target, "w") as handle:
            handle.write(data)
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
