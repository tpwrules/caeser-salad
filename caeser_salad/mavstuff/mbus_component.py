# this file defines a component that talks to mavlink
# over the mbus

# this uses mav_system tag to talk back to the mav stuff

import asyncio

from caeser_salad.mbus import client as mclient
from caeser_salad.mbus.message import Message

class MAVSystemMessage(Message):
    pass

class ChangeDestinationMessage(MAVSystemMessage):
    def __init__(self, tag, create):
        # change the destination on the given tag
        # if create = True, create it
        # otherwise, destroy it
        self.tag = tag
        self.create = create

class MAVMessageToComponent(Message):
    def __init__(self, msg, src, dest):
        self.msg = msg
        self.src = src
        self.dest = dest

class MAVMessageFromComponent(Message):
    def __init__(self, msg, src):
        self.msg = msg
        self.src = src

async def main():
    mbus = await mclient.MessageBusClient.create(
        "./socket_mbus_main")
    mfilter = mclient.MessageBusFilter(mbus,
        {"mav_test": [object]})

    mbus.send("mav_system",
        ChangeDestinationMessage("mav_test", create=True))

    while True:
        tag, msg = await mfilter.recv()
        print("mc got it", msg.msg, msg.src, msg.dest)

if __name__ == "__main__":
    asyncio.run(main())
