# this file runs the mavlink stuff for the salad

import asyncio

import router
import destination
import route_mbus

async def main():
    try:
        # first, start up the router in its own task
        router = router.Router()
        route_task = asyncio.create_task(router.route())

        # now connect to the message bus
        mbus_manager = \
            mav_mbus.MBusDestinationManager("./socket_mbus_main", router)
        # and start the manager on its own task too
        manage_task = asyncio.create_task(mbus_manager.manage())

        # now that we are conneced to the rest of the system, 
        # connect to the drone
        reader, writer = await asyncio.open_connection('localhost', 5763)
        # it is its own destination, so create one for it
        drone_dest = destination.StreamDestination(reader, writer)
        router.add_destination(drone_dest)

        # now everything will behave itself and we can just snooze
        while True:
            await asyncio.sleep(1)
    finally:
        # theoretically, close things out
        # i don't think much needs to be done here?
        pass

if __name__ == "__main__":
    asyncio.run(main())