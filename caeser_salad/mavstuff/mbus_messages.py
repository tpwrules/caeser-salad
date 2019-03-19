from caeser_salad.mbus.message import Message

# these all need to be in their own module so that the unpickler
# can find them reliably

class MAVSystemMessage(Message):
    pass

class MAVMessageToComponent(Message):
    def __init__(self, msg, src, dest):
        self.msg = msg
        self.src = src
        self.dest = dest

class MAVMessageFromComponent(Message):
    def __init__(self, msg, src):
        self.msg = msg
        self.src = src
