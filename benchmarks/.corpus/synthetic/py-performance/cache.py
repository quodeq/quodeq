import asyncio


async def fetch_many(names: list[str]) -> list[str]:
    from fetcher import fetch_one

    return list(await asyncio.gather(*(fetch_one(n) for n in names)))
