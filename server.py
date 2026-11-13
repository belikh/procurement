"""Entry point for `uv run python server.py` and `uv run mcp dev server.py`.

The server lives in the `procurement` package.
"""

from procurement.app import main, mcp

__all__ = ["main", "mcp"]

if __name__ == "__main__":
    main()
