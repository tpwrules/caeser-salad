import asyncio
import threading

import message

class Actor:
    def __init__(self, listen_ip, listen_port):
        start_event = threading.Event()
        self._thread = threading.Thread(
            target=self._start,
            args=(listen_ip, listen_port, start_event))
        self._thread.start()
        start_event.wait()

    def _start(self, listen_ip, listen_port, start_event):
        # create a new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # start up the task to handle connections from other actors
        self._loop.create_task(
            self._handle_connections(listen_ip, listen_port))

        start_event.set()

        self._loop.run_forever()

    async def _handle_connections(self, listen_ip, listen_port):
        server = await self._loop.create_server(
            lambda: message.MessageRecvProtocol(self),
            listen_ip, listen_port)

        async with server:
            await server.serve_forever()

    def _handle_msg(self, src, msg):
        self._loop.call_soon_threadsafe(self._loop.create_task,
            self.on_receive(src, msg))

    async def on_receive(self, src, msg):
        print("got this: ", msg)



class InterActorHandle:
    def __init__(self, ip, port, orig_actor):
        # we attach to the loop of the actor that created us
        self._orig_actor = orig_actor
        self._loop = self.orig_actor._loop

        self._msg_queue = asyncio.Queue(loop=self._loop)

        # start up the task to connect to the destination actor
        # and send messages from the queue
        self._loop.create_task(
            self._send_messages(ip, port))

    async def _send_messages(self, ip, port):
        while True:
            transport, protocol = await self._loop.create_connection(
                lambda: message.MessageSendProtocol(self._orig_actor),
                ip, port)

            while True:
                msg = await self._msg_queue.get()
                protocol.send_msg(msg)

    def send(self, msg):
        self._msg_queue.put_nowait(msg)

class ActorHandle:
    def __init__(self, ip, port, loop=None):
        if loop is None:
            start_event = threading.Event()
            # create a thread to host an event loop
            self._thread = threading.Thread(
                target=self._start_thread,
                args=(ip, port, start_event))
            self._thread.start()
            start_event.wait()
        else:
            self._thread = None
            self._loop = loop

        self._msg_queue = asyncio.Queue(loop=self._loop)

        self._loop.create_task(self._send_messages(ip, port))

    def _start_thread(self, ip, port, start_event):
        # create a new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        start_event.set()

        self._loop.run_forever()

    async def _send_messages(self, ip, port):
        while True:
            transport, protocol = await self._loop.create_connection(
                lambda: message.MessageSendProtocol(None),
                ip, port)

            while True:
                msg = await self._msg_queue.get()
                protocol.send_msg(msg)

    def send(self, msg):
        self._loop.call_soon_threadsafe(
            self._msg_queue.put_nowait, msg)