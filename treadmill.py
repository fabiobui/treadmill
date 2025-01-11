import asyncio
from bleak import BleakClient

def convert_kmh_to_pace(speed_kmh):
    """
    Convert speed in km/h to pace in min/km.
    """
    if speed_kmh > 0:
        pace_min_km = 60 / speed_kmh
        minutes = int(pace_min_km)
        seconds = int((pace_min_km - minutes) * 60)
        return f"{minutes}:{seconds:02d} min/km"
    else:
        return "0:00 min/km"  # Handle zero speed gracefully


def decode_treadmill_data(value):
    """
    Decode treadmill speed data.
    Assumes speed is in bytes 2 and 3 (little-endian format), in cm/s.
    """
    speed_raw = int.from_bytes(value[2:4], byteorder="little", signed=False)
    speed_kmh = speed_raw / 100  # kmh
    pace = convert_kmh_to_pace(speed_kmh)
    print(f"Speed: {speed_kmh:.2f} km/h | Pace {pace} min/km")


    # Extract flags (2 bytes, little-endian)
    flags = int.from_bytes(value[0:2], byteorder='little')

    # Initial position (2 octets for flags + 2 octets for instantaneous speed)
    next_position = 4

    # Conditional positions based on flags
    if flags & (1 << 1):
        pos_avg_speed = next_position
        next_position += 2
    if flags & (1 << 2):
        pos_tot_distance = next_position
        next_position += 3
    if flags & (1 << 3):
        pos_inclination = next_position
        next_position += 4
    if flags & (1 << 4):
        pos_elev_gain = next_position
        next_position += 4
    if flags & (1 << 5):
        pos_ins_pace = next_position
        next_position += 1
    if flags & (1 << 6):
        pos_avg_pace = next_position
        next_position += 1
    if flags & (1 << 7):
        pos_kcal = next_position
        next_position += 5
    if flags & (1 << 8):
        pos_hr = next_position
        next_position += 1
    if flags & (1 << 9):
        pos_met = next_position
        next_position += 1
    if flags & (1 << 10):
        pos_elapsed_time = next_position
        next_position += 2
    if flags & (1 << 11):
        pos_remain_time = next_position
        next_position += 2
    if flags & (1 << 12):
        pos_force_belt = next_position
        next_position += 4

    # Instantaneous speed (2 bytes, little-endian)
    speed = int.from_bytes(value[2:4], byteorder='little') / 100
    print(f'> Speed {speed}')

    # Total distance
    if 'pos_tot_distance' in locals():
        distance = int.from_bytes(value[pos_tot_distance:pos_tot_distance + 2], byteorder='little')
        distance_complement = value[pos_tot_distance + 2] << 16
        distance += distance_complement
        print(f'> Distance {distance}')

    # Inclination
    if 'pos_inclination' in locals():
        inclination = int.from_bytes(value[pos_inclination:pos_inclination + 2], byteorder='little', signed=True) / 10
        print(f'> Inclination % {inclination}')

    # Calories
    if 'pos_kcal' in locals():
        kcal = int.from_bytes(value[pos_kcal:pos_kcal + 2], byteorder='little')
        print(f'> Kcal {kcal}')

    # Heart rate
    if 'pos_hr' in locals():
        print(f'> HR {value[pos_hr]}')

    # Elapsed time
    if 'pos_elapsed_time' in locals():
        elapsed_time = int.from_bytes(value[pos_elapsed_time:pos_elapsed_time + 2], byteorder='little')
        print(f'> Elapsed time {elapsed_time}')



def notification_handler(sender, data):
    """
    Callback to handle treadmill speed notifications.
    """
    try:
        decode_treadmill_data(data)
    except Exception as e:
        print(f"Error decoding data: {e}")
        print(f"Raw Data: {data}")

async def connect_and_subscribe(address, char_uuid):
    """
    Connect to BLE treadmill and subscribe to speed notifications.
    """
    print(f"Connecting to treadmill at {address}...")
    async with BleakClient(address) as client:
        print("Connected successfully!")

        # Subscribe to the speed characteristic
        await client.start_notify(char_uuid, notification_handler)
        print("Subscribed to speed notifications. Press Ctrl+C to stop.")

        # Keep the script alive
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Stopping notifications...")
            await client.stop_notify(char_uuid)

# Replace with your treadmill's Bluetooth address and correct characteristic UUID
treadmill_address = "FF:71:4E:77:4B:DB"
speed_characteristic_uuid = "00002acd-0000-1000-8000-00805f9b34fb"  # Correct Handle 22 UUID

# Run the asyncio event loop
asyncio.run(connect_and_subscribe(treadmill_address, speed_characteristic_uuid))
