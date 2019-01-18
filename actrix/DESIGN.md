this covers the design of the Actrix™ system

Classes
-------

#### Actor

##### `def __init__(self, listen_ip, listen_port)`
Initialize this actor to listen on the given IP and port for other actors to talk to it.

##### `def make_address(self, name, ip, port)`
Make and return an ActorAddress to the actor with the specified name, IP, and port. name must be the correct name for the actor at the other end.

##### `def send(self, dest, msg)`
Send the msg to the dest ActorAddress. returns nothing

##### `async def on_receive(self, src, msg)`
Called to process a received msg from ActorAddress src

##### `def _handle_msg(self, src, msg)`
Process a message received from another actor

##### `def _handle_connections(self)`
Handle all connections from other actors

#### MessagePipe

##### `def __init__(self, ip, port)