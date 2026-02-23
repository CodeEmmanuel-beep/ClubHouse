from app.core.async_config import get
import asyncio


async def main():
    await get()
    print("database connected")


if __name__ == "__main__":
    asyncio.run(main())
