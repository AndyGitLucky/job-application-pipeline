"""
Builds the local semantic knowledge store.
"""

from __future__ import annotations

from vector_store import ensure_store


def main() -> None:
    store = ensure_store(force_rebuild=True)
    print(f"provider={store.get('provider')}")
    print(f"items={len(store.get('items', []))}")


if __name__ == "__main__":
    main()
