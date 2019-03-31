# pretend to be a camera and fool QGC

import asyncio
import time

import pymavlink.dialects.v20.ardupilotmega as mavlink

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff import mbus_component

def pad(m, n):
    if len(m) >= n:
        return m[:n]
    else:
        return m + b"\0"*(n-len(m))

async def main():
    bt = time.monotonic()
    # connect to the message bus
    mbus = await mclient.MessageBusClient.create("./socket_mbus_main")

    # create a component that represents the first camera
    component = mbus_component.MBusComponent(mbus, "mav_test",
        1, mavlink.MAV_COMP_ID_CAMERA)

    # register a command handler for all the camera type commands
    cmd_handler = component.create_command_handler((
        mavlink.MAV_CMD_REQUEST_CAMERA_INFORMATION,
        mavlink.MAV_CMD_REQUEST_CAMERA_SETTINGS,
        mavlink.MAV_CMD_REQUEST_STORAGE_INFORMATION,
        mavlink.MAV_CMD_REQUEST_CAMERA_CAPTURE_STATUS,
        mavlink.MAV_CMD_IMAGE_START_CAPTURE,
    ))

    # receive commands and be a camera
    num_imgs = 0
    while True:
        cmd = await cmd_handler.next_command()
        print("asked", cmd.msg)
        cmd_msg, src, dest = cmd.msg, cmd.src, cmd.dest
        cmd_num = cmd_msg.command
        if cmd_num == mavlink.MAV_CMD_REQUEST_CAMERA_INFORMATION:
            # tell the GCS about this camera
            cmd_handler.respond(mavlink.MAV_RESULT_ACCEPTED)
            if cmd_msg.param1 != 1: # don't do it
                continue
            msg = mavlink.MAVLink_camera_information_message(
                time_boot_ms=int((time.monotonic()-bt)*1000),
                vendor_name=pad(b"by Thomas Computer Industries", 32),
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
        elif cmd_num == mavlink.MAV_CMD_REQUEST_CAMERA_SETTINGS:
            cmd_handler.respond(mavlink.MAV_RESULT_ACCEPTED)
            if cmd_msg.param1 != 1: # don't do it
                continue
            msg = mavlink.MAVLink_camera_settings_message(
                time_boot_ms=int((time.monotonic()-bt)*1000),
                mode_id=mavlink.CAMERA_MODE_IMAGE,
            )
            component.send_msg(msg)
        elif cmd_num == mavlink.MAV_CMD_REQUEST_STORAGE_INFORMATION:
            cmd_handler.respond(mavlink.MAV_RESULT_ACCEPTED)
            # todo: parse which from command
            msg = mavlink.MAVLink_storage_information_message(
                time_boot_ms=int((time.monotonic()-bt)*1000),
                storage_id=1,
                storage_count=1,
                status=2,
                # MiB and MiB/s
                total_capacity=65536,
                used_capacity=0,
                available_capacity=65536,
                read_speed=30,
                write_speed=30
            )
            component.send_msg(msg)
        elif cmd_num == mavlink.MAV_CMD_REQUEST_CAMERA_CAPTURE_STATUS:
            cmd_handler.respond(mavlink.MAV_RESULT_ACCEPTED)
            if cmd_msg.param1 != 1: # don't do it
                continue
            msg = mavlink.MAVLink_camera_capture_status_message(
                time_boot_ms=int((time.monotonic()-bt)*1000),
                image_status=0,
                video_status=0,
                image_interval=1,
                recording_time_ms=0,
                available_capacity=65536
            )
            component.send_msg(msg)
        elif cmd_num == mavlink.MAV_CMD_IMAGE_START_CAPTURE:
            print("CAPTURING AN IMAGE!!!")
            cmd_handler.respond(mavlink.MAV_RESULT_ACCEPTED)
            msg = mavlink.MAVLink_camera_image_captured_message(
                time_boot_ms=int((time.monotonic()-bt)*1000),
                time_utc=0,
                camera_id=1,
                lat=5,
                lon=3,
                alt=59,
                relative_alt=50,
                q=[0, 0, 0, 0],
                image_index=num_imgs,
                capture_result=1,
                file_url=b"blah"
            )
            num_imgs += 1
            component.send_msg(msg)

asyncio.run(main())