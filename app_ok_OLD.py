# app.py
# Complete App that emulate a treadmill bluetooth device and
# connect to real treadmill device
# All the data are sent to flask endpoint


import asyncio
from bleak import BleakClient
from flask import Flask, Response, redirect, url_for, jsonify, render_template
from ble_treadmill import TreadmillSimulate
import threading
import time
import json
import os

app = Flask(__name__)

# BLE device settings
TREADMILL_ADDRESS = "FF:71:4E:77:4B:DB"  # Replace with your treadmill's MAC address
SPEED_CHARACTERISTIC_UUID = "00002acd-0000-1000-8000-00805f9b34fb"  # Correct Handle 22 UUID
MAX_RETRIES = 5  # Maximum number of retries

treadmill = TreadmillSimulate(device_name="ORANGE-PI3-ZERO")

# Shared data
average = []
data_stream = {"speed": 0.0, "pace": "0:00", "distance": 0, "average_speeds": [], "running_time": 0, "energy" : 0, "bpm" : 0}
last_update = time.time()
running_start_time = None

# Shared BLE loop
ble_loop = asyncio.new_event_loop()

def convert_kmh_to_pace(speed_raw):
    """Convert speed in km/h to pace in min/km."""
    if speed_raw > 0:
        pace_min_km = 60 / (speed_raw / 100)
        minutes = int(pace_min_km)
        seconds = int((pace_min_km - minutes) * 60)
        return f"{minutes}:{seconds:02d}"
    return "0:00"


def decode_treadmill_data(value):
    """
    Decode treadmill speed data.
    Assumes speed is in bytes 2 and 3 (little-endian format), in cm/s.
    """
  
    speed_raw = int.from_bytes(value[2:4], byteorder="little", signed=False)
    data_stream["speed"] = speed_raw / 100  # kmh
    data_stream["pace"] = convert_kmh_to_pace(speed_raw)

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
    #print(f'> Speed {speed}')

    # Total distance
    if 'pos_tot_distance' in locals():
        distance = int.from_bytes(value[pos_tot_distance:pos_tot_distance + 2], byteorder='little')
        distance_complement = value[pos_tot_distance + 2] << 16
        distance += distance_complement
        data_stream["distance"] = distance / 1000
        total_km = int(data_stream["distance"])

        # Track average speed and pace for each km
        if len(data_stream["average_speeds"]) < total_km:
            print("total_km", total_km, "len(data_stream['average_speeds'])", len(data_stream["average_speeds"]))
            avg_speed = sum(average) / len(average)
            avg_pace = convert_kmh_to_pace(avg_speed)
            average.clear()
            data_stream["average_speeds"].append((avg_speed, avg_pace))
        else:
            average.append(data_stream["speed"])


    # Inclination
    if 'pos_inclination' in locals():
        inclination = int.from_bytes(value[pos_inclination:pos_inclination + 2], byteorder='little', signed=True) / 10
    #    print(f'> Inclination % {inclination}')

    # Calories
    if 'pos_kcal' in locals():
        kcal = int.from_bytes(value[pos_kcal:pos_kcal + 2], byteorder='little')
    #    print(f'> Kcal {kcal}')

    # Heart rate
    if 'pos_hr' in locals():
    #    print(f'> HR {value[pos_hr]}')
        data_stream["bpm"] = f"{value[pos_hr]}"

    # Elapsed time
    if 'pos_elapsed_time' in locals():
        elapsed_time = int.from_bytes(value[pos_elapsed_time:pos_elapsed_time + 2], byteorder='little')
        data_stream["running_time"] = elapsed_time 
    #    print(f'> Elapsed time {elapsed_time}')



def notification_handler(sender, data):
    """
    Callback to handle treadmill speed notifications.
    """
    global data_stream, last_update, running_start_time    
    try:
        decode_treadmill_data(data)
        treadmill.set_measures(
                speed_m_s=data_stream["speed"],
                distance_m=data_stream["distance"],
                energy=data_stream["energy"],
                bpm=data_stream["bpm"],
                elapsed_s=data_stream["running_time"]
        )
    except Exception as e:
        print(f"Error decoding data: {e}")
        print(f"Raw Data: {data}")


async def connect_treadmill():
    """Connect to BLE treadmill and start notifications."""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            print(f"Attempting to connect to treadmill (Attempt {retries + 1}/{MAX_RETRIES})...")
            async with BleakClient(TREADMILL_ADDRESS, timeout=10.0, loop=ble_loop) as client:
                print("Connected successfully!")
                await client.start_notify(SPEED_CHARACTERISTIC_UUID, notification_handler)

                # Keep the script alive
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    print("Stopping notifications...")
                    await client.stop_notify(SPEED_CHARACTERISTIC_UUID)
                    break  # Exit the loop gracefully
            return  # Exit the function if connection is successful
        except Exception as e:
            retries += 1
            print(f"Error connecting to treadmill: {e}")
            if retries < MAX_RETRIES:
                print("Retrying...")
                await asyncio.sleep(2)  # Wait 2 seconds before retrying
            else:
                print("Max retries reached. Unable to connect.")
                break


def start_ble_loop():
    """Start the BLE connection loop."""
    asyncio.set_event_loop(ble_loop)
    ble_loop.run_until_complete(connect_treadmill())

@app.route('/')
def index():
    return render_template('newindex.html')


@app.route('/api/treadmill_data', methods=['GET'])
def get_treadmill_data():
    """API endpoint to return treadmill data as JSON."""
    return jsonify(data_stream)


@app.route('/screen_off', methods=['POST'])
def screen_off():
    os.system("xset dpms force off")  # Command to turn off the screen
    return redirect(url_for('index'))  # Redirect back to the main page

# Route to shut down the server
@app.route('/shutdown', methods=['POST'])
def shutdown():
    os.system("sudo shutdown now")  # Send shutdown command to the operating system
    return "Server shutting down..."

def reset_bluetooth():
    print("Resetting Bluetooth interface...")
    os.system("rfkill block bluetooth")
    os.system("rfkill unblock bluetooth")


if __name__ == '__main__':
    # Start BLE connection in the main thread
    try:
        print("Starting BLE connection...")
        reset_bluetooth()
        ble_thread = threading.Thread(target=start_ble_loop, daemon=True)
        ble_thread.start()

        # We'll run the treadmill server in its own thread,
        # so we can keep updating measures from this main thread.
        server_thread = threading.Thread(target=treadmill.start, daemon=True)
        server_thread.start()

        # Start the Flask API
        print("Starting Flask API...")
        app.run(host='0.0.0.0', debug=True, threaded=True)

    except KeyboardInterrupt:
        print("Shutting down...")

    finally:
        treadmill.stop()
        server_thread.join()
        ble_loop.stop()
        ble_thread.join()
        print("Main app done.")