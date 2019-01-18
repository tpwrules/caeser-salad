import asyncio
import pickle

# handles sending of messages to an actor
# this is effectively the client
class MessageSendProtocol(asyncio.Protocol):
    def __init__(self, actor):
        super().__init__()
        self.actor = actor

    def connection_made(self, transport):
        self.transport = transport

    # data should never be received

    def send_msg(self, msg):
        # pickle up the message
        data = pickle.dumps(msg)
        # tell the other side how big the message is
        self.transport.write(len(data).to_bytes(4, byteorder='little'))
        # and write the message
        self.transport.write(data)

    def connection_lost(self, exc):
        pass

class MessageRecvProtocol(asyncio.Protocol):
    def __init__(self, actor):
        super().__init__()
        self.actor = actor
        self.src = None
        self.data_buf = bytes()

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self.data_buf = self.data_buf + data

        while True:  
            if len(self.data_buf) < 4:
                # we don't know the length
                return

            data_len = int.from_bytes(self.data_buf[:4], byteorder='little')+4

            if len(self.data_buf) < data_len:
                # we don't have the whole message
                return

            msg_bytes, self.data_buf = \
                self.data_buf[:data_len], self.data_buf[data_len:]

            msg = pickle.loads(msg_bytes[4:])

            self.actor._handle_msg(self.src, msg)


