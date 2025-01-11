import asyncio
from bleak import BleakClient

async def list_services(address):
    async with BleakClient(address) as client:
        try:
            await client.connect()
            if not client.is_connected:
                print("Failed to connect.")
                return
            svcs = await client.get_services()
            for service in svcs:
                print(f"Service {service.uuid}: {service.description}")
                for char in service.characteristics:
                    props = ",".join(char.properties)
                    print(f"  Characteristic {char.uuid}: {char.description} ({props})")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    address = "FF:71:4E:77:4B:DB"  # Replace with your treadmill's MAC address
    asyncio.run(list_services(address))
