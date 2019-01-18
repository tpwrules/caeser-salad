import asyncio
import actrix
import sys
import time

serve_port = int(sys.argv[1])


actor = actrix.Actor('0.0.0.0', serve_port)

handle = actrix.ActorHandle('localhost', serve_port)
while True:
    handle.send("hi")
    time.sleep(1)