"""Separate DuckDB foundation entry point; legacy SQLite builder is preserved."""
from src.warehouse.core import main

if __name__ == "__main__":
    raise SystemExit(main("build"))
