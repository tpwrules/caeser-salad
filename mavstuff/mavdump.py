# try to load the mavlink parser

import importlib
import socket

mavlink = importlib.import_module("pymavlink.dialects.v20.ardupilotmega")

mav = mavlink.MAVLink(None, srcSystem=254, srcComponent=195, use_native=True)

conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn.connect(("localhost", 5763))

while True:
    b = conn.recv(mav.bytes_needed())
    msg = mav.parse_char(b)
    if msg is not None:
        print(msg)
