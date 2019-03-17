# this file runs the mavlink stuff for the salad

import asyncio

import router
import destination

async def main():
    # we want to connect to the actual drone first
    reader, writer = await asyncio.open_connection('localhost', 5763)

    # crappily print messages from it
    try:
        dest = destination.StreamDestination(reader, writer)
        while True:
            msg, src = await dest.read_msg()
    finally:
        # theoretically, close things out
        # i don't think much needs to be done here?
        pass

if __name__ == "__main__":
    asyncio.run(main())