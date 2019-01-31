# runs the message bus server

import asyncio
import os
import struct
import pickle

# handle a subscriber
class SubscriberHandler:
    def __init__(self, server, reader, writer):
        self.server = server
        self.reader = reader
        self.writer = writer
        self.sendq = asyncio.Queue()
        self.closing = False

        # initialize read buffer
        self.read_blocks = []
        self.read_bytes = 0

        # start task to receive data from client
        self.rx_task = asyncio.ensure_future(self.receive_data())
        # and then task to send data from the queue
        self.tx_task = asyncio.ensure_future(self.send_data())

    async def read_exactly(self, n):
        # read exactly n bytes of data from the reader

        while self.read_bytes < n:
            # read in some new data
            data = await self.reader.read(65536)
            if len(data) == 0: # reader disconnected
                # since we are still in the loop and received no new data,
                # we will never receive enough data to satisfy the request
                # so die now
                raise ConnectionResetError()
            # add it to the read buffer as its own entity
            self.read_blocks.append(data)
            # and note how many bytes are now in the buffer
            self.read_bytes += len(data)

        # we have enough, so join all the blocks together into one big piece
        data = b''.join(self.read_blocks)
        # and split it into what the user wants and what's left over for later
        out = data[:n]
        remaining = data[n:]
        self.read_blocks = [remaining]
        self.read_bytes = len(remaining)

        return out

    def die(self):
        # die because the receive or send loops have ended
        # schedule a task to close them out
        if self.closing is False:
            self.closing = True
            asyncio.ensure_future(self.close())

    async def close(self):
        print("closing", self)
        # we could be in any state
        self.closing = True

        # tell the server to clean us up and stop sending us messages
        self.server.close_subscriber(self)

        # ask the reader and writer tasks to cancel
        if not self.rx_task.done():
            self.rx_task.cancel()
        if not self.tx_task.done():
            self.tx_task.cancel()

        # wait for them to cancel and clean up
        try:
            await self.rx_task
        except:
            pass
        try:
            await self.tx_task
        except:
            pass

        # finally, close off the writer socket
        self.writer.close()

    async def receive_data(self):
        # loop to receive data from the client and forward it on to the server

        try:
            while True:
                # get data length
                dlen_bytes = await self.read_exactly(4)
                dlen, = struct.unpack("<I", dlen_bytes)

                # and then that much data
                data = await self.read_exactly(dlen)

                msg = pickle.loads(data)

                self.server.route(self.sendq, msg)
        except asyncio.CancelledError:
            # let ourselves be cancelled naturally
            raise
        except:
            # otherwise, just end the connection now
            self.die()

    async def send_data(self):
        # loop to send data from the server and forward it to the client

        try:
            while True:
                # get a new message
                msg = await self.sendq.get()

                data = pickle.dumps(msg)

                self.writer.write(struct.pack("<I", len(data)))
                self.writer.write(data)

                await self.writer.drain()
        except asyncio.CancelledError:
            # let ourselves be cancelled naturally
            raise
        except:
            # otherwise, just end the connection now
            self.die()


class MessageBusServer:
    def __init__(self, bus_addr):
        self.bus_addr = bus_addr
        self.subscribers_for_tag = {}
        self.tags_for_subscriber = {}

    async def serve(self):
        self.server = await asyncio.start_unix_server(self.subscriber_connected, 
            path=self.bus_addr)

    def subscriber_connected(self, reader, writer):
        # instantiate a handler for this subscriber
        subscriber = SubscriberHandler(self, reader, writer)
        # it will call us back when it receives a messages
        # remember it so we can tell it to stop
        self.tags_for_subscriber[subscriber] = set()

    async def close(self):
        # close off the server so we don't get any new connections
        self.server.close()
        await self.server.wait_closed()

        # forget all the subscriptions so we don't waste time searching them
        subscribers = self.tags_for_subscriber.keys()
        self.tags_for_subscriber = None
        self.subscribers_for_tag = None

        # close the connection to each subscriber
        for subscriber in subscribers:
            await subscriber.close()

    def close_subscriber(self, subscriber):
        # forget this subscriber entirely

        # busy shutting down
        if self.tags_for_subscriber is None:
            return

        tags = self.tags_for_subscriber[subscriber]
        del self.tags_for_subscriber[subscriber]

        # remove all subscriptions to the tags this subscriber has
        # so that we don't try to send it any more messages
        for tag in tags:
            del self.subscribers_for_tag[tag][subscriber]



if __name__ == "__main__":
    try:
        server = MessageBusServer("./socket_mbus_main")
        loop = asyncio.get_event_loop()
        asyncio.ensure_future(server.serve())
        loop.run_forever()
    finally:
        loop.run_until_complete(server.close())
        if os.path.exists("./socket_mbus_main"):
            os.remove("./socket_mbus_main")