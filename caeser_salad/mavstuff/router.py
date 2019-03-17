import asyncio
import traceback

class Router:
    def __init__(self):
        # map of destinations to the task receiving from them
        self._destinations = {}

        # queue of messages that need to be routed by route()
        self._route_q = asyncio.Queue()


    async def route(self):
        while True:
            try:
                msg, from_dest, src = await self._route_q.get()

                # figure out where this message is headed
                dest = [0, 0] # sysid, compid
                if hasattr(msg, "target_system"):
                    dest[0] = msg.target_system
                    if hasattr(msg, "target_component"):
                        dest[1] = msg.target_component

                dest = tuple(dest)

                print("ROUTING {}: {}->{}".format(msg, src, dest))

                # now that we know, try to send it to all our destinations
                for destination in self._destinations.keys():
                    # don't loop back
                    if destination is from_dest:
                        continue
                    was_sent = destination.write_msg(msg, src, dest)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                print("COULDN'T ROUTE MESSAGE")
                traceback.print_exc()


    def add_destination(self, destination):
        # create a task to receive from this destination
        rx_task = asyncio.create_task(self._rx_dest(destination))
        # and save it so we can send messages to that destination
        self._destinations[destination] = rx_task

    async def remove_destination(self, destination):
        # get the task receiving from this destination
        # (and remove it so we don't send to that destination)
        rx_task = self._destinations.pop(destination)
        # cancel it so we don't receive anymore
        rx_task.cancel()
        # wait for it to be fully cancelled
        await rx_task

    async def _rx_dest(self, destination):
        try:
            while True:
                msg, src = await destination.read_msg()
                self._route_q.put_nowait((msg, destination, src))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print("RECEPTION ERROR. THIS DEST IS DYING")
            traceback.print_exc()
