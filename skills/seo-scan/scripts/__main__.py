"""Enable ``python -m narwhal …`` for the installed package."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
