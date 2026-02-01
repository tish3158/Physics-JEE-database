import sqlite3
import math
import datetime
from db_manager import DB_FILE, JEE_2025_WEIGHTAGE

# --- 1. CONFIGURATION ---
# Weights for the composite Mastery Score
ACCURACY_WEIGHT = 0.7
SPEED_WEIGHT = 0.3

# Global reference: average time per question in seconds
# Used to normalize speed performance
GLOBAL_AVG_TIME = 120


# --- 2. CORE ANALYTICS FUNCTIONS ---

def get_connection():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_FILE)


def calculate_mastery_scores(conn):
    """
    Calculates and updates the Mastery_Scores table based on all user logs.
    Runs after every test session to keep performance data up-to-date.
    """
    cursor = conn.cursor()

    # Aggregate performance per sub-topic
    query = """
    SELECT 
        q.sub_topic,
        SUM(CASE WHEN ul.result = 'Correct' THEN 1 ELSE 0 END) AS correct_count,
        SUM(CASE WHEN ul.result IN ('Correct', 'Wrong') THEN 1 ELSE 0 END) AS total_attempts,
        AVG(CASE WHEN ul.result = 'Correct' THEN ul.time_taken ELSE NULL END) AS avg_time_correct
    FROM User_Logs ul
    JOIN Questions q ON ul.question_id = q.id
    GROUP BY q.sub_topic
    HAVING total_attempts > 0;
    """
    cursor.execute(query)
    results = cursor.fetchall()
    
    print("\n--- Calculating Mastery Scores ---")
    
    today = datetime.date.today()
    
    for row in results:
        sub_topic, correct_count, total_attempts, avg_time_correct = row
        
        # Accuracy (proportion of correct among serious attempts)
        accuracy = correct_count / total_attempts if total_attempts > 0 else 0.0
        
        # Speed factor: how much faster/slower than average
        if avg_time_correct is not None and avg_time_correct > 0:
            speed_factor = GLOBAL_AVG_TIME / avg_time_correct
            speed_factor = min(speed_factor, 2.0)  # cap bonus at 2× speed
        else:
            speed_factor = 1.0  # neutral if no correct answers yet
        
        # Composite score
        raw_mastery = (ACCURACY_WEIGHT * accuracy) + (SPEED_WEIGHT * (speed_factor / 2.0))
        
        # Cap at 1.0 (100%) — prevents inflated scores from very fast answers
        mastery_score = min(raw_mastery, 1.0)
        
        # Spaced repetition: longer interval for higher mastery
        review_interval_days = math.ceil(mastery_score * 30)  # 0 → today, 1.0 → ~30 days
        next_review_date = (today + datetime.timedelta(days=review_interval_days)).isoformat()
        
        print(f"[{sub_topic}] "
              f"Acc: {accuracy:>5.2f} | "
              f"Speed: {speed_factor:>5.2f}x | "
              f"Mastery: {mastery_score:>5.2f} | "
              f"Next: {next_review_date}")
        
        # Save / update
        cursor.execute("""
            INSERT OR REPLACE INTO Mastery_Scores 
            (sub_topic, accuracy, avg_time, mastery_score, next_review_date)
            VALUES (?, ?, ?, ?, ?)
        """, (sub_topic, accuracy, avg_time_correct, mastery_score, next_review_date))

    conn.commit()
    print("Mastery scores updated.")


def get_weakest_topics(conn, num_topics=3, chapter_filter=None):
    """
    Returns list of the weakest sub-topics (lowest mastery_score).
    Can be global or filtered to one chapter.
    """
    cursor = conn.cursor()
    
    query = """
    SELECT ms.sub_topic 
    FROM Mastery_Scores ms
    """
    params = []
    
    if chapter_filter:
        query += """
        JOIN Questions q ON q.sub_topic = ms.sub_topic
        WHERE q.chapter = ?
        """
        params.append(chapter_filter)
    
    query += " ORDER BY ms.mastery_score ASC LIMIT ?"
    params.append(num_topics)
    
    cursor.execute(query, params)
    weakest = [row[0] for row in cursor.fetchall()]
    
    return weakest


def display_mastery_heatmap(conn):
    """
    Shows a text-based progress dashboard:
    - Average mastery per chapter
    - Number of sub-topics tracked in that chapter
    - Color indicator
    """
    cursor = conn.cursor()
    
    # Better grouping: average mastery per chapter + topic count
    query = """
    SELECT 
        q.chapter,
        AVG(ms.mastery_score) AS avg_mastery,
        COUNT(DISTINCT ms.sub_topic) AS topic_count,
        MIN(ms.next_review_date) AS earliest_review
    FROM Questions q
    JOIN Mastery_Scores ms ON q.sub_topic = ms.sub_topic
    GROUP BY q.chapter
    ORDER BY avg_mastery DESC
    """
    cursor.execute(query)
    
    print("\n" + "="*70)
    print("          PROGRESS DASHBOARD — Chapter Level Overview")
    print("="*70)
    print(f"{'Chapter':<28} {'Avg Mastery':<12} {'Topics':<8} {'Earliest Review':<15} Status")
    print("-"*70)
    
    for chapter, avg_mastery, topic_count, earliest_review in cursor.fetchall():
        mastery_val = avg_mastery if avg_mastery is not None else 0.0
        color = "🟢" if mastery_val >= 0.80 else ("🟡" if mastery_val >= 0.50 else "🔴")
        
        review_str = earliest_review if earliest_review else "N/A"
        
        print(f"{chapter:<28} "
              f"{mastery_val:>6.1%}   "
              f"{topic_count:>6}    "
              f"{review_str:<15} "
              f"{color}")
    
    print("-"*70)
    print("🟢 = strong (>80%)   🟡 = developing (50–80%)   🔴 = needs attention (<50%)")
    print("="*70 + "\n")


# --- 3. For quick testing / debugging (run this file directly) ---

if __name__ == "__main__":
    conn = get_connection()
    try:
        calculate_mastery_scores(conn)
        display_mastery_heatmap(conn)
        
        # Example: show 3 weakest topics globally
        weakest = get_weakest_topics(conn, num_topics=3)
        print("\n3 Weakest Sub-Topics (global):")
        if weakest:
            for t in weakest:
                print(f"  • {t}")
        else:
            print("  (No performance data yet — solve some questions first)")
            
    finally:
        conn.close()