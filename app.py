from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import sqlite3
import tempfile
import logging
import traceback
import base64
import shutil
import threading
import time
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='.')
CORS(app)

# Global variables for caching
_db_path = None
_last_sync = None
_sync_interval = 300  # 5 minutes in seconds
_lock = threading.Lock()

def ensure_data_directories():
    """Ensure all required data directories exist."""
    try:
        # Create main data directory
        data_dir = '/tmp/data'
        os.makedirs(data_dir, exist_ok=True)
        logger.info(f"Created/verified data directory: {data_dir}")
        
        # Create profile photos directory
        photos_dir = os.path.join(data_dir, 'profile_photos')
        os.makedirs(photos_dir, exist_ok=True)
        logger.info(f"Created/verified profile photos directory: {photos_dir}")
        
        return data_dir
    except Exception as e:
        logger.error(f"Error creating directories: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def get_db_path():
    global _db_path
    try:
        if _db_path is None:
            # Ensure data directories exist
            data_dir = ensure_data_directories()
            _db_path = os.path.join(data_dir, 'carehome.db')
            logger.info(f"Database path: {_db_path}")
            
            # Initialize database if it doesn't exist
            if not os.path.exists(_db_path):
                logger.info("Database file does not exist, initializing new database")
                init_db()
            else:
                logger.info("Database file exists at: %s", _db_path)
                # Verify database connection
                try:
                    conn = sqlite3.connect(_db_path)
                    c = conn.cursor()
                    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='care_plans'")
                    if not c.fetchone():
                        logger.warning("care_plans table does not exist, reinitializing database")
                        init_db()
                    else:
                        logger.info("Database connection successful and care_plans table exists")
                    conn.close()
                except Exception as e:
                    logger.error(f"Error verifying database: {str(e)}")
                    logger.error(traceback.format_exc())
                    logger.info("Reinitializing database due to verification error")
                    init_db()
        return _db_path
    except Exception as e:
        logger.error(f"Error in get_db_path: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def get_db_connection():
    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Error creating database connection: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Create care_plans table
        c.execute('''
            CREATE TABLE IF NOT EXISTS care_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resident_name TEXT NOT NULL,
                item_index INTEGER NOT NULL,
                item_text TEXT NOT NULL,
                UNIQUE(resident_name, item_index)
            )
        ''')
        
        # Insert sample data if the table is empty
        c.execute('SELECT COUNT(*) FROM care_plans')
        if c.fetchone()[0] == 0:
            logger.info("Inserting sample care plan data")
            sample_data = [
                # Mary's care plan
                ('mary', 0, 'Morning medication at 7 AM'),
                ('mary', 1, 'Breakfast at 7:30 AM'),
                ('mary', 2, 'Morning exercise at 10 AM'),
                ('mary', 3, 'Lunch at 12 PM'),
                ('mary', 4, 'Afternoon rest period'),
                ('mary', 5, 'Evening medication at 6 PM'),
                ('mary', 6, 'Dinner at 6:30 PM'),
                
                # John's care plan
                ('john', 0, 'Morning medication at 8 AM'),
                ('john', 1, 'Breakfast at 8:30 AM'),
                ('john', 2, 'Morning exercise at 10 AM'),
                ('john', 3, 'Music therapy at 11 AM'),
                ('john', 4, 'Lunch at 12:30 PM'),
                ('john', 5, 'Afternoon walk at 2 PM'),
                ('john', 6, 'Evening medication at 6 PM'),
                
                # Linda's care plan
                ('linda', 0, 'Blood pressure check at 9 AM'),
                ('linda', 1, 'Physical therapy at 11 AM'),
                ('linda', 2, 'Lunch at 12 PM'),
                ('linda', 3, 'Painting session at 2 PM'),
                ('linda', 4, 'Evening medication at 5 PM'),
                ('linda', 5, 'Dinner at 5:30 PM'),
                
                # Jack's care plan
                ('jack', 0, 'Medication with breakfast'),
                ('jack', 1, 'Oxygen level check at 10 AM'),
                ('jack', 2, 'Afternoon walk at 2 PM'),
                ('jack', 3, 'Evening medication at 6 PM'),
                ('jack', 4, 'Dinner at 6:30 PM'),
                ('jack', 5, 'Oxygen level check at 8 PM')
            ]
            c.executemany('INSERT INTO care_plans (resident_name, item_index, item_text) VALUES (?, ?, ?)', sample_data)
            logger.info("Sample data inserted successfully")
        
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        logger.error(traceback.format_exc())
        raise
    finally:
        conn.close()

def get_profile_photo(resident_name):
    try:
        # Check if profile photo exists in local storage
        photo_path = os.path.join('/tmp/data/profile_photos', f'{resident_name.lower()}.jpg')
        logger.info(f"Looking for profile photo at: {photo_path}")
        if os.path.exists(photo_path):
            # Read and encode the image
            with open(photo_path, 'rb') as f:
                image_data = f.read()
            logger.info(f"Found profile photo for {resident_name}")
            return base64.b64encode(image_data).decode('utf-8')
        else:
            logger.warning(f"No profile photo found for {resident_name} at {photo_path}")
            return None
    except Exception as e:
        logger.error(f"Error getting profile photo for {resident_name}: {str(e)}")
        logger.error(traceback.format_exc())
        return None

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/care-plans/<resident_name>', methods=['GET'])
def get_care_plan(resident_name):
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"[{current_time}] Starting to fetch care plan for resident: {resident_name}")
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # First, check if the table exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='care_plans'")
        if not c.fetchone():
            logger.warning(f"[{current_time}] care_plans table does not exist, initializing database")
            init_db()
        
        # Then fetch the care plan items
        c.execute('SELECT item_index, item_text FROM care_plans WHERE resident_name = ? ORDER BY item_index', (resident_name.lower(),))
        items = c.fetchall()
        logger.info(f"[{current_time}] Found {len(items)} care plan items for {resident_name}")
        
        # If no items found, create a default care plan
        if not items:
            logger.info(f"[{current_time}] No care plan found for {resident_name}, creating default plan")
            default_items = [
                (0, f'Morning medication for {resident_name.title()}'),
                (1, f'Breakfast for {resident_name.title()}'),
                (2, f'Daily activities for {resident_name.title()}')
            ]
            c.executemany('INSERT INTO care_plans (resident_name, item_index, item_text) VALUES (?, ?, ?)',
                         [(resident_name.lower(), idx, text) for idx, text in default_items])
            conn.commit()
            items = default_items
            logger.info(f"[{current_time}] Created default care plan for {resident_name}")
        
        # Debug: Print the actual items
        for item in items:
            logger.info(f"[{current_time}] Care plan item: index={item[0]}, text={item[1]}")
        
        # Get profile photo
        profile_photo = get_profile_photo(resident_name)
        if profile_photo:
            logger.info(f"[{current_time}] Found profile photo for {resident_name}")
        else:
            logger.warning(f"[{current_time}] No profile photo found for {resident_name}")
        
        response_data = {
            'title': f"{resident_name.title()} - Care Plan",
            'items': [item[1] for item in sorted(items, key=lambda x: x[0])],
            'profile_photo': profile_photo
        }
        logger.info(f"[{current_time}] Successfully prepared response for {resident_name}")
        return jsonify(response_data)
    except Exception as e:
        error_msg = f"Error loading care plan at {current_time}. Please try again."
        logger.error(f"[{current_time}] Error fetching care plan for {resident_name}: {str(e)}")
        logger.error(f"[{current_time}] Traceback: {traceback.format_exc()}")
        return jsonify({'error': error_msg, 'traceback': traceback.format_exc()}), 500
    finally:
        if 'conn' in locals():
            conn.close()
            logger.info(f"[{current_time}] Database connection closed")

@app.route('/api/care-plans/<resident_name>', methods=['POST'])
def update_care_plan(resident_name):
    data = request.json
    item_index = data.get('index')
    item_text = data.get('text')
    
    logger.info(f"Updating care plan for {resident_name}: index={item_index}, text={item_text}")
    
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO care_plans (resident_name, item_index, item_text)
            VALUES (?, ?, ?)
            ON CONFLICT (resident_name, item_index) 
            DO UPDATE SET item_text = excluded.item_text
        ''', (resident_name.lower(), item_index, item_text))
        conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating care plan: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

if __name__ == '__main__':
    # Initialize database if not in production
    if os.environ.get('FLASK_ENV') != 'production':
        init_db()
    
    # Get port from environment variable or default to 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port) 
