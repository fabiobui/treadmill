import asyncio

from bleak import BleakScanner, BleakClient

async def scan_ble_devices():
    print("Scanning for Bluetooth LE devices...")
    devices = await BleakScanner.discover()
    for d in devices:
        print(f"Address: {d.address}, Name: {d.name}")



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

async def connect_and_subscribe(address):
    print(f"Connecting to device at {address}...")
    async with BleakClient(address) as client:
        print("Connected successfully!")

        # Iterate through all services and subscribe to notify characteristics
        for service in client.services:
            print(f"Service: {service.uuid}")
            for char in service.characteristics:
                if "notify" in char.properties:
                    print(f"Subscribing to characteristic: {char.uuid}")
                    await client.start_notify(char.uuid, notification_handler)
        
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




asyncio.run(scan_ble_devices())

#address = "FF:71:4E:77:4B:DB"
address = "00-C3-F4-71-3F-23"
asyncio.run(discover_services(address))

speed_char_uuid = "00002ad3-0000-1000-8000-00805f9b34fb"  # Speed characteristic UUID

# Run the asyncio event loop
#asyncio.run(connect_and_read_speed(address, speed_char_uuid))
asyncio.run(connect_and_subscribe(address))
