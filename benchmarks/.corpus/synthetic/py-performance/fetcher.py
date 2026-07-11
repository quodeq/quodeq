import asyncio


async def fetch_one(name: str) -> str:
    await asyncio.sleep(0.1)
    return name


async def fetch_all() -> list[str]:
    first = await fetch_one("alpha")
    second = await fetch_one("beta")
    third = await fetch_one("gamma")
    return [first, second, third]


async def read_snapshot(path: str) -> str:
    with open(path) as handle:
        return handle.read()
