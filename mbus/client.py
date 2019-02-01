# this file contains all the logic and classes for Clients to use

import asyncio
import pickle
import traceback

from connector import ConnectionEndedError, BusConnector, MessageAction

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
        self._connector = BusConnector(reader, writer)

        # keep refcount of our subscriptions
        self._subscriptions = {}

        self._ended = False

        # spawn task to handle messages received from the connector
        self._rx_task = asyncio.ensure_future(self._rx_msg_task())

    async def _rx_msg_task(self):
        try:
            while True:
                tag, data = await self._connector.recv()
                self._process(tag, data)            
        except asyncio.CancelledError:
            # let ourselves be cancelled naturally
            # (we will only end up here if _ended is already True)
            raise
        except Exception as e:
            # something went seriously wrong
            if not isinstance(e, ConnectionEndedError):
                traceback.print_exc()
            # force ourselves closed
            # we can't just await on close, because it awaits on us, and there
            # would be a deadlock
            # so note that we ended so the functions stop working
            self._ended = True
            # then schedule a task to call close for us
            asyncio.ensure_future(self.close())

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
        if self._ended:
            raise ConnectionEndedError()

        if not isinstance(tag, str):
            raise ValueError("tag must be string")

        mdata = pickle.dumps(message)

        self._connector.send((MessageAction.SEND, tag), mdata)

    def subscribe(self, tag):
        if self._ended:
            raise ConnectionEndedError()

        if not isinstance(tag, str):
            raise ValueError("tag must be string")

        subscriptions = self._subscriptions.get(tag, 0)
        self._connector.send((MessageAction.SUBSCRIBE, tag), b'')
        self._subscriptions[tag] = subscriptions+1

    def unsubscribe(self, tag):
        if self._ended:
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
        self._ended = True

        # close the connector to be sure we don't receive or send anything more
        # but wait for curent messages to be sent
        await self._connector.flush()
        await self._connector.close()

        # cancel the receive task
        if not self._rx_task.done():
            self._rx_task.cancel()

        # wait for it to cancel and/or eat any exceptions it produced
        try:
            await self._rx_task
        except:
            pass

        # for now we don't have to tell anybody else that we are closing


async def main():
    client = await MessageBusClient.create("./socket_mbus_main")
    client.subscribe("test")
    import random
    x = random.randrange(0, 9999)
    print("sending", x)
    client.send("test", x)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(main())
    loop.run_forever()

