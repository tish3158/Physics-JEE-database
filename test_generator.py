import sqlite3
import random
import math
from db_manager import DB_FILE, JEE_2025_WEIGHTAGE
from analytics import get_weakest_topics

# --- 1. UTILITY FUNCTIONS ---

def get_connection():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_FILE)

def fetch_questions(conn, condition, limit=None, order="RANDOM()"):
    """
    Generic function to fetch questions based on a SQL WHERE clause condition.
    Returns a list of question dictionaries.
    """
    cursor = conn.cursor()
    
    # We select all necessary fields (q.*)
    query = f"""
    SELECT id, question_text, options, answer, is_numerical, chapter, sub_topic, difficulty, images
    FROM Questions
    WHERE {condition}
    ORDER BY {order}
    {f'LIMIT {limit}' if limit else ''};
    """
    
    cursor.execute(query)
    
    # Map column names to results for easy dictionary access
    columns = [desc[0] for desc in cursor.description]
    questions = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return questions

# --- 2. CHAPTER MASTERY MODES (A) ---

def generate_foundational_test(chapter_name, num_questions=25):
    """
    Mode A.1: Generates a test focusing on easy, foundational questions for a chapter.
    Prioritizes questions with low difficulty (L1 or L2) and low attempts.
    """
    conn = get_connection()
    print(f"\n--- Generating FOUNDATIONAL Test for: {chapter_name} ---")
    
    # Prioritize UNSEEN (or least-seen) questions with low difficulty
    # This requires a LEFT JOIN with User_Logs, which we simplify for now
    # We use a simple NOT EXISTS to check for unseen questions
    condition = f"""
        chapter = '{chapter_name}' 
        AND difficulty <= 2 
        AND NOT EXISTS (
            SELECT 1 FROM User_Logs ul WHERE ul.question_id = Questions.id
        )
    """
    
    # If not enough unseen are found, pull from all low-difficulty questions
    questions = fetch_questions(conn, condition, limit=num_questions)
    
    if len(questions) < num_questions:
        print(f"Warning: Only found {len(questions)} unseen L1/L2 Qs. Filling with previously seen Qs.")
        # Fallback to all L1/L2, ordering by attempts ASC
        condition = f"chapter = '{chapter_name}' AND difficulty <= 2"
        questions = fetch_questions(conn, condition, limit=num_questions, order="RANDOM()")

    conn.close()
    return questions

def generate_subtopic_drill(chapter_name, num_questions=15):
    """
    Mode A.2: Generates a drill focusing on the user's 3 weakest sub_topics within the chapter.
    Questions are medium/hard (L3+).
    """
    conn = get_connection()
    
    # 1. Identify the weak sub_topics within the specified chapter
    weakest_topics = get_weakest_topics(conn, num_topics=3, chapter_filter=chapter_name)
    
    if not weakest_topics:
        conn.close()
        print(f"Error: No mastery data available for {chapter_name}. Please solve more questions first.")
        return []

    topic_list = ', '.join([f"'{t}'" for t in weakest_topics])
    print(f"\n--- Generating SUB-TOPIC DRILL for weak areas in {chapter_name} ---")
    print(f"Targeting Sub-Topics: {weakest_topics}")

    # 2. Select hard (L3+) questions from these topics
    condition = f"sub_topic IN ({topic_list}) AND difficulty >= 3"
    
    # Prioritize questions that were answered Wrong in the past
    questions = fetch_questions(conn, condition, limit=num_questions, order="CASE WHEN (SELECT result FROM User_Logs WHERE question_id = Questions.id ORDER BY timestamp DESC LIMIT 1) = 'Wrong' THEN 0 ELSE 1 END, RANDOM()")

    conn.close()
    return questions

# --- 3. EXAM SIMULATION MODES (B) ---

def generate_balanced_mock(total_questions=25):
    conn = get_connection()
    numerical_candidates = []
    mcq_candidates = []
    
    total_weight = sum(JEE_2025_WEIGHTAGE.values())
    
    for chapter, weight in JEE_2025_WEIGHTAGE.items():
        # Numerical candidates
        cond_num = f"chapter = '{chapter}' AND is_numerical = 1"
        num_qs = fetch_questions(conn, cond_num)
        numerical_candidates.extend([(q, weight) for q in num_qs])
        
        # MCQ candidates
        cond_mcq = f"chapter = '{chapter}' AND is_numerical = 0"
        mcq_qs = fetch_questions(conn, cond_mcq)
        mcq_candidates.extend([(q, weight) for q in mcq_qs])
    
    # Select exactly 5 numerical (weighted random)
    selected_num = []
    if numerical_candidates:
        qs_num, weights_num = zip(*numerical_candidates)
        selected_num = random.choices(list(qs_num), weights=weights_num, k=min(5, len(qs_num)))
    
    # Fill rest with MCQ (target 20, weighted)
    target_mcq = total_questions - len(selected_num)
    selected_mcq = []
    if mcq_candidates:
        qs_mcq, weights_mcq = zip(*mcq_candidates)
        selected_mcq = random.choices(list(qs_mcq), weights=weights_mcq, k=min(target_mcq, len(qs_mcq)))
    
    questions = selected_num + selected_mcq
    random.shuffle(questions)
    
    conn.close()
    print(f"\n--- Generated Balanced Mock Test ({len(questions)} Qs | {len(selected_num)} Numerical) ---")
    return questions[:total_questions]


def generate_advanced_drill(num_questions=15):
    """
    Mode B.2: Generates a high-difficulty drill focusing on the user's 3 weakest sub_topics GLOBALLY.
    Questions are L4 or L5 difficulty.
    """
    conn = get_connection()
    
    # 1. Identify the weak sub_topics globally (no chapter filter)
    weakest_topics = get_weakest_topics(conn, num_topics=3)
    
    if not weakest_topics:
        conn.close()
        print("Error: No global mastery data available. Please solve more Balanced Mock Tests first.")
        return []

    topic_list = ', '.join([f"'{t}'" for t in weakest_topics])
    print(f"\n--- Generating ADVANCED DRILL for GLOBAL Weakest Areas ---")
    print(f"Targeting Global Weakest Sub-Topics: {weakest_topics}")

    # 2. Select the hardest questions (L4+) from these topics
    # ORDER BY next_review_date ASC (Spaced Repetition Logic)
    condition = f"sub_topic IN ({topic_list}) AND difficulty >= 4"
    questions = fetch_questions(conn, condition, limit=num_questions, order="RANDOM()") # Using RANDOM() as a proxy for Spaced Repetition for simplicity

    conn.close()
    return questions

# --- 4. EXECUTION EXAMPLE ---

if __name__ == "__main__":
    # NOTE: These tests assume your database has data in the 'Questions' table 
    # and that 'analytics.py' has been run at least once to populate Mastery_Scores.
    
    # Test 1: Chapter Foundational Test
    chap_qs = generate_foundational_test('Rotational Motion')
    print(f"Rotational Motion Foundational Qs: {len(chap_qs)}")
    
    # Test 2: Sub-Topic Drill (Needs weakest topics, will work if analytics was run)
    drill_qs = generate_subtopic_drill('Rotational Motion')
    print(f"Rotational Motion Drill Qs: {len(drill_qs)}")
    
    # Test 3: Balanced Mock Test
    mock_qs = generate_balanced_mock()
    print(f"Balanced Mock Test Qs: {len(mock_qs)}")
    
    # Test 4: Advanced Drill (Needs global weakest topics, will work if analytics was run)
    adv_qs = generate_advanced_drill()
    print(f"Advanced Drill Qs: {len(adv_qs)}")