# this file contains all the logic and classes for Clients to use

import asyncio
import pickle
import traceback

from connector import ConnectionClosedError, BusConnector, MessageAction

class MessageBusClient:
    @classmethod
    async def create(cls, bus_addr):
        self = MessageBusClient()
        await self._connect(bus_addr)
        return self

    async def _connect(self, bus_addr):
        # called to actually connect to the bus and get the party started
        # this needs to be the first method called

        # connect to the specified bus
        reader, writer = await asyncio.open_unix_connection(bus_addr)

        # create a connector to handle it
        self._connector = BusConnector(reader, writer, self._handle_rx)

        # keep refcount of our subscriptions
        self._subscriptions = {}

        self._closed = False

    def _handle_rx(self, connector, meta, data):
        # the connector is calling us with a new message
        if meta is None and data is None:
            # the connector died and is letting us know
            # we did close
            self._closed = True
            asyncio.ensure_future(self.close())
            return

        try:
            self._process(meta, data)
        except Exception as e:
            traceback.print_exc()

    def _process(self, tag, data):
        try:
            # unpickle the message data
            message = pickle.loads(data)
        except:
            print("MESSAGE UNPICKLE FAILURE")
            print(meta, data)
            traceback.print_exc()

        print("got a message", message)

    def send(self, tag, message):
        if self._closed:
            raise ConnectionClosedError()

        if not isinstance(tag, str):
            raise ValueError("tag must be string")

        mdata = pickle.dumps(message)

        self._connector.send((MessageAction.SEND, tag), mdata)

    def subscribe(self, tag):
        if self._closed:
            raise ConnectionClosedError()

        if not isinstance(tag, str):
            raise ValueError("tag must be string")

        subscriptions = self._subscriptions.get(tag, 0)
        self._connector.send((MessageAction.SUBSCRIBE, tag), b'')
        self._subscriptions[tag] = subscriptions+1

    def unsubscribe(self, tag):
        if self._closed:
            return

        if not isinstance(tag, str):
            raise ValueError("tag must be string")

        subscriptions = self._subscriptions.get(tag)
        if subscriptions is None:
            return
        self._subscriptions[tag] = subscriptions-1

        if subscriptions-1 == 0:
            self._connector.send((MessageAction.UNSUBSCRIBE, tag), b'')

    async def close(self):
        # we are done
        self._closed = True

        # close the connector to be sure we don't receive or send anything more
        # but wait for curent messages to be sent
        await self._connector.flush()
        await self._connector.close()

        # for now we don't have to tell anybody else that we are closing


async def main():
    try:
        client = await MessageBusClient.create("./socket_mbus_main")
        client.subscribe("test")
        import random
        while True:
            x = random.randrange(0, 9999)
            print("sending", x)
            client.send("test", x)
            await asyncio.sleep(5)
    finally:
        print("closing out client")
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

