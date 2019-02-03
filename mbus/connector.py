# this file defines the Connector, which translates from a reader/writer
# to defined messages

import asyncio
import struct
import pickle

from enum import Enum

# raised when send or recv is called but the connection has closed
class ConnectionClosedError(Exception):
    pass

# things to do with the tag in the metadata
class MessageAction(Enum):
    SUBSCRIBE = 1
    UNSUBSCRIBE = 2
    SEND = 3

class BusConnector:
    def __init__(self, reader, writer, recv_cb):
        self._reader = reader
        self._writer = writer
        self._recv_cb = recv_cb

        self._closed = False

        # we have a list of chunks to hold received bytes
        # this approach lets us avoid joining everything until we know we
        # have enough
        self._rx_chunks = []
        self._rx_bytes = 0 # how many bytes our chunks total to

        # a simple queue holds the messages to be transmitted
        self._tx_queue = asyncio.Queue()

        # transmission is run in a separate task so the user doesn't have
        # to await for a transmission to complete
        self._tx_task = asyncio.ensure_future(self._tx_messages())

        # we also need a task to handle received messages and call the user's
        # callback
        self._rx_task = asyncio.ensure_future(self._rx_messages())

    # Receive oriented functions

    async def _read_exactly(self, n):
        # read exactly n bytes of data from the reader

        if n == 0:
            return b''

        while self._rx_bytes < n:
            data = await self._reader.read(65536)

            if len(data) == 0: # reader was disconnected
                # we will never have enough bytes cause this loop will add 0
                # so just die now
                raise ConnectionResetError()

            self._rx_chunks.append(data)
            self._rx_bytes += len(data)

        # we have enough so join the chunks together into one piece
        data = b''.join(self._rx_chunks)
        # and split it into what we want and what's left over
        out, remaining = data[:n], data[n:]
        self._rx_chunks = [remaining]
        self._rx_bytes = len(remaining)

        return out

    async def _rx_message(self):
        # receive exactly one message and let the exceptions raise as they may

        # get 8 bytes of length: one for meta, one for data
        lens = await self._read_exactly(8)
        metalen, datalen = struct.unpack("<II", lens)

        # read and unpickle the metadata
        metabytes = await self._read_exactly(metalen)
        meta = pickle.loads(metabytes)

        # and just read the data bytes
        data = await self._read_exactly(datalen)

        return meta, data

    async def _rx_messages(self):
        # loop to receive messages and call the callback
        try:
            while True:
                # receive one message
                meta, data = await self._rx_message()
                # and then call the callback
                try:
                    self._recv_cb(self, meta, data)
                except:
                    pass
        except asyncio.CancelledError:
            # let ourselves be cancelled naturally
            # (we will only end up here if _closed is already True)
            raise
        except:
            # otherwise, close out the connection
            # we can't just await on close, because it awaits on us, and there
            # would be a deadlock
            # so note that we ended so the functions stop working
            self._closed = True
            # then schedule a task to call close for us
            asyncio.ensure_future(self.close())

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
        except asyncio.CancelledError:
            # let ourselves be cancelled naturally
            # (we will only end up here if _closed is already True)
            raise
        except:
            # otherwise, close out the connection
            # we can't just await on close, because it awaits on us, and there
            # would be a deadlock
            # so note that we ended so the functions stop working
            self._closed = True
            # then schedule a task to call close for us
            asyncio.ensure_future(self.close())
        finally:
            # regardless, pretend we finished all the messages in the queue
            # so that flush() doesn't deadlock
            try:
                while True:
                    self._tx_queue.task_done()
            except ValueError: # no more tasks to end
                pass

            # finally, close the writer socket so the other end sees us die
            self._writer.close()

    def send(self, meta, data):
        # send a message to the other side of the connector
        if self._closed:
            raise ConnectionClosedError()

        # pickle up the metadata so if something goes wrong, it happens now
        metabytes = pickle.dumps(meta)

        # and enqueue it, along with the data
        self._tx_queue.put_nowait((metabytes, data))

    async def flush(self):
        # wait for the tx queue to complete its messages
        # if the connection has ended, all messages will be completed
        # and no new messages will start, so we don't have to test that here
        await self._tx_queue.join()


    async def close(self):
        # we have officially ended
        self._closed = True

        # try to cancel the tasks
        if not self._tx_task.done():
            self._tx_task.cancel()
        if not self._rx_task.done():
            self._rx_task.cancel()

        # wait for them to cancel and/or eat any exception they produced
        try:
            await self._tx_task
        except:
            pass
        try:
            await self._rx_task
        except:
            pass

        # now call the callback to say we are finally done with everything
        try:
            self._recv_cb(self, None, None)
        except:
            pass