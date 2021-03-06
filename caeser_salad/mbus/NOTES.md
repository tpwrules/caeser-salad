Design Notes

# Concept

On a message bus, messages are passed back and forth. A message on the bus is an instance of Message (or subclass) and is pickled for transmission. The bus supports message tags, which are strings that name the category or destination or whatever of the message. Someone who wants to be on the bus can instantiate a MessageBusClient and then subscribe to relevant tags. 

# Public API

### Message

Tis class represents a message object. It doesn't really do anything except be subclassed from.

### MessageBusClient
This class is a client on the message bus. It connects to the message bus server over a Unix socket and can receive and transmit messages on the bus. It uses asyncio to do its job, and so needs to be associated with a loop. Messages are not queued in this object.

@classmethod
async def create(self, bus_addr):
    Instantiate a MessageBusClient that connects to `bus_addr`.

def send(self, tag, message):
    Send `message` to the bus with the given `tag`. Raises ConnectionClosedError if the connection is closed.


def subscribe(self, tag):
    Subscribe to messages with the given `tag` if not already subscribed, and increment the subscription count for the tag. To reduce load, the client will only be sent messages with the subscribed tags. Raises ConnectionClosedError if the connection is closed.

def unsubscribe(self, tag):
    Decrement the subscription count for the tag, and stop receiving messages with the given `tag` if it drops to zero. Does nothing if the connection is closed.


def register_cb(self, mtype, callback, tag=None):
    Register a callback to be called when the specified message type is received. A message is considered `mtype` if `isinstance(message, mtype) is True`. If `tag` is not None, subscribe to the tag and only call the callback for messages with the specified tag. If the same tuple is registered multiple times, it is called multiple times. The callback is called with the message's tag and then the message. When the connection ends, the callback is called with both as None, once for each time it has been registered. Exceptions raised by the callback are ignored. Raises ConnectionClosedError if the connection is closed.

def unregister_cb(self, mtype, callback, tag=None):
    Unregister a callback registered above and unsubscribes from the tag if not None. The callback must be the same object that was previously registered to the given type and tag. Only the first occurrence is deleted. Raises ValueError if the callback was not previously registered. Does nothing if the connection is closed.


async def close(self):
    Immediately unregisters all filters and callbacks, and unsubscribes from all messages. Any further operations will result in raising ConnectionClosedError.


### MessageBusFilter
This class receives filtered messages from the bus and then queues them, then lets the user retrieve them with async methods.

def __init__(self, client, filter=None):
    Connect to `client` and wait for the messages in `filters`. `filters` is a dictionary whose keys are tags to watch for and values are iterables of `mtype`s to filter for. A key of None is valid and means to receive all messages. If `filter` itself is None, no messages are received.

def add(self, mtype, tag=None):
    Add the specific `mtype` to this filter, optionally only received by `tag`. If the same tag, mtype is added multiple times, nothing happens. Raises ConnectionClosedError if the client is closed.

def remove(self, mtype, tag=None):
    Remove the specific `mtype` from this filter, on `tag`. Raises ValueError if it was not previously added. Does nothing if the client is closed.

def remove_all(self):
    Remove all items from the filter. Does nothing if the client is closed.

async def recv(self):
    Wait for a message to be received by this filter, then return (tag, message).  Raises ConnectionClosedError if the connection is closed and the queue becomes empty. Raises asyncio.QueueEmpty if the filter has no messages and the queue becomes empty.

# Other APIs

### BusConnector
This class handles reading and writing from the bus using a reader and writer.

def __init__(self, reader, writer, recv_cb):
    Create a connector with the given asyncio.StreamReader and asyncio.StreamWriter instances as returned by eg. asyncio.open_unix_connection. `recv_cb` is a callback that is called with the callback first, then `meta` and `data` as the two next parameters every time a message is received. When the connection closes, the callback is called with `meta` and `data` as None. Exceptions raised by the callback are ignored.

def send(self, meta, data):
    Send a message to the other side of the connector. `meta` is an arbitrary Python object that gets pickled and unpickled on the other side. `data` is a bytes that gets transmitted unchanged. Raises ConnectionClosedError if the connection is closed.

async def close(self):
    Close the connector and wait for it to be fully closed. Messages queued for transmission are discarded.

async def flush(self):
    Flush sent messages, if possible. If the connection ends or has ended, no exception is raised.