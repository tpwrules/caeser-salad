# this file contains all the logic and classes for Clients to use

import asyncio
import pickle
import traceback

from connector import ConnectionClosedError, BusConnector, MessageAction

# how we close down
# closing can start from various sources
# 1a. close() is called
# 1b. _handle_rx is is called with None cause the connector closed
# then we begin the process
# 2. _start_close() is called
# 3. if not already created, start_close creates a task which runs
#    _do_close(). this locks out all other functions. if it is already created,
#    _start_close() returns without doing anything
# 4. _do_close() begins running and flushes the connector
# 5. _do_close() closes the connector and waits for it to be closed
# 6. _do_close() calls all the callbacks and stuffs all the queues to let them
#    all know we are closed
# 7. _do_close() cleans up memory we don't need anymore
# 8. _do_close() task finished
# 9. close() awaits on the close task, and closing is finished

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

        # this task is created to close down everything
        # if it is not None, then functions raise ConnectionClosedError()
        # or otherwise act as if the connection is closed
        self._close_task = None

        # keep track of our callbacks
        # this is a dictionary whose key is the message tag
        # and whose value is a list of (mtype, callback) tuples
        self._callbacks = {}

    def _handle_rx(self, connector, meta, data):
        # the connector is calling us with a new message
        if meta is None and data is None:
            # the connector died and is letting us know
            # we need to close ourselves in response
            self._start_close()
        else:
            try:
                # the meta is just the tag on reception
                self._process(meta, data)
            except Exception as e:
                traceback.print_exc()

    def _process(self, tag, data):
        try:
            # unpickle the message data
            message = pickle.loads(data)
        except:
            print("MESSAGE UNPICKLE FAILURE")
            print(tag, data)
            traceback.print_exc()

        # call all the callbacks for this tag
        tag_cbs = self._callbacks.get(tag)
        if tag_cbs is not None:
            for mtype, callback in tag_cbs:
                # is there a way to not have to isinstance every time?
                if isinstance(message, mtype):
                    try:
                        callback(tag, message)
                    except:
                        pass

    def send(self, tag, message):
        if self._close_task is not None:
            raise ConnectionClosedError("can't send: connection is closed")

        if not isinstance(tag, str):
            raise ValueError("tag must be string")

        mdata = pickle.dumps(message)

        self._connector.send((MessageAction.SEND, tag), mdata)


    def subscribe(self, tag):
        if self._close_task is not None:
            raise ConnectionClosedError("can't subscribe: connection is closed")

        if not isinstance(tag, str):
            raise ValueError("tag must be string")

        subscriptions = self._subscriptions.get(tag, 0)
        if subscriptions == 0:
            self._connector.send((MessageAction.SUBSCRIBE, tag), b'')
        self._subscriptions[tag] = subscriptions+1

    def unsubscribe(self, tag):
        if self._close_task is not None:
            return

        if not isinstance(tag, str):
            raise ValueError("tag must be string")

        subscriptions = self._subscriptions.get(tag)
        if subscriptions is None:
            return
        self._subscriptions[tag] = subscriptions-1

        if subscriptions-1 == 0:
            self._connector.send((MessageAction.UNSUBSCRIBE, tag), b'')


    def register_cb(self, mtype, callback, tag=None):
        if self._close_task is not None:
            raise ConnectionClosedError(
                "can't register cb: connection is closed")

        tag_cbs = self._callbacks.get(tag)
        if tag_cbs is None:
            tag_cbs = []
            self._callbacks[tag] = tag_cbs

        tag_cbs.append((mtype, callback))

        if tag is not None:
            self.subscribe(tag)

    def unregister_cb(self, mtype, callback, tag=None):
        if self._close_task is not None:
            return

        try:
            tag_cbs = self._callbacks[tag]
        except KeyError:
            raise ValueError("can't unregister cb: no cbs for that tag")

        try:
            tag_cbs.remove((mtype, callback))
        except ValueError:
            raise ValueError(
                "can't unregister cb: that mtype, cb pair was never registered")

        if tag is not None:
            self.unsubscribe(tag)


    def _start_close(self):
        if self._close_task is None:
            # schedule a task to do the actual closing
            self._close_task = asyncio.create_task(self._do_close())

    async def _do_close(self):
        # close the connector to be sure we don't receive or send anything more
        # but wait for curent messages to be sent
        await self._connector.flush()
        await self._connector.close()

        # tell all the callbacks we are closing down
        for tag_cbs in self._callbacks.values():
            for mtype, callback in tag_cbs:
                try:
                    callback(None, None)
                except:
                    pass

        # clean up things we won't need anymore
        # probably not exactly necessary
        self._connector = None
        self._subscriptions = None
        self._callbacks = None

    async def close(self):
        # start the close process (if it's not already started)
        self._start_close()
        # and wait for it to finish
        await self._close_task

def msg_callback(tag, message):
    print("got message", message, "on tag", tag)

async def main():
    try:
        client = await MessageBusClient.create("./socket_mbus_main")
        client.register_cb(object, msg_callback, tag="test")
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

