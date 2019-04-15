# receive sense info and then use them to avoid obstacles

import asyncio
import time

import pymavlink.dialects.v20.ardupilotmega as mavlink

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff import mbus_component

# handle keeping and monitoring params
class ParamKeeper:
    def __init__(self, param_names):
        params = set(param_names)

        # latest value of each param
        self._values = {}

        # events that get set when a parameter changes
        self._events = {}

        # initialize the above
        for param in params:
            self._values[param] = None
            self._events[param] = asyncio.Event()

    def __getattr__(self, name):
        # when obj.x happens, we get asked for "x"
        # the only attributes we support are those in our params
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError("no param {}".format(name)) from None

    def __setattr__(self, name, value):
        if name[0] == "_":
            return super().__setattr__(name, value)

        # when obj.x = y, we get "x" and y
        if name not in self._values:
            raise AttributeError("no param {}".format(name))

        # update the new value of the attribute
        self._values[name] = value

        # wake up everyone that was waiting on it changing
        e = self._events[name]
        e.set()
        # and clear it so any new waiters have to wait for the next change
        e.clear()

    async def wait_for(self, param):
        # wait for the param to be updated and return its new value
        await self._events[param].wait()
        return self._values[param]

    async def wait_until(self, param, cond):
        # wait for new values of param until cond is True
        # returns immediately if it is already true
        # cond is a function that is called with param as its only argument
        val = self._values[param]
        while not cond(val):
            val = await self.wait_for(param)
        return val

# update the param keeper with the new message parameters
async def update_params(msg_filter, pk):
    while True:
        msg = await msg_filter.next_message()
        msg, src, dest = msg.msg, msg.src, msg.dest

        if isinstance(msg, mavlink.MAVLink_vfr_hud_message):
            pk.airspeed = msg.airspeed
            pk.heading = msg.heading
        elif isinstance(msg, mavlink.MAVLink_heartbeat_message):
            if src != (1, 1): continue
            name = mavlink.enums["COPTER_MODE"][msg.custom_mode].name
            pk.mode = name.replace("COPTER_MODE_", "").lower()
            pk.armed = True if msg.base_mode & 128 else False

async def listen_for_hits(mbus, pk):
    mf = mclient.MessageBusFilter(mbus, filters={"saa_collision": (str,)})

    while True:
        tag, msg = await mf.recv()
        pk.collision = msg

# do the sense and avoid task
async def avoid(msg_filter, pk):
    print("sensing")

    while True:
        print(await pk.wait_for("collision"))

async def main():
    # system boot time
    bt = time.monotonic()

    # connect to the message bus so we can send mavlink
    # and receive sense info
    mbus = await mclient.MessageBusClient.create("./socket_mbus_main")

    # create a component on mavlink that we will be talking to the
    # flight controller from
    # we just claim to be a peripheral because we don't have parameters
    component = mbus_component.MBusComponent(mbus, "mav_navigator",
        1, mavlink.MAV_COMP_ID_PERIPHERAL)

    # we don't handle any commands so we don't need to create such a handler

    # but we do handle several messages
    msg_filter = component.create_message_filter((
        # drone speed and heading information
        mavlink.MAVLink_vfr_hud_message,
        # current flight mode
        mavlink.MAVLink_heartbeat_message
    ))

    # ask the drone to send us the data streams with those messages
    component.send_msg(mavlink.MAVLink_request_data_stream_message(
        1, # drone system
        1, # autopilot component,
        mavlink.MAV_DATA_STREAM_EXTRA2,
        5, # 5Hz transmission frequency
        1 # start sending it
    ))

    # create a param keeper so that we can easily act on the message values
    pk = ParamKeeper((
        # from VFR_HUD
        "airspeed",
        "heading",
        # from HEARTBEAT
        "mode",
        "armed",
        # from the sense engine
        "collision"
    ))

    # start a task to keep it running
    pk_task = asyncio.create_task(update_params(msg_filter, pk))

    # start another task to receive collision information
    coll_task = asyncio.create_task(listen_for_hits(mbus, pk))

    while True:
        # wait for the copter to switch to auto mode
        while not pk.armed or pk.mode != "auto":
            await pk.wait_until("mode", lambda m: m == "auto")

        # start a task to do the avoidance
        av_task = asyncio.create_task(avoid(msg_filter, pk))

        while not av_task.done():
            curr_mode = await pk.wait_for("mode")
            # if the copter switches out of auto, brake, or guided mode
            # we need to kill the avoid routine because the pilot
            # is back in control
            if curr_mode not in ("auto", "brake", "guided") or not pk.armed:
                av_task.cancel()

        print("COLLISION PROGRAM ENDING")

        # wait for the task to finish before we start a new one
        try:
            await av_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
