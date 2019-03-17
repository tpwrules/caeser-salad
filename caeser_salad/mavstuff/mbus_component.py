# this file defines a component that talks to mavlink
# over the mbus

# this uses mav_system tag to talk back to the mav stuff

import asyncio

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff.mbus_messages import *


async def main():
    mbus = await mclient.MessageBusClient.create(
        "./socket_mbus_main")
    mfilter = mclient.MessageBusFilter(mbus,
        {"mav_test": [MAVMessageToComponent]})

    mbus.send("mav_system",
        ChangeDestinationMessage("mav_test", create=True))

    while True:
        tag, msg = await mfilter.recv()
        print("mc got it", msg.msg, msg.src, msg.dest)

if __name__ == "__main__":
    asyncio.run(main())
