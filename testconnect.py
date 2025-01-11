import asyncio
import threading
from bleak import BleakClient

DEVICE_ADDRESS = "FF:71:4E:77:4B:DB"
FTMS_CONTROL_POINT_UUID = "00002ad9-0000-1000-8000-00805f9b34fb"

ble_loop = asyncio.new_event_loop()
client = None

def kph_to_ftms_speed_bytes(kph: float) -> bytes:
    """
    Convert km/h -> 0.01 m/s.
    Returns a 2-byte, little-endian representation.
    """
    # Convert to m/s
    mps = kph * 1000 / 3600  # or 0.27778 * kph
    # Multiply by 100 for 0.01 m/s increments
    speed_int = int(round(kph * 100))
    # Little-endian 2-byte
    return speed_int.to_bytes(2, byteorder='little', signed=False)


def handle_indication(sender, data):
    print(f"Indication from {sender}: {data}")


def send_speed(speed_kmh):
    """
    Send speed data to the treadmill device using FTMS Control Point.
    
    Args:
        speed_kmh (float): Desired speed in km/h.
    """
    # Opcode for Set Target Speed
    SET_TARGET_SPEED_OPCODE = 0x01
    
    # Reserved byte
    RESERVED_BYTE = 0x00
    # Encode speed as IEEE-11073 16-bit float
    
    # Build the payload: [Opcode][Reserved][Speed (2 bytes)]
    #payload = struct.pack('<B', SET_TARGET_SPEED_OPCODE) + b'\x00' + speed_encoded
    # Schedule the write operation on the BLE event loop
    future = asyncio.run_coroutine_threadsafe(
        write_control_point(speed_kmh),
        ble_loop
    )
    try:
        # Wait for the write operation to complete (timeout after 5 seconds)
        future.result(timeout=5)
        print(f"Successfully sent speed: {speed_kmh} km/h")
    except Exception as e:
        print(f"Failed to send speed: {e}")

async def write_control_point(data):
    """Asynchronously write data to the Control Point characteristic."""
    global client
    if client and client.is_connected:
        try:
            # Try writing with response first
            # 1) Request Control: OpCode = 0x00
            # Some treadmills won't allow Start/Resume or Set Speed until you have control.
            #await client.write_gatt_char(FTMS_CONTROL_POINT_UUID, bytearray([0x00]), response=True)
            #print("Requested control...")
            await asyncio.sleep(1)
            # 2) Start/Resume: OpCode = 0x06
            await client.write_gatt_char(FTMS_CONTROL_POINT_UUID, bytearray([0x07]), response=True)        
            await asyncio.sleep(1)
            # 3) Set Target Speed: OpCode = 0x02
            data = b'\x02' + data # Set Target Speed OpCode = 0x02
            await client.write_gatt_char(FTMS_CONTROL_POINT_UUID, data, response=True)
            print(f"Set Target Speed {data} command sent successfully with response.")
            await asyncio.sleep(1)            

        except Exception as e:
            print(f"Failed to write to Control Point: {e}")
    else:
        print("BLE client is not connected. Cannot send speed data.")



async def connect_treadmill():
    async with BleakClient(DEVICE_ADDRESS) as Mclient:
        global client
        client = Mclient
        if not client.is_connected:
            print("Failed to connect.")
            return

        await client.start_notify(FTMS_CONTROL_POINT_UUID, handle_indication)
        print("Connected. Waiting for notifications...")
        #await asyncio.sleep(5)
        # Keep the connection alive
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Stopping notifications...")
            await client.stop_notify(FTMS_CONTROL_POINT_UUID)
            print("Disconnected.")

def start_ble_loop():
    global ble_loop    
    asyncio.set_event_loop(ble_loop)
    # Run the BLE coroutine until it's finished
    try:
        ble_loop.run_until_complete(connect_treadmill())
    finally:
        ble_loop.close()


if __name__ == "__main__":
    print("Starting BLE connection...")

    # Start BLE connection loop in a separate daemon thread
    ble_thread = threading.Thread(target=start_ble_loop, daemon=True)
    ble_thread.start()

    sent_speed = False
    try:
        while True:
            if client and client.is_connected and not sent_speed:
                send_speed(kph_to_ftms_speed_bytes(5))
                sent_speed = True
                
    except KeyboardInterrupt:
        print("Stopping notifications...")
        client.stop_notify(FTMS_CONTROL_POINT_UUID)
        print("Disconnected.")



    #asyncio.run(main())
