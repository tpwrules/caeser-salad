# runs the message bus server

import asyncio
import os
import traceback
import sys

from .connector import ConnectionClosedError, BusConnector, MessageAction

class MessageBusServer:
    def __init__(self, bus_addr):
        self.bus_addr = bus_addr
        self.connectors_for_tag = {}
        self.connectors = set()

    async def serve(self):
        self.server = await asyncio.start_unix_server(
            self.subscriber_connected, 
            path=self.bus_addr)

    def subscriber_connected(self, reader, writer):
        # instantiate a connector to manage this subscriber
        connector = BusConnector(reader, writer, self.handle_rx)
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

    def forget_connector(self, connector):
        # if this is called, the connector has already closed itself
        # so all we need to do is forget that it existed

        # busy shutting down so it's already forgotten
        if self.connectors is None:
            return

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

    def handle_rx(self, connector, meta, data):
        # receive one message from the connector
        if meta is None and data is None:
            # the connector has closed, so forget it
            self.forget_connector(connector)
        else:
            # otherwise, try to route the message
            try:
                self.route(connector, meta, data)
            except Exception as e:
                print("ROUTE FAILURE", file=sys.stderr)
                print(connector, meta, data, file=sys.stderr)
                traceback.print_exc()

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
                except ConnectionClosedError:
                    # oops, the connector is closed
                    self.forget_connector(dest_connector)
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


async def main():
    try:
        server = MessageBusServer("./socket_mbus_main")
        await server.serve()
        # server will do everything
        while True:
            await asyncio.sleep(1)
    finally:
        await server.close()
        if os.path.exists("./socket_mbus_main"):
            os.remove("./socket_mbus_main")   

if __name__ == "__main__":
    asyncio.run(main())