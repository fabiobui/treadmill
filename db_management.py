# db_management.py
# One file that manages everything: config, models, and sync logic in a DBManagement class.

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import traceback

########################################################################
# 1. Configuration
########################################################################

class SQLiteConfig:
    # Local SQLite config
    SQLALCHEMY_DATABASE_URI = 'sqlite:///ftms.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class MySQLConfig:
    # Replace user, password, host, db_name with your MySQL credentials
    SQLALCHEMY_DATABASE_URI = 'mysql+mysqlconnector://Sql1818353:Gagagaga0761!@31.11.39.178/Sql1818353_4'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

########################################################################
# 2. Two SQLAlchemy Instances
########################################################################

local_db = SQLAlchemy()
remote_db = SQLAlchemy()

########################################################################
# 3. Models
########################################################################

class LocalSession(local_db.Model):
    __tablename__ = 'sessions'
    id = local_db.Column(local_db.Integer, primary_key=True)
    datetime = local_db.Column(local_db.String, nullable=False)
    km = local_db.Column(local_db.Integer, default=0)
    elapsed = local_db.Column(local_db.Integer, default=0)
    avg_speed = local_db.Column(local_db.Float, default=0.0)
    avg_bpm = local_db.Column(local_db.Float, default=0.0)
    kcal = local_db.Column(local_db.Integer, default=0)
    needs_sync = local_db.Column(local_db.Boolean, default=True)

class RemoteSession(remote_db.Model):
    __tablename__ = 'sessions'
    id = remote_db.Column(remote_db.Integer, primary_key=True)
    datetime = remote_db.Column(remote_db.DateTime, nullable=False)
    km = remote_db.Column(remote_db.Integer, default=0)
    elapsed = remote_db.Column(remote_db.Integer, default=0)
    avg_speed = remote_db.Column(remote_db.Float, default=0.0)
    avg_bpm = remote_db.Column(remote_db.Float, default=0.0)
    kcal = remote_db.Column(remote_db.Integer, default=0)

########################################################################
# 4. DBManagement Class
########################################################################

class DBManagement:
    """
    This single class sets up both local and remote Flask apps,
    initializes the databases, starts APScheduler,
    and contains the sync logic (parse_local_datetime, sync_session, etc.).
    """

    def __init__(self):
        # -------------------------
        # Create the local (SQLite) Flask app
        # -------------------------
        self.app = Flask(__name__)
        self.app.config.from_object(SQLiteConfig)
        local_db.init_app(self.app)

        # -------------------------
        # Create the remote (MySQL) Flask app
        # -------------------------
        self.remote_app = Flask(__name__)
        self.remote_app.config.from_object(MySQLConfig)
        remote_db.init_app(self.remote_app)

        # -------------------------
        # Initialize local DB
        # -------------------------
        with self.app.app_context():
            local_db.create_all()  # Creates tables for LocalSession if not existing

        # -------------------------
        # Start a background scheduler
        # -------------------------
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

        print("[DBManagement] Initialization complete.")

    def parse_local_datetime(self, dt_str):
        """
        Convert a local string (e.g. "2025-01-01 11:30:00" or "01/01/2025 11:30")
        into a Python datetime object.

        Adjust the format string to match how you store datetime in the local DB.
        """
        # Example format: "YYYY-MM-DD HH:MM:SS"
        format_str = "%Y-%m-%d %H:%M:%S"
        return datetime.datetime.strptime(dt_str, format_str)
    
    def save_local_session(self, data):
        """
        Save a new session in local DB, attempt immediate remote sync.
       """

        with self.app.app_context():
            new_sess = LocalSession(
                datetime=data['datetime'],  # stored as TEXT
                km=data['km'],
                elapsed=data['elapsed'],
                avg_speed=data['avg_speed'],
                avg_bpm=data['avg_bpm'],
                kcal=data['kcal'],
                needs_sync=True
            )
            local_db.session.add(new_sess)
            local_db.session.commit()

            created_id = new_sess.id

        try:
            self.sync_session(created_id)
        except Exception as e:
            print("[IMMEDIATE SYNC ERROR]", e)
            return {        
                "message": "Session saved locally. Immediate sync failed.",
                "id": new_sess.id
            }, 500

        return {
            "message": "Session saved locally. Sync attempted.",
            "id": new_sess.id
        }, 201

    def list_local_sessions(self):
        """
        Returns all local sessions (SQLite), showing which ones need sync.
        """
        with self.app.app_context():
            sessions = LocalSession.query.all()
            results = []
            for s in sessions:
                results.append({
                    "id": s.id,
                    "datetime": s.datetime,
                    "km": s.km,
                    "elapsed": s.elapsed,
                    "avg_speed": s.avg_speed,
                    "avg_bpm": s.avg_bpm,
                    "kcal": s.kcal,
                    "needs_sync": s.needs_sync
                })
        return results


    def sync_session(self, session_id):
        """
        Attempt to sync a single local session (SQLite) to the remote (MySQL).
        If success, mark needs_sync=False locally.
        If fail, handle error (or schedule a retry).
        """
        with self.app.app_context():
            local_session = local_db.session.get(LocalSession, session_id)
            if not local_session:
                print(f"[SYNC ERROR] session {session_id} not found locally.")
                return

            try:
                # Sync with remote DB in its own context
                with self.remote_app.app_context():
                    remote_session = remote_db.session.get(RemoteSession, session_id)
                    if not remote_session:
                        remote_session = RemoteSession(id=session_id)

                    # Convert local TEXT datetime into Python datetime
                    dt_obj = self.parse_local_datetime(local_session.datetime)

                    remote_session.datetime = dt_obj
                    remote_session.km = local_session.km
                    remote_session.elapsed = local_session.elapsed
                    remote_session.avg_speed = local_session.avg_speed
                    remote_session.avg_bpm = local_session.avg_bpm
                    remote_session.kcal = local_session.kcal

                    remote_db.session.add(remote_session)
                    remote_db.session.commit()

                # Mark local item as synced
                local_session.needs_sync = False
                local_db.session.commit()
                print(f"[SYNC SUCCESS] session {session_id} synced to remote.")

            except Exception as e:
                print(f"[SYNC FAILED] session {session_id}: {e}")
                traceback.print_exc()
                # Optionally schedule a one-time retry job here if needed
                # e.g., self.scheduler.add_job(...)

    def shutdown(self):
        """Graceful shutdown of the scheduler (if needed)."""
        self.scheduler.shutdown()
        print("[DBManagement] Scheduler shut down.")
