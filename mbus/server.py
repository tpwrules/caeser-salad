# runs the message bus server

import asyncio
import os
import traceback

from connector import ConnectionEndedError, BusConnector, MessageAction

class MessageBusServer:
    def __init__(self, bus_addr):
        self.bus_addr = bus_addr
        self.connectors_for_tag = {}
        self.connectors = set()

    async def serve(self):
        self.server = await asyncio.start_unix_server(self.subscriber_connected, 
            path=self.bus_addr)

    def subscriber_connected(self, reader, writer):
        # instantiate a connector to manage this subscriber
        connector = BusConnector(reader, writer)
        # create a task to receive messages from this connector
        asyncio.ensure_future(self.rx_messages(connector))
        # it will die when the connector dies, so we don't need to
        # keep it around

        self.connectors.add(connector)

    async def close(self):
        # close off the server so we don't get any new connections
        self.server.close()
        await self.server.wait_closed()

        connectors = self.connectors

        # forget all the subscriptions so we don't waste time searching them
        # or unexpectedly route messages while half-closed
        self.connectors_for_tag = None
        self.connectors = None

        # close all our connectors
        for connector in connectors:
            await connector.close()
            # closing the connector will cause it to raise
            # a ConnectionEndedError in recv()
            # which will stop the rx task

    def forget_connector(self, connector):
        # forget this connector entirely

        # busy shutting down
        if self.connectors is None:
            return

        # if this is called, the connector has already closed itself
        # so all we need to do is forget that it existed

        try:
            self.connectors.remove(connector)
        except KeyError:
            # this connector doesn't exist anymore
            # so don't bother removing it from connectors_for_tag
            return

        # find and remove this connector from any tags
        for tag_connectors in self.connectors_for_tag.values():
            try:
                tag_connectors.remove(connector)
            except KeyError:
                pass

    async def rx_messages(self, connector):
        # task to receive and process messages from a particular connector
        try:
            while True:
                meta, data = await connector.recv()
                self.route(connector, meta, data)
        except ConnectionEndedError:
            # expected cause of death
            pass
        except Exception as e:
            # just print the exception so this task can die in peace
            traceback.print_exc()
            # and make sure the connector is closed, no matter the error
            await connector.close()
        finally:
            # make sure this connector is forgotten
            # this may double forget it, but that's safe
            self.forget_connector(connector)

    def route(self, connector, meta, data):
        # the first element of meta is an action to do with the tag
        # and the second is the tag as a string

        # we don't care what's in the data bytes
        action, tag = meta

        if action == MessageAction.SEND:
            # figure out who is interested in this message
            c_set = self.connectors_for_tag.get(tag)
            if c_set is None:
                # nobody, apparently
                return
            # and send the message to all of em
            # copy the set so if we need to forget a connection we can do it
            # without changing the set we're iterating over
            for dest_connector in c_set.copy():
                # don't loop back
                if dest_connector is connector: continue
                # the metadata is just the tag name
                try:
                    dest_connector.send(tag, data)
                except ConnectionEndedError:
                    # oops, the connector is closed
                    self.forget_connector(connector)
        elif action == MessageAction.SUBSCRIBE:
            # add this connector to the set of connectors for this tag
            # so that it will receive future messages
            c_set = self.connectors_for_tag.get(tag)
            if c_set is None:
                # nobody's subscribed to this tag yet, so create a set
                c_set = set()
                self.connectors_for_tag[tag] = c_set
            c_set.add(connector)
        elif action == MessageAction.UNSUBSCRIBE:
            try:
                self.connectors_for_tag[tag].remove(connector)
            except KeyError:
                pass


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