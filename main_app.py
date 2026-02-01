import time
import json
import random
import os
from datetime import datetime
import webbrowser
from db_manager import get_connection, JEE_2025_WEIGHTAGE, initialize_database
from test_generator import (
    generate_foundational_test, 
    generate_subtopic_drill, 
    generate_balanced_mock, 
    generate_advanced_drill,
    fetch_questions
)
from analytics import calculate_mastery_scores, display_mastery_heatmap

# --- 1. SESSION MANAGEMENT ---

def log_user_answer(conn, q_id, is_correct, time_taken, session_id):
    """Logs the user's attempt into the User_Logs table."""
    cursor = conn.cursor()
    result = 'Correct' if is_correct else 'Wrong'
    
    # Use REPLACE INTO to overwrite the entry if the user retries a question in the same session
    cursor.execute("""
        INSERT OR REPLACE INTO User_Logs (session_id, question_id, result, time_taken)
        VALUES (?, ?, ?, ?)
    """, (session_id, q_id, result, time_taken))
    conn.commit()
    return result

def run_test_session(questions, conn, session_name):
    """Runs a study session, presents questions, and logs results."""
    session_id = f"{session_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print("\n" + "="*50)
    print(f"STARTING SESSION: {session_name} ({len(questions)} Questions)")
    print("="*50)
    
    total_correct = 0
    
    for i, q in enumerate(questions):
        start_time = time.time()
        
        # --- Display Question ---
        print("-" * 50)
        print(f"Q {i+1}/{len(questions)} ({q['sub_topic']}) [Difficulty: L{q['difficulty']}]")
        print(f"\n{q['question_text']}")


        
        # Parse options safely
        options_list = json.loads(q['options']) if q['options'] else []
        
        # NEW: Handle images in question
        images = json.loads(q.get('images', '[]'))
        if images:
            print("\nThis question has image(s)/diagram(s):")
            for img_url in images:
                print(f" - {img_url}")
                # Optional: auto-open in browser (comment out if too many tabs!)
                # webbrowser.open_new_tab(img_url)
            print("Copy-paste URLs above into your browser to view.\n")

        # UPDATED: Handle options (text or image URLs)
        options_list = json.loads(q['options']) if q['options'] else []
        if options_list:
            labels = ['A', 'B', 'C', 'D']
            for j, opt in enumerate(options_list):
                if isinstance(opt, str) and opt.startswith(('http://', 'https://')):
                    print(f" {labels[j]}. [Image Option] {opt}")
                    # webbrowser.open_new_tab(opt)  # optional
                else:
                    print(f" {labels[j]}. {opt}")
        
        # --- Get User Input ---
        user_input = input("\nYour Answer (Type the option, or 'SKIP', or 'EXIT'): ").strip().upper()
        end_time = time.time()
        time_taken = round(end_time - start_time, 2)
        
        # --- Process Answer and Log ---
        is_correct = False
        if user_input == 'EXIT':
            print("Session interrupted.")
            break
        elif user_input == 'SKIP':
            log_user_answer(conn, q['id'], False, time_taken, session_id)
            print(">>> SKIPPED. Logging as 'Wrong' for drill purposes.")
        else:
            # Simple check for MCQs (A, B, C, D) vs. Numerical (direct answer text)
            if options_list:
                try:
                    chosen_answer = options_list[labels.index(user_input)]
                    if chosen_answer.strip().lower() == q['answer'].strip().lower():
                         is_correct = True
                except ValueError:
                    # Input wasn't A, B, C, or D
                    pass
            else: # Numerical type question
                # A robust app would use float parsing and tolerance, but for now:
                if user_input.strip().lower() == q['answer'].strip().lower():
                    is_correct = True
                    
            log_user_answer(conn, q['id'], is_correct, time_taken, session_id)
            
            if is_correct:
                total_correct += 1
                print(f">>> CORRECT! Time: {time_taken}s")
            else:
                print(f">>> WRONG. Correct Answer: {q['answer']}. Time: {time_taken}s")

    # --- Session Summary & Update ---
    accuracy = (total_correct / len(questions)) * 100 if questions else 0
    print("\n" + "="*50)
    print(f"SESSION ENDED. Final Score: {total_correct}/{len(questions)} ({accuracy:.1f}%)")
    cursor = conn.cursor()
    # NEW: Update N/A answers for attempted questions in this session
    cursor.execute("""
        SELECT q.id, q.question_text 
        FROM User_Logs ul 
        JOIN Questions q ON ul.question_id = q.id 
        WHERE ul.session_id = ? AND q.answer = 'N/A'
    """, (session_id,))
    na_questions = cursor.fetchall()

    if na_questions:
        print("\n" + "="*50)
        print("Some numerical questions had 'N/A' as the stored answer.")
        print("Please provide the correct answer (usually an integer, no units):")
        for q_id, q_text in na_questions:
            print(f"\nQuestion: {q_text}")
            while True:
                new_answer = input("Correct answer (integer): ").strip()
                try:
                    int(new_answer)  # Validate as integer
                    break
                except ValueError:
                    print("Please enter a valid integer (e.g. 5, 100).")
            cursor.execute("UPDATE Questions SET answer = ? WHERE id = ?", (new_answer, q_id))
            conn.commit()
            print(f"Updated answer to '{new_answer}'.")
        print("="*50)

    # NEW: Simple learning loop - review wrongs/skipped
    print("\n" + "="*50)
    print("Learning Loop: Review Wrong / Skipped Questions")
    cursor.execute("""
        SELECT q.id, q.question_text, q.answer 
        FROM User_Logs ul 
        JOIN Questions q ON ul.question_id = q.id 
        WHERE ul.session_id = ? AND ul.result != 'Correct'
    """, (session_id,))
    wrong_qs = cursor.fetchall()

    if not wrong_qs:
        print("Great job! No wrongs/skipped in this session.")
    else:
        for q_id, text, ans in wrong_qs:
            print(f"\nQuestion: {text}")
            print(f"Correct Answer: {ans}")
            retry = input("Retry this question now? (y/n): ").strip().lower()
            if retry == 'y':
                print("\nRe-presenting question...")
                # Simple re-display (no timer/log for simplicity)
                print(text)
                # Re-show images/options like above (copy-paste the display code here if needed)
                input("Press Enter when done reviewing...")
    print("="*50)
    
    # Crucial Step: Update the Mastery_Scores after the session
    calculate_mastery_scores(conn)
    print("Mastery Scores Updated. Check the Main Menu for new insights.")
    print("="*50)


# --- 2. MAIN MENU AND APP FLOW ---

def main_menu(conn):
    """Displays the main menu and handles mode selection."""
    
    # 1. Update scores and display high-level map first
    calculate_mastery_scores(conn)
    display_mastery_heatmap(conn)

    print("\n--- JEE PHYSICS ADAPTIVE TUTOR ---")
    print("A. Chapter Mastery (Deep Dive)")
    print("B. Exam Simulation (Mock & Drill)")
    print("R. Refresh/Show Report")
    print("X. Exit")
    
    choice = input("\nSelect a mode (A/B/R/X): ").strip().upper()
    
    if choice == 'A':
        chapter_mastery_menu(conn)
    elif choice == 'B':
        exam_simulation_menu(conn)
    elif choice == 'R':
        main_menu(conn) # Just redisplay with fresh data
    elif choice == 'X':
        print("Goodbye! Keep up the practice.")
        return
    else:
        print("Invalid choice. Try again.")
        main_menu(conn)
        
def chapter_mastery_menu(conn):
    """Handles the Chapter Mastery sub-menu (A.1 and A.2)."""
    
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT chapter FROM Questions ORDER BY chapter ASC")
    chapters = [row[0] for row in cursor.fetchall()]
    
    print("\n--- CHAPTER MASTERY ---")
    for i, chap in enumerate(chapters):
        print(f" {i+1}. {chap}")
    
    chap_choice = input("\nSelect a Chapter Number to drill: ").strip()
    try:
        chapter_name = chapters[int(chap_choice) - 1]
    except (ValueError, IndexError):
        print("Invalid chapter selection.")
        return main_menu(conn)
    
    print(f"\n--- {chapter_name.upper()} MODES ---")
    print("1. Foundational Test (L1/L2 Unseen)")
    print("2. Sub-Topic Drill (Weakness Correction)")
    
    mode_choice = input("Select a drill type (1/2): ").strip()

    if mode_choice == '1':
        questions = generate_foundational_test(chapter_name)
        run_test_session(questions, conn, f"FOUNDATIONAL_{chapter_name}")
    elif mode_choice == '2':
        questions = generate_subtopic_drill(chapter_name)
        run_test_session(questions, conn, f"DRILL_CHAPTER_{chapter_name}")
    else:
        print("Invalid mode selection.")

def exam_simulation_menu(conn):
    """Handles the Exam Simulation sub-menu (B.1 and B.2)."""
    print("\n--- EXAM SIMULATION ---")
    print("1. Balanced Mock Test (25 Qs - Full JEE Weightage)")
    print("2. Advanced Drill (15 Qs - Global Weakest Sub-Topics)")

    mode_choice = input("Select a test type (1/2): ").strip()

    if mode_choice == '1':
        questions = generate_balanced_mock()
        run_test_session(questions, conn, "MOCK_BALANCED_JEE")
    elif mode_choice == '2':
        questions = generate_advanced_drill()
        run_test_session(questions, conn, "DRILL_ADVANCED_GLOBAL")
    else:
        print("Invalid mode selection.")
        
    main_menu(conn) # Return to the main menu after the test

# --- 3. INITIALIZATION ---

if __name__ == "__main__":
    # Ensure the database is initialized first
    # NOTE: Comment this out after the very first run to prevent re-importing data
    # initialize_database() 
    
    conn = get_connection()
    if conn:
        # Run the main application loop
        main_menu(conn)
        conn.close()
    else:
        print("Application failed to connect to the database. Exiting.")