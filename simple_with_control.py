# Copyright 2024, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging

from pyftms import FitnessMachine, FtmsEvents, get_client_from_address

#ADDRESS = "29:84:5A:22:A4:11"
ADDRESS = "FF:71:4E:77:4B:DB"

logging.basicConfig(level=logging.ERROR)

_LOGGER = logging.getLogger(__name__)


def on_event(event: FtmsEvents):
    print(f"Event received: {event}")


def on_disconnect(m: FitnessMachine):
    print("Fitness Machine disconnected.")


def notification_handler(sender, data):
    print(f"Indicate received: {data}")

speed_characteristic_uuid="00002acd-0000-1000-8000-00805f9b34fb"




async def run():
    async with await get_client_from_address(
        ADDRESS, on_ftms_event=on_event, on_disconnect=on_disconnect
    ) as c:
        await c.start_resume()
        await asyncio.sleep(10)
        await c.set_target_speed(5)
        await asyncio.sleep(30)
        await c.stop()


asyncio.run(run())
