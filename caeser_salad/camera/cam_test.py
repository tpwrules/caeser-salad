# pretend to be a camera and fool QGC

import asyncio

import pymavlink.dialects.v20.ardupilotmega as mavlink

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff import mbus_component

def pad(m, n):
    if len(m) >= n:
        return m[:n]
    else:
        return m + b"\0"*(n-len(m))

async def main():
    # connect to the message bus
    mbus = await mclient.MessageBusClient.create("./socket_mbus_main")

    # create a component that represents the first camera
    component = mbus_component.MBusComponent(mbus, "mav_test",
        1, mavlink.MAV_COMP_ID_CAMERA)

    # register a command handler for all the camera type commands
    cmd_handler = component.create_command_handler((
        mavlink.MAV_CMD_REQUEST_CAMERA_INFORMATION,
    ))

    # receive commands and be a camera
    while True:
        cmd = await cmd_handler.next_command()
        cmd_msg, src, dest = cmd.msg, cmd.src, cmd.dest
        cmd_num = cmd_msg.command
        if cmd_num == mavlink.MAV_CMD_REQUEST_CAMERA_INFORMATION:
            # tell the GCS about this camera
            cmd_handler.respond(mavlink.MAV_RESULT_ACCEPTED)
            msg = mavlink.MAVLink_camera_information_message(
                time_boot_ms=100,
                vendor_name=pad(b"Thomas Computer Industries", 32),
                model_name=pad(b"Caeser Salad Visual Camera", 32),
                firmware_version=0,
                focal_length=100, # mm
                sensor_size_h=10, # mm
                sensor_size_v=10, # mm
                resolution_h=1920,
                resolution_v=1080,
                lens_id=0,
                flags=(
                    mavlink.CAMERA_CAP_FLAGS_CAPTURE_VIDEO |
                    mavlink.CAMERA_CAP_FLAGS_CAPTURE_IMAGE
                ),
                cam_definition_version=0,
                cam_definition_uri=b""
            )
            component.send_msg(msg)

asyncio.run(main())