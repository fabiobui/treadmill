# app.py
# Complete App that emulates a treadmill bluetooth device and
# connects to a real treadmill device
# All data are sent to a Flask endpoint

import threading
import time
import json
import os
import subprocess
#import webview
import paho.mqtt.client as mqtt

from flask import Flask, Response, request, redirect, url_for, jsonify, render_template

from db_management import DBManagement

# Import your TreadmillSimulate as before
from ble_treadmill import TreadmillSimulate

# Import the new BLEConnection class
from ble_connection import BLEConnection


# Load the JSON file
with open("config.json", "r") as file:
    config = json.load(file)

# Access BLE-related settings from the "Settings" section
settings = config["Settings"]
limits = config["Limits"]
mqtt_settings = config["MQTT"]

# Access MQTT settings
mqtt_broker = mqtt_settings["server"]
mqtt_port = mqtt_settings["port"]
mqtt_topic = mqtt_settings["topic"]
mqtt_message = mqtt_settings["message"]

app = Flask(__name__)


# Instantiate the class
db_manager = DBManagement(config["Database"])

client = mqtt.Client()

# Set environment variables from the JSON file
env_vars = config["EnvironmentVariables"]
os.environ["PATH"] += f":{env_vars['PATH']}"  # Append to PATH
os.environ["DISPLAY"] = env_vars["DISPLAY"]   # Set DISPLAY
os.environ["XAUTHORITY"] = env_vars["XAUTHORITY"]  # Set XAUTHORITY

# Create a Flask app

# Instantiate your treadmill simulator
treadmill = TreadmillSimulate(device_name=settings["device_name"])


# Instantiate the BLEConnection class using values from the config
ble_connection = BLEConnection(
    treadmill=treadmill,  # Assuming treadmill is already defined in your code
    db_manager=db_manager,
    address=settings["address"],
    speed_characteristic_uuid=settings["speed_characteristic_uuid"],
    control_point_uuid=settings["control_point_uuid"],
    max_retries=settings["max_retries"],
    limits=limits
)

temp_average = {
    "speed": [],
    "bpm": []
}

# Create an API class that will be exposed to JavaScript
class API:
    def close_window(self):
        # Use the reference to the window (stored globally or passed in)
        global window
        if window:
            window.destroy()


@app.route('/')
def index():
    return render_template('newindex.html')

@app.route('/api/treadmill_data', methods=['GET'])
def get_treadmill_data():
    """API endpoint to return treadmill data as JSON."""
    speed = float(ble_connection.data_stream["speed"])
    bpm = int(ble_connection.data_stream["bpm"])
    if (speed > 0): 
        temp_average["speed"].append(speed)   
    if (bpm > 0):
        temp_average["bpm"].append(bpm) 
    # Access the data_stream from our ble_connection instance
    return jsonify(ble_connection.data_stream)


@app.route('/save_session', methods=['POST'])
def save_session():  
    avg_speed = sum(temp_average["speed"]) / len(temp_average["speed"]) if len(temp_average["speed"]) > 0 else 0
    avg_bpm = sum(temp_average["bpm"]) / len(temp_average["bpm"]) if len(temp_average["bpm"]) > 0 else 0
    data = {
        "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
        "km": int(ble_connection.data_stream["distance"]*1000),
        "elapsed": ble_connection.data_stream["running_time"],
        "avg_speed": avg_speed,
        "avg_bpm": avg_bpm,
        "kcal": ble_connection.data_stream["energy"]
    }
    db_manager.save_local_session(data)
    temp_average["speed"].clear()
    temp_average["bpm"].clear()
    return redirect(url_for('index'))


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
        #ble_connection.send_speed(speed)
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Failed to set speed: {e}")
    

@app.route("/exit_kiosk")
def exit_kiosk():
    # Kills all chromium processes, effectively exiting kiosk mode
    import os
    os.system("pkill chromium")
    return "Exited kiosk by killing chromium!"

@app.route('/screen_off', methods=['POST'])
def screen_off():
    os.system("xset dpms force off")
    return redirect(url_for('index'))

@app.route('/shutdown', methods=['POST'])
def shutdown():
    try:
        # Initialize MQTT client
        client = mqtt.Client()
        client.connect(mqtt_broker, mqtt_port)
        print("Connected to MQTT broker successfully.")
        client.publish(mqtt_topic, mqtt_message)
        print(f"Message published to topic '{mqtt_topic}': {mqtt_message}")

        # Disconnect from the broker
        client.disconnect()
        print("Disconnected from MQTT broker.")

    except Exception as e:
        print(f"An error occurred: {e}")
        time.sleep(5)  # Wait for 5 seconds before shutting down
        return redirect(url_for('index'))

    os.system("sudo shutdown now")  # Send shutdown command
    return "Server shutting down..."


def reset_bluetooth():
    print("Resetting Bluetooth interface...")
    os.system("rfkill block bluetooth")
    os.system("rfkill unblock bluetooth")

def start_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

##############
#   MAIN APP
##############

if __name__ == '__main__':
    try:
        print("Starting BLE connection...")
        reset_bluetooth()

        # Start BLE connection loop in a separate daemon thread
        ble_thread = threading.Thread(target=ble_connection.start_ble_loop, daemon=True)
        ble_thread.start()

        # Start the treadmill server in its own thread
        server_thread = threading.Thread(target=treadmill.start, daemon=True)
        server_thread.start()

        # Start the Flask API     
        print("Starting Flask API...")
        # Start Flask in a separate thread
        api = API()
        flask_thread = threading.Thread(target=start_flask, daemon=True)
        flask_thread.start()

        # Create a PyWebView window
        #window = webview.create_window(
        #    title='PyWebView App - Kiosk Mode',
        #    url='http://127.0.0.1:5000',
        #    js_api=api,
        #    fullscreen=True,
        #    frameless=True
        #)
        #webview.start()        

    except KeyboardInterrupt:
        print("Shutting down...")

    finally:
        #if window:
        #    window.destroy()
        db_manager.shutdown()
        treadmill.stop()
        server_thread.join()
        # Stop the asyncio loop & join the BLE thread
        ble_connection.disconnect()
        #ble_connection.ble_loop.stop()
        ble_connection.disconnect()
        ble_thread.join()
        print("Main app done.")
