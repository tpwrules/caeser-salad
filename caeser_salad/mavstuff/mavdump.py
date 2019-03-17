# try to load the mavlink parser

import importlib
import socket

class WProxy:
    def __init__(self, conn):
        self.conn = conn

    def write(self, data):
        print(self.conn.send(data))

mavlink = importlib.import_module("pymavlink.dialects.v20.ardupilotmega")


conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn.connect(("localhost", 5763))

mav = mavlink.MAVLink(WProxy(conn), 
    srcSystem=254, srcComponent=195, use_native=True)

import time



mi = 0
while True:
    b = conn.recv(mav.bytes_needed())
    msg = mav.parse_char(b)
    if msg is not None:
        print(msg, msg.get_srcSystem(), msg.get_srcComponent())
        mi += 1
        if mi > 5:
            mav.heartbeat_send(mavlink.MAV_TYPE_ONBOARD_CONTROLLER, 0, 0, 0, 
                mavlink.MAV_STATE_ACTIVE, 3)
        if mi == 7:
            mav.param_request_list_send(1, 1)

