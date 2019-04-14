# this file runs the mavlink stuff for the salad

import asyncio
import argparse

import serial_asyncio

import caeser_salad.mavstuff.router as mav_router
import caeser_salad.mavstuff.destination as destination
import caeser_salad.mavstuff.route_mbus as route_mbus

import caeser_salad.mbus.client as mclient

mbus_tags = (
    "mav_test", # testing the mbus component
)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Connect the salad to a real MAVLink system.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--host", help="TCP host to connect to")
    group.add_argument("--serial", help="RS232 device name to connect to")
    parser.add_argument("--baud", type=int, default=115200,
        help="RS232 baud rate")
    parser.add_argument("--port", type=int, default=5763,
        help="TCP port")
    return parser.parse_args()

async def main(args):
    # try and connect to the mavlink port
    if args.host is not None: # TCP connection
        reader, writer = await asyncio.open_connection(args.host, args.port)
    else: # can only be a serial connection
        reader, writer = await asyncio.open_serial_connection(
            url=args.serial, baudrate=args.baud)

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
        # create a destination to receive messages from the drone
        drone_dest = destination.StreamDestination(reader, writer)
        router.add_destination(drone_dest)

        # now everything will behave itself and we can just snooze
        while True:
            await asyncio.sleep(1)
    finally:
        # we need to close everything out
        pass

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))