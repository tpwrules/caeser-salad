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
    Send `message` to the bus with the given `tag`.


def subscribe(self, tag):
    Subscribe to messages with the given `tag` if not already subscribed, and increment the subscription count for the tag. To reduce load, the client will only be sent messages with the subscribed tags.

def unsubscribe(self, tag):
    Decrement the subscription count for the tag, and stop receiving messages with the given `tag` if it drops to zero.


def register_cb(self, mtype, callback, tag=None):
    Register a callback to be called when the specified message type is received. A message is considered `mtype` if `isinstance(message, mtype) is True`. If `tag` is not None, subscribe to the tag and only call the callback for messages with the specified tag. The callback is called with the message's tag and then the message.

def unregister_cb(self, mtype, callback, tag=None):
    Unregister a callback registered above and unsubscribes from the tag if not None. The callback must be the same object that was previously registered to the given type and tag. Raises ValueError if the callback was not previously registered.


def register_filter(self, messages):
    Create and return a MessageBusFilter for the given messages. messages is a dictionary whose keys are tags on the bus and whose values are iterables of `mtype`s to filter for. A key of None is valid and means to receive all messages. Subscribes to all tags that are not None.

def unregister_filter(self, mfilter):
    Unregister a MessageBusFilter object from this client. Any messages still in the queue of the MessageBusFilter will still be processed. This must be an object that was previously returned from register_filter. Raises ValueError if this is not true. Unsubscribes from all the tags the filter handled.

def shutdown(self):
    Unregisters all filters and callbacks, and unsubscribes from all messages. It is valid, but silly, to subscribe and add filters after this is called.


### MessageBusFilter
This class receives filtered messages from the bus and then queues them, then lets the user retrieve them with async methods. Instantiate it by calling the method of the client.

async def wait(self):
    Wait for a message to be received by this filter, then return it. Raises asyncio.QueueEmpty if the filter has been unregistered and the queue becomes empty.

# Other APIs

### BusConnector
This class handles reading and writing from the bus using a reader and writer.

def __init__(self, reader, writer):
    Create a connector with the given asyncio.StreamReader and asyncio.StreamWriter instances as returned by eg. asyncio.open_unix_connection.

def send(self, meta, data):
    Send a message to the other side of the connector. `meta` is an arbitrary Python object that gets pickled and unpickled on the other side. `data` is a bytes that gets transmitted unchanged. Raises ConnectionEndedError if the connection is closed.

async def recv(self):
    Receive a message from the other side of the connector. Returns `meta` and `data` as sent by send above. Raises ConnectionEndedError if the connection is closed. This function is not reentrant!

async def close(self):
    Immediately close the connector. Messages queued for transmission are discarded.

async def flush(self):
    Flush sent messages, if possible. If the connection ends or has ended, no exception is raised.