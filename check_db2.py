import sqlite3

conn = sqlite3.connect('articles.db')
c = conn.cursor()
c.execute("SELECT id, title, url FROM articles WHERE source='The AI Daily Brief' AND id LIKE 'yt:%' ORDER BY rowid DESC")
rows = c.fetchall()
for row in rows:
    print(row)
conn.close()
