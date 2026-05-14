"""Allow ``python -m cdcs_mini`` to run the CLI."""

from cdcs_mini.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
