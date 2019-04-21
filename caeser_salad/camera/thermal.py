# manage the visual camera

import asyncio
import datetime
import time
import traceback
import pathlib

import threading
import queue
import subprocess

import pymavlink.dialects.v20.ardupilotmega as mavlink

from caeser_salad.mbus import client as mclient
from caeser_salad.mavstuff import mbus_component

import piexif

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

        self.cmd_task = None

        self._shutdown_task = None

    async def start(self):
        # we start here
        # nothing to be done in init cause it can't be async

        self.cam_bt = time.monotonic()

        # connect to the message bus
        self.mbus = await mclient.MessageBusClient.create("./socket_mbus_main")

        # create a component that represents this camera
        self.comp = mbus_component.MBusComponent(self.mbus,
            "mav_thermal_camera", 1, mavlink.MAV_COMP_ID_CAMERA2)

        # create a handler for commands for the camera
        # do it now so we can catch any that build up as we initialize
        cam_cmd_handler = self.comp.create_command_handler((
            mavlink.MAV_CMD_REQUEST_CAMERA_INFORMATION,
            mavlink.MAV_CMD_REQUEST_CAMERA_SETTINGS,
            mavlink.MAV_CMD_REQUEST_STORAGE_INFORMATION,
            mavlink.MAV_CMD_REQUEST_CAMERA_CAPTURE_STATUS,
            mavlink.MAV_CMD_VIDEO_START_CAPTURE,
            mavlink.MAV_CMD_VIDEO_STOP_CAPTURE
        ))

        # make sure the system gets shut down if the task excepts or finishes
        async def c(t):
            try:
                return await t
            finally:
                self._start_shutdown()

        # set up the mavlink side of the camera
        self.recording = False
        self.record_process = None
        self.record_time = 0

        # start the task to handle camera commands
        self.cmd_task = asyncio.create_task(
            c(self.handle_cmds(cam_cmd_handler)))


    async def handle_cmds(self, handler):
        bt = self.cam_bt
        print("c wait")
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
                    model_name=pad(b"CAESER Salad Thermal Camera", 32),
                    firmware_version=0,
                    # i don't actually know what these are but they don't
                    # seem to particularly matter
                    focal_length=100, # mm
                    sensor_size_h=10, # mm
                    sensor_size_v=10, # mm
                    # maximum from the camera. don't seem to matter either
                    resolution_h=1280,
                    resolution_v=720,
                    lens_id=0,
                    # this camera is really boring and can only
                    # capture images
                    flags=(
                        mavlink.CAMERA_CAP_FLAGS_CAPTURE_VIDEO
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
                    # we only have video mode
                    mode_id=mavlink.CAMERA_MODE_VIDEO,
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
                if self.recording is False:
                    rt = 0
                else:
                    rt = time.monotonic()-self.record_start
                msg = mavlink.MAVLink_camera_capture_status_message(
                    time_boot_ms=int((time.monotonic()-bt)*1000),
                    # we don't capture images, so always 0
                    image_status=0,
                    video_status=1 if self.recording else 0,
                    image_interval=0,
                    recording_time_ms=int(rt*1000),
                    available_capacity=65536
                )
                self.comp.send_msg(msg)
            elif cmd_num == mavlink.MAV_CMD_VIDEO_START_CAPTURE:
                handler.respond(mavlink.MAV_RESULT_ACCEPTED)
                # capture status message frequency
                print(cmd_msg.param2)

                await self.start_recording()
            elif cmd_num == mavlink.MAV_CMD_VIDEO_STOP_CAPTURE:
                handler.respond(mavlink.MAV_RESULT_ACCEPTED)
                await self.stop_recording()


    async def start_recording(self):
        data_base_dir = pathlib.Path("/home/pilot/data_drive")
        if not (data_base_dir/".is_mounted").exists():
            raise Exception("data drive not mounted?")

        self.recording = True

        start_time = datetime.datetime.now()
        video_name = start_time.strftime("THERMAL_%Y%m%d_%H%M%S.mpg")

        self.record_start = time.monotonic()

        self.record_process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner", "-loglevel", "error", # no output please
            "-f", "v4l2", # capture from camera with video4linux2
            "-input_format", "mjpeg", # let the camera encode JPEGs
            "-framerate", "30",
            "-video_size", "1280x720",
            "-i", "/dev/video1", # the thermal camera. is this always video1?
            "-f", "avi", # write frames to avi file
            "-vcodec", "copy", # don't reencode them (they come out as JPEGs)
            str(data_base_dir/video_name),
            stdin=asyncio.subprocess.DEVNULL,
        )


    async def stop_recording(self):
        self.recording = False
        if self.record_process is not None:
            if self.record_process.returncode is not None:
                self.record_process.send_signal(asyncio.subprocess.SIGINT)
                await self.record_process.communicate()
            self.record_process = None


    async def shutdown(self):
        self._start_shutdown()
        await self._shutdown_task

    def _start_shutdown(self):
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(self._do_shutdown())

    async def _do_shutdown(self):
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

        await end_task(self.cmd_task)
        await self.stop_recording()


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