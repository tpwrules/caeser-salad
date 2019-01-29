# runs the message bus server

import asyncio
import os

class MessageBusServer:
    def __init__(self, bus_addr):
        self.bus_addr = bus_addr

    async def serve(self):
        await asyncio.start_unix_server(self.client_connected, 
            path=self.bus_addr)

    async def client_connected(self, reader, writer):
        print("hi!", type(reader), type(writer))
        try:
            while True:
                print("send")
                writer.write(b"3")
                try:
                    await writer.drain()
                except ConnectionResetError:
                    print("oh no!")
                    break
                await asyncio.sleep(1)
        finally:
            writer.close()


if __name__ == "__main__":
    try:
        server = MessageBusServer("./socket_mbus_main")
        loop = asyncio.get_event_loop()
        asyncio.ensure_future(server.serve())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if os.path.exists("./socket_mbus_main"):
            os.remove("./socket_mbus_main")