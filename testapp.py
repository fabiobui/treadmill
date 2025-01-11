# testapp.py
# Testing app that emulates a bluetooth treadmill
# Tha app call the TreadmillSimulate class in ble_treadmill.py

import time
import threading
from ble_treadmill import TreadmillSimulate

def main():
    treadmill = TreadmillSimulate(device_name="ORANGE-PI3-ZERO")

    # We'll run the treadmill server in its own thread,
    # so we can keep updating measures from this main thread.
    server_thread = threading.Thread(target=treadmill.start, daemon=True)
    server_thread.start()

    try:
        i = 0
        while True:
            # Example: ramp up speed, distance, energy
            speed    = 10   # ~3 km/h + some offset
            distance = i * 2.0           # 2m per iteration
            energy   = i * 5
            bpm = 105
            elapsed  = i

            # Update treadmill data
            treadmill.set_measures(
                speed_m_s=speed,
                distance_m=distance,
                energy=energy,
                bpm=bpm,
                elapsed_s=elapsed
            )

            print(f"[Main] Setting measures: speed={speed:.2f}, dist={distance}, energy={energy}, bpm={bpm}, time={elapsed}")
            i += 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("Caught Ctrl+C in main loop.")
    finally:
        treadmill.stop()
        server_thread.join()
        print("Main app done.")

if __name__ == "__main__":
    main()
