# this file runs the mavlink stuff for the salad

import asyncio
import sys

import serial_asyncio

import caeser_salad.mavstuff.router as mav_router
import caeser_salad.mavstuff.destination as destination
import caeser_salad.mavstuff.route_mbus as route_mbus

import caeser_salad.mbus.client as mclient

mbus_tags = (
    "mav_test", # testing the mbus component
)

async def main():
    try:
        # first, start up the router in its own task
        router = mav_router.Router()
        route_task = asyncio.create_task(router.route())

        # connect to the message bus
        mbus = await mclient.MessageBusClient.create("./socket_mbus_main")

        # make a destination for each mbus tag
        mbus_destinations = \
            (route_mbus.MBusDestination(tag, mbus) for tag in mbus_tags)
        for the_destination in mbus_destinations:
            router.add_destination(the_destination)

        # now that we are conneced to the rest of the system, 
        # connect to the drone
        #reader, writer = await asyncio.open_connection('141.225.163.227', 5763)
        reader, writer = \
            await serial_asyncio.open_serial_connection(
                url=sys.argv[1], baudrate=115200)
        # it is its own destination, so create one for it
        drone_dest = destination.StreamDestination(reader, writer)
        router.add_destination(drone_dest)

        # now everything will behave itself and we can just snooze
        while True:
            await asyncio.sleep(1)
    finally:
        # we need to close everything out
        pass

if __name__ == "__main__":
    asyncio.run(main())