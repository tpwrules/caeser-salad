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

class ComponentCommandHandler:
    def __init__(self, cmd_q, component):
        self._cmd_q = cmd_q
        self._component = component
        self._last_cmd = None

    async def next_command(self):
        # todo: figure out how to handle confirmation number
        if self._last_cmd is not None:
            raise RuntimeError("last command was never responded to")
        self._last_cmd = await self._cmd_q.get()
        return self._last_cmd

    def respond(self, result):
        if result not in mavlink.enums["MAV_RESULT"]:
            raise ValueError("{} is not a MAV_RESULT".format(result))
        if self._last_cmd is None:
            raise RuntimeError("last command was already responded to")
        self._component.send_msg(mavlink.MAVLink_command_ack_message(
            self._last_cmd.msg.command, result, 0, 0, *self._last_cmd.src))
        self._last_cmd = None


class MBusComponent:
    def __init__(self, mbus, tag, sysid, compid):
        # create a filter for mavlink messages on the given tag
        self._mbus = mbus
        self._mfilter = mclient.MessageBusFilter(mbus,
            {tag: [MAVMessageToComponent]})

        self._tag = tag
        self._src = (sysid, compid)

        # dictionary of message to set of queues that go to filters.
        # you can have many filters per message
        self._message_filters = {}
        # stores filterless filters that receive all messages
        self._message_pipes = set()

        # dictionary of command ID (in the MAV_CMD enum) to queues that go to
        # command handlers
        # you can only have one command handler per command
        self._command_handlers = {}

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


    def create_command_handler(self, cmds=None):
        # cmds is an iterable of mavlink commands to filter for
        # they must be in the MAV_CMD enum

        cmds_to_filter = set()
        for cmd in cmds:
            # make sure this is a valid command number
            if cmd not in mavlink.enums["MAV_CMD"]:
                raise ValueError("{} is not a MAV_CMD".format(cmd))
            # make sure there isn't a handler for this command already
            if cmd in self._command_handlers:
                raise ValueError("MAV_CMD {} already has a handler".format(cmd))
            cmds_to_filter.add(cmd)

        cmd_q = asyncio.Queue()
        for cmd in cmds_to_filter:
            self._command_handlers[cmd] = cmd_q

        return ComponentCommandHandler(cmd_q, self)

    async def _send_heartbeat(self):
        # automatically send the heartbeat message every second
        # to do: send current state
        while True:
            hb = mavlink.MAVLink_heartbeat_message(
                mavlink.MAV_TYPE_CAMERA, 0, 0, 0, 
                mavlink.MAV_STATE_ACTIVE, 3)
            self.send_msg(hb)

            await asyncio.sleep(1)

    async def _rx_messages(self):
        # receive messages from the mbus and put them in the appropriate
        # filter queues
        while True:
            tag, msg = await self._mfilter.recv()

            # this message is a command to do something
            if isinstance(msg.msg, mavlink.MAVLink_command_long_message):
                # so tell the appropriate command handler
                handler_q = self._command_handlers.get(msg.msg.command)
                if handler_q is not None:
                    handler_q.put_nowait(msg)
            else: # it's just a normal message. tell message filters
                queues = self._message_filters.get(type(msg.msg))
                if queues is not None:
                    for queue in queues:
                        queue.put_nowait(msg)
                for queue in self._message_pipes:
                    queue.put_nowait(msg)


    def send_msg(self, msg):
        # pack it up with our source and send it to the message bus
        self._mbus.send(self._tag, MAVMessageFromComponent(msg, self._src))



async def main():
    # test making the camera cause that's easy to see working
    mbus = await mclient.MessageBusClient.create(
        "./socket_mbus_main")

    comp = MBusComponent(mbus, "mav_test", 1, 195)

    c = comp.create_command_handler((
        mavlink.MAV_CMD_REQUEST_CAMERA_INFORMATION,))

    while True:
        print(await c.next_command())
        c.respond(mavlink.MAV_RESULT_UNSUPPORTED)

if __name__ == "__main__":
    asyncio.run(main())
