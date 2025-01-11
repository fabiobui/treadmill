# fake_treamill.py
# app to simulate a treadmill device

import threading
import time
import os
import subprocess



# Import your TreadmillSimulate as before
from ble_treadmill import TreadmillSimulate


# Instantiate your treadmill simulator
treadmill = TreadmillSimulate(device_name="ORANGE-PI3-ZERO")

def generate_data():
    distance = 0.0
    elapsed_time = 0
    energy = 0
    while True:
        # Generate some data
        distance += 0.1
        elapsed_time += 1
        energy += 1
        data = {
            "speed_m_s": 15,
            "distance": distance,
            "energy": energy,
            "bpm": 100,
            "elapsed_s": elapsed_time
        }
        #def set_measures(self, speed_m_s=None, distance_m=None, energy=None, bpm=None, elapsed_s=None):

        # Update the treadmill data
        treadmill.set_measures(data)
        time.sleep(1.0)

    
def reset_bluetooth():
    print("Resetting Bluetooth interface...")
    os.system("rfkill block bluetooth")
    os.system("rfkill unblock bluetooth")

if __name__ == '__main__':
    try:
        print("Starting BLE connection...")
        reset_bluetooth()


        # Start the treadmill server in its own thread
        server_thread = threading.Thread(target=treadmill.start, daemon=True)
        server_thread.start()

        generate_data()

        # Start the Flask API
        print("Starting ...")

    except KeyboardInterrupt:
        print("Shutting down...")

    finally:
        treadmill.stop()
        server_thread.join()
        print("Main app done.")
