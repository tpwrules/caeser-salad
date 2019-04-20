# dump collision messages to stdout so the status can be observed

import asyncio

from caeser_salad.mbus import client as mclient

async def main():
    mbus = await mclient.MessageBusClient.create("./socket_mbus_main")
    mf = mclient.MessageBusFilter(mbus,
        filters={"saa_collision": (str,)})

    while True:
        tag, direction = await mf.recv()
        print("  Colliding: {}    ".format(direction), end="\r")

asyncio.run(main())