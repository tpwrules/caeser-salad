# receive sense info and then use them to avoid obstacles

import asyncio
import time
import math

import pymavlink.dialects.v20.ardupilotmega as mavlink

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff import mbus_component

def ang_dist(a, b):
    # https://stackoverflow.com/questions/7570808/
    # how-do-i-calculate-the-difference-of-two-angle-measures/30887154
    x = abs(b-a)%360
    return 360-x if x > 180 else x

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
        elif isinstance(msg, mavlink.MAVLink_attitude_message):
            pk.yaw = msg.yaw
        elif isinstance(msg, mavlink.MAVLink_local_position_ned_message):
            pk.l_north = msg.x
            pk.l_east = msg.y
            pk.l_down = msg.z

async def listen_for_hits(mbus, pk):
    mf = mclient.MessageBusFilter(mbus, filters={"saa_collision": (str,)})

    while True:
        tag, msg = await mf.recv()
        pk.collision = msg

# do the sense and avoid task
async def avoid(msg_filter, pk, component):
    print("sensing")

    while True:
        # wait for a collision to be imminent
        where = await pk.wait_until("collision", lambda c: c != "none")
        # stop the drone!!!!
        component.send_msg(mavlink.MAVLink_set_mode_message(
            1, # drone system
            mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mavlink.COPTER_MODE_BRAKE, # copter's mode
        ))
        print("stopping!!!!")
        await pk.wait_until("airspeed", lambda a: a < 0.1)
        # it overcorrects a little
        await asyncio.sleep(2)
        await pk.wait_until("airspeed", lambda a: a < 0.1)
        print("phew, stopped")

        print("navigating around obstacle")
        component.send_msg(mavlink.MAVLink_set_mode_message(
            1, # drone system
            mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mavlink.COPTER_MODE_GUIDED, # copter's mode
        ))

        angle_step = -15 if where == "right" else 15

        total_step = 0

        heading = pk.heading

        print("looking for opening")
        while await pk.wait_for("collision") != "none":
            heading = (heading + angle_step) % 360
            total_step += abs(angle_step)
            if total_step >= 360:
                print("uhm. can't see a way around it. giving up")
                return
            component.send_msg(mavlink.MAVLink_command_long_message(
                1, # drone system
                1, # autopilot component,
                mavlink.MAV_CMD_CONDITION_YAW, # change heading
                0,
                heading, # new yaw in degrees,
                0, # degrees per second,
                1, # clockwise
                0, # absolute angle
                0, 0, 0 # unused
            ))
            await pk.wait_until("heading", lambda h: ang_dist(h, heading) < 2)
            # wait now to avoid any rotation blurring problems
            await pk.wait_for("collision")
            # next message will have started when the drone was stationary

        print("i see one!!")
        await asyncio.sleep(2)

        # calculate ten meters away at the current heading
        forward = 10
        right = 0
        down = 0
        yaw = await pk.wait_for("yaw")
        print(yaw)
        pos = pk.l_north, pk.l_east, pk.l_down
        new_pos = (forward*math.cos(yaw)-right*math.sin(yaw),
            forward*math.sin(yaw)+right*math.cos(yaw),
            down)
        print(pos, new_pos)

        # and tell the drone to go there
        print("going for it...")
        component.send_msg(
            mavlink.MAVLink_set_position_target_local_ned_message(
                0, # time boot ms
                1, 1, # target drone autopilot,
                mavlink.MAV_FRAME_LOCAL_OFFSET_NED,
                0b0000111111111000, # type_mask (only positions enabled)
                *new_pos,
                0, 0, 0, #xyz velocity, not used,
                0, 0, 0, #xyz acceleration, not used,
                0, 0 # yaw and rate, not used
            ))

        await asyncio.sleep(10)

        print("resuming mission")
        component.send_msg(mavlink.MAVLink_set_mode_message(
            1, # drone system
            mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mavlink.COPTER_MODE_AUTO, # copter's mode
        ))


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
        # attitude message for local flight
        mavlink.MAVLink_attitude_message,
        # position of drone in its local frame
        mavlink.MAVLink_local_position_ned_message,
        # current flight mode
        mavlink.MAVLink_heartbeat_message
    ))

    # ask the drone to send us the data streams with those messages
    component.send_msg(mavlink.MAVLink_request_data_stream_message(
        1, # drone system
        1, # autopilot component,
        mavlink.MAV_DATA_STREAM_POSITION,
        5, # 5Hz transmission frequency
        1 # start sending it
    ))
    component.send_msg(mavlink.MAVLink_request_data_stream_message(
        1, # drone system
        1, # autopilot component,
        mavlink.MAV_DATA_STREAM_EXTRA1,
        5, # 5Hz transmission frequency
        1 # start sending it
    ))
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
        # from ATTITUDE,
        "yaw",
        # from LOCAL_POSITION_NED,
        "l_north",
        "l_east",
        "l_down",
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
        av_task = asyncio.create_task(avoid(msg_filter, pk, component))

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
