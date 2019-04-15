# this file defines the Connector, which translates from a reader/writer
# to defined messages

import asyncio
import struct
import pickle
import traceback
import sys

from enum import Enum

# raised when send or recv is called but the connection has closed
class ConnectionClosedError(Exception):
    pass

# things to do with the tag in the metadata
class MessageAction(Enum):
    SUBSCRIBE = 1
    UNSUBSCRIBE = 2
    SEND = 3

# how we close down
# closing can start from various sources
# 1a. close() is called
# 1b. receive task raises an exception
# 1c. transmit task raises an exception
# then we begin the process
# 2. _start_close() is called
# 3. if not already created, start_close creates a task which runs
#    _do_close(). this locks out all other functions. if it is already created,
#    _start_close() returns without doing anything
# 4. _do_close() begins running and cancels the tx and rx tasks and waits for
#    them to be cancelled
# 5. _do_close() closes the writer and waits for it to be closed
# 6. _do_close() calls recv_cb(self, None, None) to tell the callback we're done
# 7. _do_close() cleans up memory we don't need anymore
# 8. _do_close() task finished
# 9. close() awaits on the close task, and closing is finished

class BusConnector:
    def __init__(self, reader, writer, recv_cb):
        self._reader = reader
        self._writer = writer
        self._recv_cb = recv_cb

        # this task is created to close down everything
        # if it is not None, then functions raise ConnectionClosedError()
        # or otherwise act as if the connection is closed
        self._close_task = None

        # a simple queue holds the messages to be transmitted
        self._tx_queue = asyncio.Queue()

        # transmission is run in a separate task so the user doesn't have
        # to await for a transmission to complete
        self._tx_task = asyncio.create_task(self._tx_messages())

        # reception reads bytes from the reader and calls the callback
        self._rx_task = asyncio.create_task(self._rx_messages())

    # Receive oriented functions

    async def _rx_messages(self):
        # loop to receive messages and call the callback
        try:
            while True:
                # get 8 bytes of length: one uint32_t for meta, one for data
                lens = await self._reader.readexactly(8)
                metalen, datalen = struct.unpack("<II", lens)

                # read and unpickle the metadata
                metabytes = await self._reader.readexactly(metalen)
                meta = pickle.loads(metabytes)

                # and just read the data bytes
                data = await self._reader.readexactly(datalen)

                # tell the callback about this new message
                try:
                    self._recv_cb(self, meta, data)
                except:
                    pass
        finally:
            # no matter how this loop ends, it ending means the connection
            # should be closed
            self._start_close()

    # Transmit oriented functions

    async def _tx_messages(self):
        # loop to send messages from the queue
        try:
            while True:
                # get a new message from the queue
                # (which has already been pre-pickled)
                metabytes, databytes = await self._tx_queue.get()

                self._writer.write(struct.pack("<II",
                    len(metabytes), len(databytes)))
                self._writer.write(metabytes)
                self._writer.write(databytes)

                await self._writer.drain()
                # message has made it into the pipe at least
                self._tx_queue.task_done()
        finally:
            # no matter how this loop ends, it ending means the connection
            # should be closed
            self._start_close()

            # pretend we finished all the messages in the queue
            # so that flush() doesn't wait forever
            try:
                while True:
                    self._tx_queue.task_done()
            except ValueError: # no more tasks to be done
                pass

    def send(self, meta, data):
        # send a message to the other side of the connector
        if self._close_task is not None:
            raise ConnectionClosedError("can't send: connector is closed")

        # pickle up the metadata so if something goes wrong, it happens now
        metabytes = pickle.dumps(meta)

        # and enqueue it, along with the data
        self._tx_queue.put_nowait((metabytes, data))

    async def flush(self):
        if self._close_task is not None:
            return
        # wait for all messages in the queue to be sent
        await self._tx_queue.join()

    def _start_close(self):
        if self._close_task is None:
            # schedule a task to do the actual closing
            self._close_task = asyncio.create_task(self._do_close())

    async def _do_close(self):
        # cancel the rx and tx tasks
        if not self._tx_task.done():
            self._tx_task.cancel()
        if not self._rx_task.done():
            self._rx_task.cancel()

        # wait for them to cancel and/or print any exception they produced
        try:
            await self._tx_task
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        except:
            print("TX TASK EXCEPTION ON", self, file=sys.stderr)
            traceback.print_exc()

        try:
            await self._rx_task
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError,
                asyncio.IncompleteReadError):
            pass
        except:
            print("RX TASK EXCEPTION ON", self, file=sys.stderr)
            traceback.print_exc()

        # close out the writer so the other end sees us stop now
        self._writer.close()
        await self._writer.wait_closed()

        # tell the callback we are finished
        try:
            self._recv_cb(self, None, None)
        except:
            pass

        # clean up things we won't need anymore
        # probably not exactly necessary
        self._writer = None
        self._tx_task = None
        self._tx_queue = None

        self._reader = None
        self._recv_cb = None

        # and we are finally, totally, closed! no tasks running, no objects
        # lingering, no exceptions waiting, etc.

    async def close(self):
        # start the close process (if it's not already started)
        self._start_close()
        # and wait for it to finish
        await self._close_task