"""Allow ``python -m cdcs`` to run the CLI."""

from cdcs.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
