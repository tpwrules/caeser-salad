# send collision messages based on keyboard input

import threading
import sys

from caeser_salad.mbus import client as mclient

direction = "none"
dir_lock = threading.Lock()

def mbus_thread():
    import asyncio
    async def tmain():
        # connect to message bus
        mbus = await mclient.MessageBusClient.create("./socket_mbus_main")

        while True:
            with dir_lock:
                our_dir = direction
            mbus.send("saa_collision", our_dir)
            await asyncio.sleep(0.1)

    asyncio.run(tmain())

mt = threading.Thread(target=mbus_thread, daemon=True)
mt.start()

print("DRONE CRASHER 9000")
print("a: obstacle on left")
print("d: obstacle on right")
print("w: no obstacle")
while True:
    print("Obstacle status: "+direction, end="\r")
    k = sys.stdin.read(1)
    if k == "a":
        nd = "left"
    elif k == "d":
        nd = "right"
    elif k == "w":
        nd = "none"
    else:
        nd = direction
    with dir_lock:
        direction = nd
