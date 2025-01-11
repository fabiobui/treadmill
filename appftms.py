# app.py
# Complete App that emulates a treadmill bluetooth device and
# connects to a real treadmill device
# All data are sent to a Flask endpoint

import threading
import time
import json
import os
import subprocess
import logging
import asyncio

from pyftms import FitnessMachine, FtmsEvents, get_client_from_address
from flask import Flask, Response, request, redirect, url_for, jsonify, render_template

# Import your TreadmillSimulate as before
#from ble_treadmill import TreadmillSimulate


logging.basicConfig(level=logging.ERROR)

_LOGGER = logging.getLogger(__name__)

ADDRESS = "FF:71:4E:77:4B:DB"

ble_loop = None


app = Flask(__name__)


# Set environment variables
os.environ['PATH'] += ':/usr/bin'  # Adjust if wmctrl is in a different path
os.environ['DISPLAY'] = ':0'        # Set DISPLAY if not already set
os.environ['XAUTHORITY'] = '/home/orangepi/.Xauthority'  # Replace with actual path


# Instantiate your treadmill simulator
#treadmill = TreadmillSimulate(device_name="ORANGE-PI3-ZERO")

@app.route('/')
def index():
    return render_template('newindex.html')

data_stream = {
    'speed': 3.0,
    'incline': 0.0,
    'bpm': 90,
    'elapsed_time': 0,
    'distance': 0.0,
    'energy': 0.0,
    'status': 'stopped'
}   

@app.route('/api/treadmill_data', methods=['GET'])
def get_treadmill_data():
    """API endpoint to return treadmill data as JSON."""
    # Access the data_stream from our ble_connection instance
    return jsonify(data_stream)


@app.route('/set_speed', methods=['POST'])
def set_speed():
    """
    Endpoint to handle speed setting via HTML form submission.
    Expects form data with 'speed' field.
    """
    speed = request.form.get('set_speed')
    print(f"Setting speed to {speed} km/h...")

    if speed is None:
        print("Speed value is missing.")

    try:
        speed = float(speed)
        if speed < 0:
            raise ValueError("Speed cannot be negative.")
    except (ValueError, TypeError) as e:
        return print(f"Invalid speed value: {e}")

    # Optional: Define maximum speed limit
    MAX_SPEED_KMH = 16.0  # Example maximum speed
    if speed > MAX_SPEED_KMH:
        print(f"Speed exceeds maximum limit of {MAX_SPEED_KMH} km/h.")

    # Send speed to the BLE treadmill
    try:
        ble_connection.send_speed(speed)
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Failed to set speed: {e}")
    

@app.route('/screen_off', methods=['POST'])
def screen_off():
    os.system("xset dpms force off")
    return redirect(url_for('index'))

@app.route('/shutdown', methods=['POST'])
def shutdown():
    os.system("sudo shutdown now")  # Send shutdown command
    return "Server shutting down..."


@app.route('/exit_kiosk', methods=['POST'])
def exit_kiosk():
    try:
        # Use wmctrl to list windows and find Chromium
        result = subprocess.run(['wmctrl', '-lx'], capture_output=True, text=True, check=True)
        windows = result.stdout.splitlines()

        # Filter Chromium windows based on window class
        chromium_windows = [w for w in windows if 'chromium' in w.lower() or 'chrome' in w.lower()]

        if not chromium_windows:
            return jsonify({'status': 'error', 'message': 'Chromium window not found.'}), 404

        # Assume the first Chromium window is the target
        window_id = chromium_windows[0].split()[0]

        # Remove the fullscreen state
        subprocess.run(['wmctrl', '-i', '-r', window_id, '-b', 'remove,fullscreen'], check=True)

        return jsonify({'status': 'success', 'message': 'Exited kiosk mode.'})

    except subprocess.CalledProcessError as e:
        return jsonify({'status': 'error', 'message': f'Command failed: {e}'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
def reset_bluetooth():
    print("Resetting Bluetooth interface...")
    os.system("rfkill block bluetooth")
    os.system("rfkill unblock bluetooth")



def on_event(event: FtmsEvents):
    print(f"Event received: {event}")


def on_disconnect(m: FitnessMachine):
    print("Fitness Machine disconnected.")

async def connect_treadmill():
    async with await get_client_from_address(
        ADDRESS, on_ftms_event=on_event, on_disconnect=on_disconnect
    ) as c:
        # Keep the connection alive
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Stopping notifications...")
            await c.stop()

def start_ble_loop():
    """Start the BLE connection loop in the current thread."""
    global ble_loop
    asyncio.set_event_loop(ble_loop)
    # Run the BLE coroutine until it's finished
    try:
        ble_loop.run_until_complete(connect_treadmill())
    finally:
        ble_loop.close()


if __name__ == '__main__':
    try:
        print("Starting BLE connection...")
        reset_bluetooth()

        # Start BLE connection loop in a separate daemon thread
        ble_thread = threading.Thread(target=start_ble_loop, daemon=True)
        ble_thread.start()

        # Start the treadmill server in its own thread
#        server_thread = threading.Thread(target=treadmill.start, daemon=True)
#        server_thread.start()

        # Start the Flask API
        print("Starting Flask API...")
        app.run(host='0.0.0.0', debug=False, threaded=True)

    except KeyboardInterrupt:
        print("Shutting down...")

    finally:
 #       treadmill.stop()
 #       server_thread.join()
        # Stop the asyncio loop & join the BLE thread 
        ble_loop.stop()    
        ble_thread.join()
        print("Main app done.")
