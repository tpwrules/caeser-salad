# receive sense info and then use them to avoid obstacles

import asyncio
import time

import pymavlink.dialects.v20.ardupilotmega as mavlink

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff import mbus_component

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

    # for now, just print them out to make sure it's working
    while True:
        msg = await msg_filter.next_message()
        msg, src, dest = msg.msg, msg.src, msg.dest
        print(msg, src)

if __name__ == "__main__":
    asyncio.run(main())
