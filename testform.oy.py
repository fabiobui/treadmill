from flask import Flask, request, redirect, url_for, render_template, flash
import logging

app = Flask(__name__)
app.secret_key = 'your_secure_secret_key'  # Replace with a secure secret key

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    return render_template('newindex.html')

@app.route('/set_speed', methods=['POST'])
def set_speed():
    """
    Endpoint to handle speed setting via HTML form submission.
    Expects form data with 'set_speed' field.
    """
    speed = request.form.get('set_speed')
    logger.info(f"Received speed: {speed}")

    if speed is None or speed.strip() == '':
        logger.error("Speed value is missing.")
        flash("Speed value is missing.", "error")
        return redirect(url_for('index'))
    else:
        try:
            speed_value = float(speed)
            logger.info(f"Setting speed to {speed_value} km/h...")
            # Add your speed setting logic here
            flash(f"Speed set to {speed_value} km/h successfully.", "success")
            return redirect(url_for('index'))
        except ValueError:
            logger.error("Invalid speed value provided.")
            flash("Invalid speed value provided.", "error")
            return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
