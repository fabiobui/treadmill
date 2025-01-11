import asyncio
from bleak import BleakClient
from flask import Flask, Response, jsonify, render_template
import threading
import time
import json

app = Flask(__name__)


# Shared data
data_stream = {"speed": 0.0, "pace": "0:00", "distance": 0, "average_speeds": [], "running_time": 0}
last_update = time.time()
running_start_time = None

async def generate_data():
    while True:
        await asyncio.sleep(1)
        data_stream["speed"] = round(time.time() % 10, 2)
        data_stream["pace"] = f"{int(time.time() % 10)}:00"
        data_stream["distance"] += time.time() % 10 / 3600
        data_stream["running_time"] += 1
        await asyncio.sleep(1)

def start_loop():
    """Run in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(generate_data())



\
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data_stream')
def stream():
    """Stream treadmill data as Server-Sent Events (SSE)."""
    def event_stream():
        while True:
            time.sleep(1)
            yield f"data: {data_stream}\n\n"
    return Response(event_stream(), content_type='text/event-stream')


@app.route('/data_stream_json')
def stream_json():
    """Stream treadmill data as pure JSON."""
    def event_stream_json():
        while True:
            time.sleep(1)
            yield json.dumps(data_stream) + "\n" # Send pure JSON
    return Response(event_stream_json(), content_type='text/event-stream')


@app.route('/api/treadmill_data', methods=['GET'])
def get_treadmill_data():
    """API endpoint to return treadmill data as JSON."""
    return jsonify(data_stream)


if __name__ == '__main__':
    threading.Thread(target=start_loop, daemon=True).start()
    app.run(host='0.0.0.0', debug=True, threaded=True)
