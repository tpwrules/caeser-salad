# wrap josh's code to send collision messages on the bus

# make sure we can find the realsense libraries
import sys
sys.path.append("/usr/local/lib")

import asyncio

from caeser_salad.mbus import client as mclient

from caeser_salad.saa import criticalPointOptimized as cp

async def main():
    mbus = await mclient.MessageBusClient.create("./socket_mbus_main")

    def status(collision):
        if collision == "left":
            mbus.send("saa_collision", "left")
        elif collision == "right":
            mbus.send("saa_collision", "right")
        elif collision == "okay":
            mbus.send("saa_collision", "none")

    # contrary to its name, calling this function starts off everything
    await cp.init_Camera(status)

asyncio.run(main())