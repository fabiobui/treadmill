# app to test sending static data to
# html page

from flask import Flask, Response, jsonify, render_template
from threading import Thread
import time
import json
import webview


app = Flask(__name__)

# Mock data for the treadmill
data_stream = {
    "speed": 1.0,
    "pace": "60:00",
    "distance": 0.0538,
    "average_speeds": [],
    "running_time": 0
}

@app.route('/api/treadmill_data', methods=['GET'])
def get_treadmill_data():
    """API endpoint to return treadmill data as JSON."""
    return jsonify(data_stream)

@app.route('/')
def index():
    return render_template('newindex.html')

@app.route('/treadmill')
def treadmill():
    return render_template('ftms_treadmill.html')

def start_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

# Create an API class that will be exposed to JavaScript
class API:
    def close_window(self):
        # Use the reference to the window (stored globally or passed in)
        global window
        if window:
            window.destroy()

if __name__ == '__main__':
    # Start Flask in a separate thread
    api = API()
    thread = Thread(target=start_flask, daemon=True)
    thread.start()

    # Create a PyWebView window
    window = webview.create_window(
        title='PyWebView App - Kiosk Mode',
        url='http://127.0.0.1:5000',
        js_api=api,
        fullscreen=True,
        frameless=True
    )
    webview.start()