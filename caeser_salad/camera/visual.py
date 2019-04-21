# manage the visual camera

import asyncio
import time
import traceback

import pymavlink.dialects.v20.ardupilotmega as mavlink

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff import mbus_component

def pad(m, n):
    if len(m) >= n:
        return m[:n]
    else:
        return m + b"\0"*(n-len(m))

class Handler:
    def __init__(self):
        # things that need to be shut down
        self.mbus = None
        self.comp = None

        self.latest_pos_lock = asyncio.Lock()
        self.latest_pos = None
        self.latest_pos_time = None

        self.pos_rx_task = None
        self.cmd_task = None
        self.cap_state_task = None
        self.capture_task = None

    async def start(self):
        # we start here
        # nothing to be done in init cause it can't be async

        # connect to the message bus
        self.mbus = await mclient.MessageBusClient.create("./socket_mbus_main")

        # create a component that represents this camera
        self.comp = mbus_component.MBusComponent(self.mbus,
            "mav_visual_camera", 1, mavlink.MAV_COMP_ID_CAMERA)

        # create a handler for commands for the camera
        # do it now so we can catch any that build up as we initialize
        cam_cmd_handler = self.comp.create_command_handler((
            mavlink.MAV_CMD_REQUEST_CAMERA_INFORMATION,
            mavlink.MAV_CMD_REQUEST_CAMERA_SETTINGS,
            mavlink.MAV_CMD_REQUEST_STORAGE_INFORMATION,
            mavlink.MAV_CMD_REQUEST_CAMERA_CAPTURE_STATUS,
            mavlink.MAV_CMD_IMAGE_START_CAPTURE,
            mavlink.MAV_CMD_IMAGE_STOP_CAPTURE
        ))

        # tell the autopilot to blast us with position information at 5hz
        # we do that so we can automatically geotag the images and video
        self.comp.send_msg(mavlink.MAVLink_request_data_stream_message(
            1, # drone system
            1, # autopilot component
            mavlink.MAV_DATA_STREAM_POSITION,
            5, # 5Hz transmission frequency
            1 # enable sending
        ))

        # create a filter to handle the position information
        pos_msgs = self.comp.create_message_filter((
            mavlink.MAVLink_global_position_int_message,
        ))

        # wait for the first position from the drone
        pos = (await pos_msgs.next_message()).msg
        # assume these happened at the same time
        self.cam_bt = time.monotonic()
        drone_bt = pos.time_boot_ms/1000
        # and use that to be able to shift drone messages to cam time
        self.drone2cam_time = self.cam_bt-drone_bt

        # make sure the system gets shut down if the task excepts or finishes
        async def c(t):
            try:
                return await t
            finally:
                self.shutdown()


        # start the task to receive the latest position from the drone
        async with self.latest_pos_lock:
            self.latest_pos = pos
            self.latest_pos_time = pos.time_boot_ms+self.drone2cam_time
        self.pos_rx_task = asyncio.create_task(c(self.rx_pos(pos_msgs)))

        # set up the mavlink side of the camera

        # seconds between image captures
        # none if single shot
        self.cap_interval = None
        # if we are actively saving image data. it's kind of unclear how this
        # works in interval mode
        self.capturing = False
        # number of pictures remaining to be captured in interval mode
        self.caps_remaining = 0

        # start the task to handle camera commands
        self.cmd_task = asyncio.create_task(
            c(self.handle_cmds(cam_cmd_handler)))

        self.latest_image = None
        self.latest_image_time = None
        self.new_image_event = asyncio.Event()

        # start the task to handle the mav capture engine
        self.cap_state_task = asyncio.create_task(
            c(self.handle_cap_state()))

        # and finally, the task to receive new images from the camera
        self.capture_task = asyncio.create_task(c(self.do_capture()))


    async def handle_cmds(self, handler):
        bt = self.cam_bt
        num_imgs = 0
        while True:
            cmd = await handler.next_command()
            cmd_msg, src, dest = cmd.msg, cmd.src, cmd.dest
            cmd_num = cmd_msg.command
            if cmd_num == mavlink.MAV_CMD_REQUEST_CAMERA_INFORMATION:
                # tell the GCS about this camera
                handler.respond(mavlink.MAV_RESULT_ACCEPTED)
                if cmd_msg.param1 != 1: # 1 means actually do it
                    continue
                msg = mavlink.MAVLink_camera_information_message(
                    time_boot_ms=int((time.monotonic()-bt)*1000),
                    vendor_name=pad(b"by Thomas Computer Industries", 32),
                    model_name=pad(b"CAESER Salad Visual Camera", 32),
                    firmware_version=0,
                    # i don't actually know what these are but they don't
                    # seem to particularly matter
                    focal_length=100, # mm
                    sensor_size_h=10, # mm
                    sensor_size_v=10, # mm
                    # maximum from the camera. don't seem to matter either
                    resolution_h=4208,
                    resolution_v=3120,
                    lens_id=0,
                    # this camera is really boring and can only
                    # capture images
                    flags=(
                        mavlink.CAMERA_CAP_FLAGS_CAPTURE_IMAGE
                    ),
                    # no camera definition
                    cam_definition_version=0,
                    cam_definition_uri=b""
                )
                self.comp.send_msg(msg)
            elif cmd_num == mavlink.MAV_CMD_REQUEST_CAMERA_SETTINGS:
                handler.respond(mavlink.MAV_RESULT_ACCEPTED)
                if cmd_msg.param1 != 1: # 1 means actually do it
                    continue
                msg = mavlink.MAVLink_camera_settings_message(
                    time_boot_ms=int((time.monotonic()-bt)*1000),
                    # we only have image mode
                    mode_id=mavlink.CAMERA_MODE_IMAGE,
                    # and we don't keep track of zoom or focus
                    zoomLevel=float("nan"),
                    focusLevel=float("nan")
                )
                self.comp.send_msg(msg)
            elif cmd_num == mavlink.MAV_CMD_REQUEST_STORAGE_INFORMATION:
                handler.respond(mavlink.MAV_RESULT_ACCEPTED)
                # just make stuff up, too lazy to deal this moment
                msg = mavlink.MAVLink_storage_information_message(
                    time_boot_ms=int((time.monotonic()-bt)*1000),
                    storage_id=1,
                    storage_count=1,
                    status=2,
                    # MiB and MiB/s
                    total_capacity=65536,
                    used_capacity=0,
                    available_capacity=65536,
                    read_speed=40,
                    write_speed=40
                )
                self.comp.send_msg(msg)
            elif cmd_num == mavlink.MAV_CMD_REQUEST_CAMERA_CAPTURE_STATUS:
                handler.respond(mavlink.MAV_RESULT_ACCEPTED)
                if cmd_msg.param1 != 1: # 1 means actually do it
                    continue

                image_interval = \
                    0 if self.cap_interval is None else self.cap_interval
                if self.cap_interval is None:
                    image_status = 1 if self.capturing else 0
                else:
                    image_status = 3 if self.capturing else 2

                msg = mavlink.MAVLink_camera_capture_status_message(
                    time_boot_ms=int((time.monotonic()-bt)*1000),
                    image_status=image_status,
                    # we don't capture video, so always 0
                    video_status=0,
                    image_interval=image_interval,
                    recording_time_ms=0,
                    available_capacity=65536
                )
                self.comp.send_msg(msg)
            elif cmd_num == mavlink.MAV_CMD_IMAGE_START_CAPTURE:
                handler.respond(mavlink.MAV_RESULT_ACCEPTED)

                if cmd_msg.param3 == 1: # capture just one image
                    self.cap_interval = None
                    self.caps_remaining = 0
                    # set to False when the image is captured
                    self.capturing = True
                else:
                    self.cap_interval = \
                        0.5 if cmd_msg.param2 < 0.5 else cmd_msg.param2
                    self.caps_remaining = \
                        -1 if cmd_msg.param3 < 1 else int(cmd_msg.param3)
                    self.capturing = True
            elif cmd_num == mavlink.MAV_CMD_IMAGE_STOP_CAPTURE:
                handler.respond(mavlink.MAV_RESULT_ACCEPTED)

                self.capturing = False
                self.cap_interval = None
                self.caps_remaining = 0


    async def rx_pos(self, pos_msgs):
        while True:
            # get another position message
            pos = (await pos_msgs.next_message()).msg
            # and store it for the rest of the system
            async with self.latest_pos_lock:
                self.latest_pos = pos
                self.latest_pos_time = pos.time_boot_ms+self.drone2cam_time


    async def handle_cap_state(self):
        def save_capture():
            print("CAPTURING IMAGE!!!!!")
            print("save done!")

        while True:
            # wait until there is a new image
            await self.new_image_event.wait()

            # if capturing got set to True, it was the drone asking us
            # to start capturing
            if self.capturing:
                # if cap_interval is None, this is a single image
                if self.cap_interval is None:
                    # so just capture it now
                    save_capture()
                else:
                    # we are starting a capture interval
                    next_image_time = self.latest_image_time
                # since we saved the capture, we are now idle
                self.capturing = False
            if self.cap_interval is not None:
                # we are capturing an image sequence
                if next_image_time <= self.latest_image_time:
                    # we could set capturing to true and false
                    # but nobody will notice since there is no await
                    save_capture()
                    next_image_time += self.cap_interval
                    # if caps_remaining was negative, this will
                    # go forever, which is precisely what we want
                    self.caps_remaining -= 1
                    if self.caps_remaining == 0:
                        self.cap_interval = None


    async def do_capture(self):
        # for now just put out frames at kind of a random rate
        import random
        while True:
            await asyncio.sleep(random.random()*0.1+0.2)
            # wake everybody waiting up, but make anybody who wasn't waiting
            # wait again
            self.new_image_event.set()
            self.new_image_event.clear()
            self.latest_image = 3
            self.latest_image_time = time.monotonic()


    async def shutdown(self):
        if self.mbus is not None:
            try:
                await self.mbus.close()
            except asyncio.CancelledError:
                pass
            except:
                traceback.print_exc()

        async def end_task(task):
            if task is None: return
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except:
                traceback.print_exc()

        await end_task(self.pos_rx_task)
        await end_task(self.cmd_task)
        await end_task(self.cap_state_task)
        await end_task(self.capture_task)


async def main():
    handler = Handler()
    try:
        await handler.start()
        # handler will handle everything
        while True:
            await asyncio.sleep(1)
    finally:
        await handler.shutdown()

asyncio.run(main())