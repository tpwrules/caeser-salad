# this file manages all the message bus connections for the MAVlink router

import asyncio

import caeser_salad.mavstuff.destination as destination

from caeser_salad.mavstuff.mbus_component import MAVSystemMessage, \
    ChangeDestinationMessage, \
    MAVMessageToComponent, MAVMessageFromComponent

from caeser_salad.mbus import client as mclient

import sys
sys.modules["__main__"].ChangeDestinationMessage = ChangeDestinationMessage
sys.modules["__main__"].MAVMessageFromComponent = MAVMessageFromComponent

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
            {tag, [MAVMessageFromComponent]})


    async def _get_msg(self):
        bus_msg = await self.mfilter.recv()
        return bus_msg.msg, bus_msg.src

    def _put_msg(self, msg, src, dest):
        # send the message along the bus
        self.mbus.send(self.tag,
            MAVMessageToComponent(msg, src, dest))


# manage destinations for the message bus
# this thing's job is to add and remove destinations in response to messages
# on the mav_system tag
class MBusDestinationManager:
    def __init__(self, router):
        self.router = router

        # dictionary from tags to destinations
        self._destinations = {}

    async def manage(self, bus_addr):
        mbus = await mclient.MessageBusClient.create(bus_addr)

        mfilter = mclient.MessageBusFilter(mbus, 
            {"mav_system": [MAVSystemMessage]})

        while True:
            try:
                msg = await mfilter.recv()
                print(msg)
                if isinstance(msg, ChangeDestinationMessage):
                    if msg.create:
                        print("NEW mbus dest", msg.tag)
                        # allocate a new destination
                        destination = MBusDestination(msg.tag, mbus)
                        self.router.add_destination(destination)
                        self._destinations[msg.tag] = destination
                    else:
                        # destroy an existing destination
                        destination = self._destinations.pop(msg.tag)
                        await self.router.remove_destination(destination)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print("MANAGE MSG FAILED")
                traceback.print_exc()
