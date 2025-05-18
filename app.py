from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__, static_folder='.')
CORS(app)

def init_db():
    conn = sqlite3.connect('carehome.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS care_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_name TEXT NOT NULL,
            item_index INTEGER NOT NULL,
            item_text TEXT NOT NULL,
            UNIQUE(resident_name, item_index)
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/care-plans/<resident_name>', methods=['GET'])
def get_care_plan(resident_name):
    conn = sqlite3.connect('carehome.db')
    c = conn.cursor()
    c.execute('SELECT item_index, item_text FROM care_plans WHERE resident_name = ? ORDER BY item_index', (resident_name,))
    items = c.fetchall()
    conn.close()
    
    return jsonify({
        'title': f"{resident_name.title()} - Care Plan",
        'items': [item[1] for item in sorted(items, key=lambda x: x[0])]
    })

@app.route('/api/care-plans/<resident_name>', methods=['POST'])
def update_care_plan(resident_name):
    data = request.json
    item_index = data.get('index')
    item_text = data.get('text')
    
    conn = sqlite3.connect('carehome.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO care_plans (resident_name, item_index, item_text)
        VALUES (?, ?, ?)
    ''', (resident_name, item_index, item_text))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000) 
