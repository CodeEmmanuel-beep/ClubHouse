import asyncio
import nest_asyncio


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
