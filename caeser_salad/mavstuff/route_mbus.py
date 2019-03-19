# this file manages all the message bus connections for the MAVlink router

import asyncio
import traceback

import caeser_salad.mavstuff.destination as destination

from caeser_salad.mavstuff.mbus_messages import *

from caeser_salad.mbus import client as mclient

# act as a destination for components on the message bus
class MBusDestination(destination.Destination):
    def __init__(self, tag, mbus):
        super().__init__()

        # tag that we send messages to
        self.tag = tag
        # and the bus we send them on
        self.mbus = mbus

        # create a filter to only get messages "from" this destination
        # we can't receive all of them in one destination because then
        # we can't route
        self.mfilter = mclient.MessageBusFilter(mbus, 
            {tag: [MAVMessageFromComponent]})


    async def _get_msg(self):
        tag, bus_msg = await self.mfilter.recv()
        return bus_msg.msg, bus_msg.src

    def _put_msg(self, msg, src, dest):
        # send the message along the bus
        self.mbus.send(self.tag,
            MAVMessageToComponent(msg, src, dest))

