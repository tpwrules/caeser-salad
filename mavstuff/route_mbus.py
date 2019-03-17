# this file manages all the message bus connections for the MAVlink router

import asyncio

import destination

import repackage
repackage.up()

from mbus import client as mclient
