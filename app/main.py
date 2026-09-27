"""Compatibility command: every invocation creates one next reel, never posts."""

import asyncio

from scripts.create_next import main

if __name__ == "__main__":
    asyncio.run(main())
