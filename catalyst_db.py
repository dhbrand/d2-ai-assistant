import sqlite3
import json
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CatalystDB:
    def __init__(self, db_path: str = "catalysts.db"):
        """Initialize the database connection"""
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """Initialize the database schema"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create catalysts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS catalysts (
                    record_hash INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    icon TEXT,
                    weapon_type TEXT,
                    last_updated TIMESTAMP,
                    data JSON
                )
            """)
            
            # Create objectives table for normalized storage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS objectives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_hash INTEGER,
                    description TEXT,
                    progress INTEGER,
                    completion INTEGER,
                    complete BOOLEAN,
                    last_updated TIMESTAMP,
                    FOREIGN KEY (record_hash) REFERENCES catalysts(record_hash)
                )
            """)
            
            # Create manifest definitions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS definitions (
                    hash INTEGER PRIMARY KEY,
                    table_name TEXT NOT NULL,
                    data JSON,
                    last_updated TIMESTAMP
                )
            """)
            
            # Create metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    last_updated TIMESTAMP
                )
            """)
            
            conn.commit()
    
    def store_catalyst(self, catalyst_data: Dict):
        """Store or update a catalyst record"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            record_hash = catalyst_data['recordHash']
            now = datetime.now()
            
            # Store main catalyst data
            cursor.execute("""
                INSERT OR REPLACE INTO catalysts 
                (record_hash, name, description, icon, weapon_type, last_updated, data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                record_hash,
                catalyst_data['name'],
                catalyst_data.get('description', ''),
                catalyst_data.get('icon', ''),
                catalyst_data.get('weaponType', 'Unknown'),
                now,
                json.dumps(catalyst_data)
            ))
            
            # Store objectives
            cursor.execute("DELETE FROM objectives WHERE record_hash = ?", (record_hash,))
            for obj in catalyst_data.get('objectives', []):
                cursor.execute("""
                    INSERT INTO objectives 
                    (record_hash, description, progress, completion, complete, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    record_hash,
                    obj['description'],
                    obj['progress'],
                    obj['completion'],
                    obj['complete'],
                    now
                ))
            
            conn.commit()
    
    def get_catalyst(self, record_hash: int) -> Optional[Dict]:
        """Retrieve a catalyst by its record hash"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get main catalyst data
            cursor.execute("SELECT data FROM catalysts WHERE record_hash = ?", (record_hash,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            catalyst_data = json.loads(row[0])
            
            # Get objectives
            cursor.execute("""
                SELECT description, progress, completion, complete 
                FROM objectives 
                WHERE record_hash = ?
            """, (record_hash,))
            
            objectives = []
            for obj_row in cursor.fetchall():
                objectives.append({
                    'description': obj_row[0],
                    'progress': obj_row[1],
                    'completion': obj_row[2],
                    'complete': obj_row[3]
                })
            
            catalyst_data['objectives'] = objectives
            return catalyst_data
    
    def get_all_catalysts(self) -> List[Dict]:
        """Retrieve all stored catalysts"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT record_hash FROM catalysts")
            hashes = cursor.fetchall()
            
            return [self.get_catalyst(h[0]) for h in hashes if h[0]]
    
    def store_definition(self, table_name: str, hash_id: int, data: Dict):
        """Store a manifest definition"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO definitions 
                (hash, table_name, data, last_updated)
                VALUES (?, ?, ?, ?)
            """, (hash_id, table_name, json.dumps(data), datetime.now()))
            conn.commit()
    
    def get_definition(self, table_name: str, hash_id: int) -> Optional[Dict]:
        """Retrieve a manifest definition"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT data, last_updated 
                FROM definitions 
                WHERE hash = ? AND table_name = ?
            """, (hash_id, table_name))
            
            row = cursor.fetchone()
            if not row:
                return None
                
            data, last_updated = row
            # Check if definition is older than 24 hours
            if datetime.now() - datetime.fromisoformat(last_updated) > timedelta(hours=24):
                return None
                
            return json.loads(data)
    
    def set_last_sync(self, timestamp: datetime = None):
        """Set the last sync timestamp"""
        if timestamp is None:
            timestamp = datetime.now()
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO metadata 
                (key, value, last_updated)
                VALUES (?, ?, ?)
            """, ('last_sync', timestamp.isoformat(), timestamp))
            conn.commit()
    
    def get_last_sync(self) -> Optional[datetime]:
        """Get the last sync timestamp"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = ?", ('last_sync',))
            row = cursor.fetchone()
            
            if row:
                return datetime.fromisoformat(row[0])
            return None
    
    def needs_sync(self, max_age_hours: int = 1) -> bool:
        """Check if data needs to be synced based on age"""
        last_sync = self.get_last_sync()
        if not last_sync:
            return True
            
        age = datetime.now() - last_sync
        return age > timedelta(hours=max_age_hours)
    
    def clear_old_data(self, max_age_days: int = 7):
        """Clear data older than specified days"""
        threshold = datetime.now() - timedelta(days=max_age_days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM catalysts WHERE last_updated < ?", (threshold,))
            cursor.execute("DELETE FROM objectives WHERE last_updated < ?", (threshold,))
            cursor.execute("DELETE FROM definitions WHERE last_updated < ?", (threshold,))
            
            conn.commit() 