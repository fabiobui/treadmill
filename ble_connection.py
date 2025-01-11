# ble_connection.py

import asyncio
import time
import struct
from bleak import BleakClient
from datetime import datetime, timedelta

from db_management import DBManagement, local_db, LocalSession

# Instantiate the class
db_manager = DBManagement()

# For convenience, get references
app = db_manager.app

class BLEConnection:
    """
    Encapsulates all BLE connection logic for treadmill data.
    """

    def __init__(
        self,
        treadmill,  # Pass your TreadmillSimulate instance
        address="FF:71:4E:77:4B:DB",  # default treadmill MAC address
        speed_characteristic_uuid="00002acd-0000-1000-8000-00805f9b34fb",
        control_point_uuid = "00002ace-0000-1000-8000-00805f9b34fb",
        max_retries=5,
        limits={
            "speed_yellow": 10.0,
            "speed_red": 12.0,
            "bpm_yellow": 120,
            "bpm_red": 140
        }
    ):
        self.treadmill = treadmill
        self.address = address
        self.speed_characteristic_uuid = speed_characteristic_uuid
        self.control_point_uuid = control_point_uuid,
        self.max_retries = max_retries
        self.limits = limits

        # Shared data
        self.average = {   # Temporary storage for average speed and bpm
            "speed": [],
            "bpm": []
        }
        self.data_stream = {
            "speed": 0.0,
            "pace": "0:00",
            "distance": 0,
            "average_speeds": [],
            "running_time": 0,
            "energy": 0,
            "bpm": 0,
            "limits": limits
        }
        self.last_update = time.time()
        self.running_start_time = None

        # Create a dedicated event loop for BLE
        self.ble_loop = asyncio.new_event_loop()
        self.client = None
        self.indicate: asyncio.Future[bytes]
        

    def convert_kmh_to_pace(self, speed_raw):
        """Convert speed in km/h to pace in min/km."""
        if speed_raw > 0:
            pace_min_km = 60 / (speed_raw / 100)  # speed_raw is cm/s
            minutes = int(pace_min_km)
            seconds = int((pace_min_km - minutes) * 60)
            return f"{minutes}:{seconds:02d}"
        return "0:00"

    def format_time(seconds):
        minutes = str(seconds // 60).zfill(2)
        secs = str(seconds % 60).zfill(2)
        return f"{minutes}:{secs}"

    def decode_treadmill_data(self, value):
        """
        Decode treadmill speed data.
        Assumes speed is in bytes 2 and 3 (little-endian format), in cm/s.
        """
        speed_raw = int.from_bytes(value[2:4], byteorder="little", signed=False)
        if (speed_raw > 0):
            self.average["speed"].append(speed_raw / 100)
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
            bpm = value[pos_hr]
            self.data_stream["bpm"] = bpm
            if (bpm > 0):
                self.average["bpm"].append(bpm)              


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
                if len(self.data_stream["average_speeds"]) == 0:
                    current_time = datetime.now()
                    started_time = current_time - timedelta(seconds=elapsed_time)
                    data = { # Save the session start time
                        "datetime": started_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "km": 0,
                        "elapsed": 0,
                        "avg_speed": 0,
                        "avg_bpm": 0,
                        "kcal": 0
                    }
                    db_manager.save_local_session(data)
                avg_speed = sum(self.average["speed"]) / len(self.average["speed"]) if len(self.average["speed"]) > 0 else 0
                avg_bpm = sum(self.average["bpm"]) / len(self.average["bpm"]) if len(self.average["bpm"]) > 0 else 0
                avg_pace = self.convert_kmh_to_pace(avg_speed * 100)  # convert back to cm/s for the method
                self.average["speed"].clear()
                self.average["bpm"].clear()
                lap_time = elapsed_time - self.data_stream["average_speeds"][-1][5] if len(self.data_stream["average_speeds"]) > 0 else elapsed_time
                lap_kal = kcal - self.data_stream["average_speeds"][-1][6] if len(self.data_stream["average_speeds"]) > 0 else kcal
                self.data_stream["average_speeds"].append((lap_time, lap_kal, avg_speed, avg_pace, avg_bpm, elapsed_time, kcal)) 
                # Save session data to database
                data = {
                    "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "km": int(distance),
                    "elapsed": elapsed_time,
                    "avg_speed": avg_speed,
                    "avg_bpm": avg_bpm,
                    "kcal": kcal
                }
                db_manager.save_local_session(data)         


        # Inclination
        if 'pos_inclination' in locals():
            inclination = int.from_bytes(
                value[pos_inclination:pos_inclination + 2], 
                byteorder='little',
                signed=True
            ) / 10


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
    
    def notification_indicate(self, sender, data):
        print(f"Indicate received: {data}")
        if not self.indicate.done():
            self.indicate.set_result(data)


    async def connect_treadmill(self):
        """Connect to BLE treadmill and start notifications."""
        retries = 0
        while retries < self.max_retries:
            try:
                print(f"Attempting to connect to treadmill (Attempt {retries + 1}/{self.max_retries})...")
                async with BleakClient(self.address, timeout=10.0, loop=self.ble_loop) as client:
                    self.client = client
                    print("Connected successfully!")
                    #await client.start_notify(self.control_point_uuid, self.notification_indicate)
                    await client.start_notify(self.speed_characteristic_uuid, self.notification_handler)

                    # Keep the connection alive
                    try:
                        while True:
                            await asyncio.sleep(1)
                    except KeyboardInterrupt:
                        print("Stopping notifications...")
                        await client.stop_notify(self.speed_characteristic_uuid)
                        break
                return  # Successful connection; exit method
            except Exception as e:
                retries += 1
                print(f"Error connecting to treadmill: {e}")
                if retries < self.max_retries:
                    print("Retrying...")
                    await asyncio.sleep(2)  # Wait 2 seconds before retrying
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

    def disconnect(self):
        """Disconnect from the treadmill."""
        if self.client and self.client.is_connected:
            asyncio.run_coroutine_threadsafe(
                self.client.disconnect(),
                self.ble_loop
            )
            print("Disconnected from treadmill.")