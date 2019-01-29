# this file contains all the logic and classes for Clients to use

import asyncio

class MessageBusClient:
    @classmethod
    async def create(cls, bus_addr):
        self = MessageBusClient()
        await self._connect(bus_addr)

    async def _connect(self, bus_addr):
        # called to actually connect to the bus and get the party started
        # this needs to be the first method called

        # connect to the specified bus
        reader, writer = await asyncio.open_unix_connection(bus_addr)

        print(type(reader), type(writer))

async def main():
    client = await MessageBusClient.create("./socket_mbus_main")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(main())
    loop.run_forever()
