import sqlite3

conn = sqlite3.connect('articles.db')
c = conn.cursor()

# Get the latest AI Daily Brief article
c.execute("SELECT id FROM articles WHERE source = 'The AI Daily Brief' ORDER BY rowid DESC LIMIT 1")
ai_brief_id = c.fetchone()[0]

# Get the latest 3 regular articles (excluding AI Daily Brief)
c.execute("SELECT id FROM articles WHERE source != 'The AI Daily Brief' AND processed = 1 ORDER BY rowid DESC LIMIT 3")
other_ids = [row[0] for row in c.fetchall()]

all_ids = [ai_brief_id] + other_ids

for article_id in all_ids:
    c.execute("UPDATE articles SET synthesized = 0 WHERE id = ?", (article_id,))

conn.commit()
print(f"Reset synthesized status for articles: {all_ids}")
conn.close()
