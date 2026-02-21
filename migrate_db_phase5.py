import sqlite3

def migrate():
    conn = sqlite3.connect("articles.db")
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE executive_summaries RENAME COLUMN model_updates TO daily_brief_summary")
        conn.commit()
        print("Successfully renamed 'model_updates' to 'daily_brief_summary' in 'executive_summaries' table.")
    except sqlite3.OperationalError as e:
        print(f"Migration error (column might already be renamed): {e}")
    conn.close()

if __name__ == "__main__":
    migrate()
