from caeser_salad.mbus.message import Message

class MAVSystemMessage(Message):
    pass

class ChangeDestinationMessage(MAVSystemMessage):
    def __init__(self, tag, create):
        # change the destination on the given tag
        # if create = True, create it
        # otherwise, destroy it
        self.tag = tag
        self.create = create

class MAVMessageToComponent(Message):
    def __init__(self, msg, src, dest):
        self.msg = msg
        self.src = src
        self.dest = dest

class MAVMessageFromComponent(Message):
    def __init__(self, msg, src):
        self.msg = msg
        self.src = src
