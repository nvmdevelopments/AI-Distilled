import sqlite3

def run_migration():
    conn = sqlite3.connect('articles.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN published_at TEXT")
        conn.commit()
        print("Successfully added published_at column to articles.")
    except sqlite3.OperationalError as e:
        print(f"Column might already exist or error: {e}")
        
    cursor.execute("UPDATE articles SET published_at = datetime('now', '-2 days') WHERE published_at IS NULL")
    conn.commit()
    conn.close()

if __name__ == '__main__':
    run_migration()
