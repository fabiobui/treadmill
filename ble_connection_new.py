# ble_connection.py

import asyncio
import time
import struct
from bleak import BleakClient


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

class BLEConnection:
    """
    Encapsulates all BLE connection logic for treadmill data.
    """

    def __init__(
        self,
        treadmill,  # Pass your TreadmillSimulate instance
        address="FF:71:4E:77:4B:DB",  # default treadmill MAC address
        speed_characteristic_uuid="00002acd-0000-1000-8000-00805f9b34fb",
        control_point_uuid="00002acc-0000-1000-8000-00805f9b34fb", 
        max_retries=5
    ):
        self.treadmill = treadmill
        self.address = address
        self.speed_characteristic_uuid = speed_characteristic_uuid
        self.control_point_uuid = control_point_uuid
        self.max_retries = max_retries

        # Shared data
        self.average = []  # Store average speed and bpm for each km
        self.data_stream = {
            "speed": 0.0,
            "pace": "0:00",
            "distance": 0,
            "average_speeds": [],
            "running_time": 0,
            "energy": 0,
            "bpm": 0
        }
        self.last_update = time.time()
        self.running_start_time = None

        # Create a dedicated event loop for BLE
        self.ble_loop = asyncio.new_event_loop()
        self.client = None

    def convert_kmh_to_pace(self, speed_raw):
        """Convert speed in km/h to pace in min/km."""
        if speed_raw > 0:
            pace_min_km = 60 / (speed_raw / 100)  # speed_raw is cm/s
            minutes = int(pace_min_km)
            seconds = int((pace_min_km - minutes) * 60)
            return f"{minutes}:{seconds:02d}"
        return "0:00"

    def decode_treadmill_data(self, value):
        """
        Decode treadmill speed data.
        Assumes speed is in bytes 2 and 3 (little-endian format), in cm/s.
        """
        speed_raw = int.from_bytes(value[2:4], byteorder="little", signed=False)
        self.data_stream["speed"] = speed_raw / 100  # km/h
        self.data_stream["pace"] = self.convert_kmh_to_pace(speed_raw)

        # Extract flags (2 bytes, little-endian)
        flags = int.from_bytes(value[0:2], byteorder='little')

        # Initial position (2 octets for flags + 2 octets for instantaneous speed)
        next_position = 4

        # Check each flag to identify the offsets in the data
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

        # Instantaneous speed
        speed = int.from_bytes(value[2:4], byteorder='little') / 100

        # Heart rate
        if 'pos_hr' in locals():
            self.data_stream["bpm"] = f"{value[pos_hr]}"


        # Total distance
        if 'pos_tot_distance' in locals():
            distance = int.from_bytes(
                value[pos_tot_distance:pos_tot_distance + 2], 
                byteorder='little'
            )
            distance_complement = value[pos_tot_distance + 2] << 16
            distance += distance_complement
            self.data_stream["distance"] = distance / 1000

            total_km = int(self.data_stream["distance"])
            # Track average speed and pace each km
            if len(self.data_stream["average_speeds"]) < total_km:
                avg_speed = sum(self.average[0]) / len(self.average[0]) if len(self.average[0]) > 0 else 0
                avg_bpm = sum(self.average[1]) / len(self.average[1]) if len(self.average[1]) > 0 else 0
                avg_pace = self.convert_kmh_to_pace(avg_speed * 100)  # convert back to cm/s for the method
                self.average.clear()
                self.data_stream["average_speeds"].append((avg_speed, avg_pace, avg_bpm))
            else:
                self.average.append((self.data_stream["speed"], self.data_stream["bpm"]))

        # Inclination
        if 'pos_inclination' in locals():
            inclination = int.from_bytes(
                value[pos_inclination:pos_inclination + 2], 
                byteorder='little',
                signed=True
            ) / 10

        # Calories
        if 'pos_kcal' in locals():
            kcal = int.from_bytes(value[pos_kcal:pos_kcal + 2], byteorder='little')
            self.data_stream["energy"] = kcal

        # Elapsed time
        if 'pos_elapsed_time' in locals():
            elapsed_time = int.from_bytes(
                value[pos_elapsed_time:pos_elapsed_time + 2], 
                byteorder='little'
            )
            self.data_stream["running_time"] = elapsed_time

    def notification_handler(self, sender, data):
        """
        Callback to handle treadmill speed notifications.
        """
        try:
            self.decode_treadmill_data(data)
            # Update treadmill simulator with new data
            self.treadmill.set_measures(
                speed_m_s=self.data_stream["speed"],
                distance_m=self.data_stream["distance"],
                energy=self.data_stream["energy"],
                bpm=self.data_stream["bpm"],
                elapsed_s=self.data_stream["running_time"]
            )
        except Exception as e:
            print(f"Error decoding data: {e}")
            print(f"Raw Data: {data}")


    async def connect_treadmill(self):
        """Connect to BLE treadmill and manage the connection."""
        retries = 0
        while retries < self.max_retries:
            try:
                print(f"Connecting to treadmill (Attempt {retries + 1}/{self.max_retries})...")
                self.client = BleakClient(self.address, timeout=10.0)
                await self.client.connect()
                if not self.client.is_connected:
                    raise Exception("Failed to connect.")

                print("Connected successfully!")

                # Optionally, subscribe to notifications if needed
                # await self.client.start_notify(self.notification_characteristic_uuid, self.notification_handler)

                    # Keep the connection alive
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    print("Stopping notifications...")
                    await self.client.stop_notify(self.speed_characteristic_uuid)
                    break
                    
            except Exception as e:
                retries += 1
                print(f"Connection error: {e}")
                if retries < self.max_retries:
                    print("Retrying in 2 seconds...")
                    await asyncio.sleep(2)
                else:
                    print("Max retries reached. Unable to connect.")
                    break

    def start_ble_loop(self):
        """Start the BLE connection loop in the current thread."""
        asyncio.set_event_loop(self.ble_loop)
        # Run the BLE coroutine until it's finished
        try:
            self.ble_loop.run_until_complete(self.connect_treadmill())
        finally:
            self.ble_loop.close()


    def send_speed(self, speed_kmh):
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
        speed_encoded = float_to_ieee11073_16bit(speed_kmh)

        # Build the payload: [Opcode][Reserved][Speed (2 bytes)]
        #payload = struct.pack('<BB', SET_TARGET_SPEED_OPCODE, RESERVED_BYTE) + speed_encoded
        
        # Build the payload: [Opcode][Reserved][Speed (2 bytes)]
        payload = struct.pack('<B', SET_TARGET_SPEED_OPCODE) + b'\x00' + speed_encoded

        # Schedule the write operation on the BLE event loop
        future = asyncio.run_coroutine_threadsafe(
            self._write_control_point(payload),
            self.ble_loop
        )

        try:
            # Wait for the write operation to complete (timeout after 5 seconds)
            future.result(timeout=5)
            print(f"Successfully sent speed: {speed_kmh} km/h")
        except Exception as e:
            print(f"Failed to send speed: {e}")

    async def _write_control_point(self, data):
        """Asynchronously write data to the Control Point characteristic."""
        if self.client and self.client.is_connected:
            try:
                # Try writing with response first
                await self.client.write_gatt_char(self.control_point_uuid, data, response=True)
                print("Set Target Speed command sent successfully with response.")
            except Exception as e:
                print(f"Write with response failed: {e}. Trying without response...")
                try:
                    await self.client.write_gatt_char(self.control_point_uuid, data, response=False)
                    print("Set Target Speed command sent successfully without response.")
                except Exception as e2:
                    print(f"Failed to write to Control Point: {e2}")
        else:
            print("BLE client is not connected. Cannot send speed data.")

    def disconnect(self):
        """Disconnect from the treadmill."""
        if self.client and self.client.is_connected:
            asyncio.run_coroutine_threadsafe(
                self.client.disconnect(),
                self.ble_loop
            )
            print("Disconnected from treadmill.")