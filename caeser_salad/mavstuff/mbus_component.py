# this file defines a component that talks to mavlink
# over the mbus

# this uses mav_system tag to talk back to the mav stuff

import asyncio

import pymavlink.dialects.v20.ardupilotmega as mavlink

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff.mbus_messages import *

class MBusComponent:
    def __init__(self, mbus, tag, sysid, compid):
        # create a filter for mavlink messages on the given tag
        self._mbus = mbus
        self._mfilter = mclient.MessageBusFilter(mbus,
            {tag: [MAVMessageToComponent]})

        self._tag = tag
        self._src = (sysid, compid)

        # dictionary of message to set of filters. you can have many filters per
        # message
        self._message_filters = {}
        # stores filterless filters that receive all messages
        self._message_pipes = set()

        # start sending heartbeats from this component
        self._heartbeat_task = asyncio.create_task(self._send_heartbeat())

        # start receiving messages from the bus and handling them
        self._rx_task = asyncio.create_task(self._rx_messages())


    async def _send_heartbeat(self):
        # automatically send the heartbeat message every second
        # to do: send current state
        while True:
            hb = mavlink.MAVLink_heartbeat_message(
                mavlink.MAV_TYPE_ONBOARD_CONTROLLER, 0, 0, 0, 
                mavlink.MAV_STATE_ACTIVE, 3)
            self._send_msg(hb)

            await asyncio.sleep(1)

    async def _rx_messages(self):
        # receive messages from the mbus and put them in the appropriate
        # filter queues
        while True:
            tag, msg = await self._mfilter.recv()
            print("rxd", msg)

            queues = self._message_filters.get(type(msg.msg))
            if queues is not None:
                for queue in queues:
                    queue.put_nowait(msg)
            for queue in self._message_pipes:
                queue.put_nowait(msg)


    def _send_msg(self, msg):
        # pack it up with our source and send it to the message bus
        self._mbus.send(self._tag, MAVMessageFromComponent(msg, self._src))



async def main():
    # test making the camera cause that's easy to see working
    mbus = await mclient.MessageBusClient.create(
        "./socket_mbus_main")

    comp = MBusComponent(mbus, "mav_test", 1, 195)

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
