# this class encompasses a mavlink Destination

import pymavlink.dialects.v20.ardupilotmega as mavlink
import types

class Destination:
    def __init__(self):
        # set of system ids we send to
        self._sysids = set()
        # set of (system, component) ids we send to
        self._compids = set()


    # read one message from the destination's transport
    async def _get_msg(self):
        raise NotImplementedError

    # write one message to the destination's transport
    def _put_msg(self, msg, src, dest):
        raise NotImplementedError


    async def read_msg(self):
        msg, src = await self._get_msg()

        # we have to monitor for HEARTBEAT messages so we can build
        # our routing table
        if isinstance(msg, mavlink.MAVLink_heartbeat_message):
            if src not in self._compids:
                self._compids.add(src)
            if src[0] not in self._sysids:
                self._sysids.add(src[0])

        return msg, src

    # write one message, if this destination should send it
    # if we sent it, return True
    def write_msg(self, msg, src, dest):
        should_send = False
        if dest[0] == 0:
            should_send = True
        elif dest[0] in self._sysids and dest[1] == 0:
            should_send = True
        elif dest in self._compids:
            should_send = True

        if should_send:
            self._put_msg(msg, src, dest)

        return should_send

# a destination that needs byte encoding/decoding
class BytesDestination(Destination):
    # Source object simply has source IDs and a sequence number for that ID
    class Source:
        def __init__(self, src):
            self.srcSystem = src[0]
            self.srcComponent = src[1]
            self.seq = 0
            self.signing = types.SimpleNamespace()
            self.signing.sign_outgoing = False

        def pack(self, msg):
            # tell the message to get packed with ourselves as the mav state
            packed = msg.pack(self)
            # sequence id is 8 bit
            self.seq = (self.seq + 1) & 0xFF
            return packed

    def __init__(self):
        super().__init__()

        # we need Sources for each source we send
        # so we can pack messages correctly and keep track of sequence numbers
        # dictionary of (src_sysid, src_compid) to Source objects
        self._sources = {}

        # we also need a proper mavlink object so we can receive and decode
        # messages from the transport
        # but it doesn't have a file cause we don't send things with it
        self._mav = mavlink.MAVLink(None)


    # read at least one byte from the transport
    async def _read(self):
        raise NotImplementedError

    # write some bytes to the transport
    def _write(self, data):
        raise NotImplementedError


    async def _get_msg(self):
        # make sure we send out any messages already in the buffer first
        # so we don't unnecessarily wait for more bytes
        msg = self._mav.parse_char(b'')
        while msg is None:
            # receive some bytes from the transport
            new_bytes = await self._read()
            # and try to parse a message from them
            msg = self._mav.parse_char(new_bytes)
            # if None, there weren't enough bytes

        return msg, (msg.get_srcSystem(), msg.get_srcComponent())

    def _put_msg(self, msg, src, dest):
        source = self._sources.get(src)
        if source is None:
            source = BytesDestination.Source(src)
            self._sources[src] = source

        self._write(source.pack(msg))

# destination based on an asyncio reader, writer pair
class StreamDestination(BytesDestination):
    def __init__(self, reader, writer):
        super().__init__()

        self._reader = reader
        self._writer = writer

    async def _read(self):
        return await self._reader.read(100)

    def _write(self, data):
        return self._writer.write(data)
