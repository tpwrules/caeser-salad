# capture images from the visual camera and write them to disk

import asyncio
import subprocess
import time

async def main():
    global ffmpeg
    print("spawning ffmpeg")
    ffmpeg = subprocess.Popen(args=(
        "ffmpeg",
        "-hide_banner", "-loglevel", "error", # nothing on stderr, please
        "-f", "v4l2", # capture from camera with video4linux2
        "-input_format", "mjpeg", # let the camera encode JPEGs
        "-framerate", "20", # minimum framerate
        "-video_size", "4208x3120", # maximum image size
        "-i", "/dev/video0", # the visual camera. is this always video0?
        "-f", "image2pipe", # dump frames to output
        "-vcodec", "copy", # don't reencode them (they come out as JPEGs)
        "-"), # output file is stdout
        stdout=subprocess.PIPE, # capture the stdout from python
        bufsize=0) # don't buffer it so we get frames as they are captured

    print("cool.")

    boottime = time.monotonic()

    # capture frames
    databuf = bytearray()
    ii = 0
    nexttime = 1
    while True:
        # search for start of image marker (\xFF\xD8)
        try:
            soi = databuf.index(b'\xFF\xD8')
        except ValueError:
            # maybe we split the marker, so don't throw away the first byte
            if len(databuf) > 0 and databuf[-1] == 0xFF:
                # is it more efficient to create a new bytearray?
                databuf = databuf[-1:]
            else:
                databuf = bytearray()
            rb = ffmpeg.stdout.read(2*1024*1024)
            if len(rb) == 0:
                raise Exception("ffmpeg died?")
            databuf.extend(rb)
            continue

        # declare that the image was captured when we find its SOI
        imagetime = time.monotonic()-boottime

        # search only the new part of the buffer for the EOI
        lastsize = soi+2

        # search for end of image marker (\xFF\xD9)
        while True:
            try:
                eoi = databuf.index(b'\xFF\xD9', lastsize)
                break
            except ValueError:
                lastsize = len(databuf)
                rb = ffmpeg.stdout.read(2*1024*1024)
                if len(rb) == 0:
                    raise Exception("ffmpeg died?")
                databuf.extend(rb)

        imagedata, databuf = databuf[soi:eoi+2], databuf[eoi+2:]

        lastsize = 0

        # capture about one image per second
        if imagetime >= nexttime:
            print(imagetime)
            nexttime += 1
            f = open("/home/pilot/m/test_dir/image_{:03d}_{}ms.jpg".format(
                ii, int(imagetime*1000)), "wb")
            f.write(imagedata)
            f.close()
            ii += 1

try:
    asyncio.run(main())
finally:
    ffmpeg.kill()
    ffmpeg.communicate()
