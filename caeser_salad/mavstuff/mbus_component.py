# this file defines a component that talks to mavlink
# over the mbus

# this uses mav_system tag to talk back to the mav stuff

import asyncio

import pymavlink.dialects.v20.ardupilotmega as mavlink

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff.mbus_messages import *

class ComponentMessageFilter:
    def __init__(self, filter_q):
        # queue of filtered messages
        self._filter_q = filter_q

    async def next_message(self):
        return await self._filter_q.get()

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


    def create_message_filter(self, msgs=None):
        # if not None, messages is an iterable of mavlink messages to filter for
        # i.e. they are subclasses of mavlink.MAVLink_message

        msgs_to_filter = None
        if msgs is not None:
            msgs_to_filter = set()
            for candidate in msgs:
                if not issubclass(candidate, mavlink.MAVLink_message):
                    raise ValueError(("{} is not a subclass of "+
                        "mavlink.MAVLink_message").format(candidate))
                msgs_to_filter.add(candidate)

        filter_q = asyncio.Queue()
        if msgs_to_filter is not None:
            for msg_to_filter in msgs_to_filter:
                filters_on_msg = self._message_filters.get(msg_to_filter)
                if filters_on_msg is None:
                    filters_on_msg = set()
                    self._message_filters[msg_to_filter] = filters_on_msg
                filters_on_msg.add(filter_q)
        else:
            self._message_pipes.add(filter_q)

        return ComponentMessageFilter(filter_q)


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

    f = comp.create_message_filter((mavlink.MAVLink_heartbeat_message,))

    while True:
        print(await f.next_message())

if __name__ == "__main__":
    asyncio.run(main())
