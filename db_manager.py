import json
import sqlite3
import os
import re

# --- 1. CONFIGURATION ---

DB_FILE = 'JEE_Master.db'
# IMPORTANT: All your final labeled JSON files (e.g., Alternating_Current_SMART.json) 
# must be in this directory.
DATA_DIR = 'JEE_Chapters_SMART' 

# JEE 2025 Weightage Data (Derived from user's input, normalized to 25 total Qs per paper)
# This will be used by the test_generator.py for the Balanced Mock Test.
JEE_2025_WEIGHTAGE = {
    "Units_Measurements": 1.37, "Vector_Algebra": 0.05, "Motion_in_a_Straight_Line": 0.37,
    "Motion_in_a_Plane": 0.63, "Circular_Motion": 0.47, "Laws_of_Motion": 0.37,
    "Work_Power_&_Energy": 0.68, "Center_of_Mass_and_Collision": 0.37, "Rotational_Motion": 1.37,
    "Properties_of_Matter": 1.68, "Heat_and_Thermodynamics": 2.63, "Simple_Harmonic_Motion": 0.58,
    "Waves": 0.58, "Gravitation": 0.68, "Semiconductor": 0.95,
    "Dual_Nature_of_Radiation": 1.11, "Atoms_and_Nuclei": 1.05, "Geometrical_Optics": 2.16,
    "Wave_Optics": 1.11, "Electromagnetic_Waves": 0.53, "Alternating_Current": 0.47,
    "Electromagnetic_Induction": 0.42, "Magnetic_Properties_of_Matter": 0.32, 
    "Magnetic_Effect_of_Current": 1.16, "Capacitor": 0.84, "Current_Electricity": 1.11, 
    "Electrostatics": 1.95 
}

def get_connection():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_FILE)

# --- 2. DATABASE SCHEMA DEFINITION (SQLITE) ---

def create_tables(conn):
    """Creates the three required tables in the database."""
    cursor = conn.cursor()

    # Table 1: Stores the static question data and labels
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            chapter TEXT NOT NULL,
            sub_topic TEXT NOT NULL,
            difficulty INTEGER NOT NULL,
            logic_type TEXT,
            physics_key TEXT,
            is_numerical BOOLEAN,
            question_text TEXT,
            options TEXT,
            answer TEXT,
            images TEXT         -- NEW: stores image URLs as JSON string
        );
    """)

    # Table 2: Stores every single attempt made by the user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS User_Logs (
            session_id TEXT NOT NULL,
            question_id INTEGER NOT NULL,
            result TEXT NOT NULL,  -- 'Correct', 'Wrong', 'Skipped'
            time_taken REAL,       -- Time in seconds
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (session_id, question_id),
            FOREIGN KEY (question_id) REFERENCES Questions(id)
        );
    """)

    # Table 3: Stores the calculated, adaptive performance metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Mastery_Scores (
            sub_topic TEXT PRIMARY KEY NOT NULL,
            accuracy REAL DEFAULT 0.0,
            avg_time REAL DEFAULT 0.0,
            mastery_score REAL DEFAULT 0.0,
            next_review_date DATETIME 
        );
    """)
    conn.commit()
    print(f"Created/Verified database tables in {DB_FILE}")


# --- 3. DATA CLEANUP AND INSERTION ---

def clean_chapter_name(filename):
    """Extracts the clean chapter name from the filename."""
    name = filename.replace('_SMART.json', '')
    # Handle the 'Syllabus_Reduced' appendix if it exists
    name = re.sub(r'Syllabus_Reduced', '', name)
    return name.replace('_', ' ').strip()

def import_data(conn):
    """Imports all JSON files from DATA_DIR into the Questions table."""
    
    if not os.path.exists(DATA_DIR):
        print(f"Error: Directory '{DATA_DIR}' not found. Please create it and place your labeled JSON files inside.")
        return

    cursor = conn.cursor()
    total_questions = 0

    for filename in os.listdir(DATA_DIR):
        if filename.endswith("_SMART.json"):
            file_path = os.path.join(DATA_DIR, filename)
            
            # Use the clean chapter name as a label for every question
            chapter_root = clean_chapter_name(filename) 
            
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    questions = json.load(f)
                except json.JSONDecodeError as e:
                    print(f"Error reading JSON file {filename}: {e}")
                    continue

            for q in questions:
                # Prepare data for insertion (handling missing AI labels gracefully)
                try:
                    # The full chapter name (including Syllabus Reduced) is preserved in the sub_topic
                    # We store the clean chapter_root in the chapter field.
                    data = (
                        q.get('url'),
                        chapter_root,
                        q.get('sub_topic', 'Unlabeled'),
                        q.get('difficulty', 0),
                        q.get('logic_type', 'N/A'),
                        q.get('physics_key', 'N/A'),
                        q.get('is_numerical', False),
                        q.get('question'),
                        json.dumps(q.get('options')),
                        q.get('answer'),
                        json.dumps(q.get('images', []))  # ← NEW: store images as JSON string
                    )

                    # Use INSERT OR IGNORE to prevent adding duplicates (based on UNIQUE URL)
                    cursor.execute("""
                        INSERT OR IGNORE INTO Questions 
                        (url, chapter, sub_topic, difficulty, logic_type, physics_key, is_numerical, question_text, options, answer, images)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, data)
                    total_questions += 1
                except Exception as e:
                    print(f"Failed to insert question with URL {q.get('url')}: {e}")

    conn.commit()
    print(f"\nSuccessfully imported {total_questions} questions into the Questions table.")
    print("Database is ready for use by the application modules.")

# --- 4. MAIN EXECUTION ---

def initialize_database():
    """Main function to set up and populate the database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        create_tables(conn)
        import_data(conn)
        return conn
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # Create a dummy folder if it doesn't exist (for testing the code structure)
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"Note: Created directory '{DATA_DIR}'. Please place your labeled JSON files here.")
    
    initialize_database()