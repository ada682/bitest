"""
Shared AI request lock.

Karena gateway hanya bisa handle 1 request sekaligus,
semua AI call (analysis + monitor) harus antri via lock ini.

Usage:
    from services.ai_lock import ai_lock

    async with ai_lock:
        resp = await client.post(...)
"""

import asyncio

# Lazy init — asyncio.Lock() harus dibuat di dalam running event loop
_lock: asyncio.Lock | None = None


def ai_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


# Bisa dipakai sebagai context manager langsung:
#   async with ai_lock():  ...
# Atau simpan referensi:
#   lock = ai_lock()
#   async with lock: ...
