import asyncio
import struct

from bleak import BleakScanner, BleakClient

def float_to_ieee11073_16bit(value):
    """
    Converts a float to IEEE-11073 16-bit float (SFloat).
    Returns bytes in little-endian format.
    """
    if value == 0:
        return b'\x00\x00'

    # Determine sign
    sign = 0
    if value < 0:
        sign = 1
        value = abs(value)

    # Find exponent and mantissa
    exponent = 0
    mantissa = value

    # Scale mantissa to fit in 12 bits
    while mantissa >= 2048 and exponent < 7:
        mantissa /= 10.0
        exponent += 1

    mantissa = int(round(mantissa))
    if mantissa >= 4096:
        mantissa = 4095
        exponent = 7

    # Pack mantissa and exponent
    sfloat = (mantissa & 0x0FFF) | ((exponent & 0x000F) << 12)
    if sign:
        sfloat |= 0x8000

    return struct.pack('<H', sfloat)



async def discover_services(address):
    print(f"Connecting to {address}...")
    async with BleakClient(address) as client:
        print("Connected successfully!")
        print("Services and Characteristics:")
        
        for service in client.services:
            print(f"Service: {service.uuid}")
            for char in service.characteristics:
                print(f"  Characteristic: {char.uuid} | Properties: {char.properties}")


# Notification handler callback
def notification_handler(sender, data):
    """
    Callback function to process treadmill speed data.
    Assumes the data is in little-endian format.
    """
    speed = int.from_bytes(data[:2], byteorder="little", signed=False) / 100  # Speed data in m/s
    print(f"Speed Notification from {sender}: {speed:.2f} m/s")

async def connect_and_read_speed(address, speed_char_uuid):
    print(f"Connecting to treadmill at {address}...")
    async with BleakClient(address) as client:
        print("Connected successfully!")

        # Start listening for notifications
        await client.start_notify(speed_char_uuid, notification_handler)
        print("Subscribed to speed notifications. Press Ctrl+C to stop.")
        
        # Keep the connection alive to receive notifications
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Stopping notifications...")
            await client.stop_notify(speed_char_uuid)

async def connect_and_write_speed(address, speed_char_uuid):
    print(f"Connecting to treadmill at {address}...")
    async with BleakClient(address) as client:
        print("Connected successfully!")

        # Start listening for notifications
        await client.start_notify(speed_char_uuid, notification_handler)
        print("Subscribed to speed notifications. Press Ctrl+C to stop.")

        # Opcode for Set Target Speed
        SET_TARGET_SPEED_OPCODE = 0x01
        
        # Reserved byte
        RESERVED_BYTE = 0x00

        # Encode speed as IEEE-11073 16-bit float
        speed_encoded = float_to_ieee11073_16bit(6.0)  # 6.0 m/s

        # Build the payload: [Opcode][Reserved][Speed (2 bytes)]
        #payload = struct.pack('<BB', SET_TARGET_SPEED_OPCODE, RESERVED_BYTE) + speed_encoded
        payload = struct.pack('<B', SET_TARGET_SPEED_OPCODE) + b'\x00' + speed_encoded
        speed_value = int(600)  # 6.0 m/s in 0.01 m/s units
        payload = speed_value.to_bytes(2, byteorder='little')
        print(f"Payload: {payload}")

        print(f"Writing to characteristic: {speed_char_uuid}")
        await client.write_gatt_char(speed_char_uuid, payload)
        
        # Keep the connection alive to receive notifications
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Stopping notifications...")
            await client.stop_notify(speed_char_uuid)


async def connect_and_subscribe(address):
    print(f"Connecting to device at {address}...")
    async with BleakClient(address) as client:
        print("Connected successfully!")

        # Iterate through all services and subscribe to notify characteristics
        for service in client.services:
            print(f"Service: {service.uuid}")
            for char in service.characteristics:
                #if "notify" in char.properties:
                #    print(f"Subscribing to characteristic: {char.uuid}")
                #    await client.start_notify(char.uuid, notification_handler)
                if "write" in char.properties:
                    print(f"Writing to characteristic: {char.uuid}")
                    await client.write_gatt_char(char.uuid, b"\x01\x00")
        
        print("Subscribed to all notify characteristics. Press Ctrl+C to stop.")

        # Keep the connection alive
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Stopping notifications...")
            for service in client.services:
                for char in service.characteristics:
                    if "notify" in char.properties:
                        await client.stop_notify(char.uuid)




# Set the treadmill's MAC address
address = "FF:71:4E:77:4B:DB"
#asyncio.run(discover_services(address))

#speed_char_uuid = "00002ad3-0000-1000-8000-00805f9b34fb"  # Speed characteristic UUID // notify
speed_char_uuid = "00002ad9-0000-1000-8000-00805f9b34fb"  # Speed characteristic UUID // write

# Run the asyncio event loop
#asyncio.run(connect_and_read_speed(address, speed_char_uuid))
#asyncio.run(connect_and_subscribe(address))
asyncio.run(connect_and_write_speed(address, speed_char_uuid))