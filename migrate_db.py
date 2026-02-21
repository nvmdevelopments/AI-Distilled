import sqlite3

def migrate():
    conn = sqlite3.connect("articles.db")
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN synthesized BOOLEAN NOT NULL DEFAULT 0")
        conn.commit()
        print("Successfully added 'synthesized' column to 'articles' table.")
    except sqlite3.OperationalError as e:
        print(f"Migration error (column might already exist): {e}")
    
    # Mark existing processed articles as synthesized so the first run isn't huge
    cursor.execute("UPDATE articles SET synthesized = 1 WHERE processed = 1")
    conn.commit()
    print("Marked existing processed articles as synthesized.")
    
    conn.close()

if __name__ == "__main__":
    migrate()
