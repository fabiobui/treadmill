# testdb.py - test database
# App to test db connection local and remote

from flask import request, jsonify
from db_management import DBManagement, local_db, LocalSession

# 1) Instantiate the class
db_manager = DBManagement()

# For convenience, get references
app = db_manager.app


################################################################
# Routes
################################################################
@app.route('/add_session', methods=['POST'])
def add_session():
    """
    Save a new session in local DB, attempt immediate remote sync.
    Body example (if we store "datetime" as "YYYY-MM-DD HH:MM:SS"):
      {
        "datetime": "2025-01-01 11:30:00",
        "km": 10,
        "elapsed": 3600,
        "avg_speed": 2.7,
        "avg_bpm": 100
      }
    """
    data = request.get_json() or {}
    required_fields = ['datetime', 'km', 'elapsed', 'avg_speed', 'avg_bpm']
    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    
    return db_manager.save_local_session(data)


@app.route('/sessions', methods=['GET'])
def list_sessions():
    """
    Returns all local sessions (SQLite), showing which ones need sync.
    """
    results = db_manager.list_local_sessions()
    return jsonify(results), 200

################################################################
# Run the Flask App
################################################################
if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', debug=True)
    finally:
        db_manager.shutdown()
        print("Scheduler shut down.")