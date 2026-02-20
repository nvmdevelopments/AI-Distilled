"""
Module for processing unstructured text articles and categorizing/summarizing
them using the Google GenAI API. This module acts as the logical LLM core.
"""

import logging
import os
import sqlite3
from typing import Any, Dict

from google import genai
from google.genai import types
from pydantic import BaseModel
from tenacity import retry, wait_exponential, stop_after_attempt
from dotenv import load_dotenv

# Load custom .env file for the user's setup
load_dotenv("API key.env")

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ArticleSummary(BaseModel):
    industry_tag: str
    summary: str


@retry(
    wait=wait_exponential(multiplier=2, min=4, max=65),
    stop=stop_after_attempt(6)
)
def generate_summary_and_category(client: genai.Client, text: str) -> ArticleSummary:
    """
    Calls the Gemini API to categorize and summarize text.
    Implements API resilience via exponential backoff (tenacity).
    Enforces structured output via Pydantic.
    """
    prompt_text = (
        "Please process the following text.\n"
        "1. Categorize the text into a specific Industry/Use Case "
        "(e.g., Healthcare, Software Eng, Finance).\n"
        "2. Generate a highly condensed, 3-sentence summary highlighting only "
        "the most relevant, applicable information for professionals.\n\n"
        f"Text to process:\n{text}"
    )

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt_text,
        config=types.GenerateContentConfig(
            response_schema=ArticleSummary,
            response_mime_type="application/json",
        ),
    )
    
    if not response.parsed:
        raise ValueError("Failed to parse response from Gemini API")
        
    return response.parsed


def distillation_job(db_path: str = "articles.db") -> None:
    """
    Queries the database for unprocessed articles, uses the LLM logic to 
    summarize and categorize them, and updates the database records.
    """
    # Simple file-based lock to prevent multiple instances (Zombie protection)
    lock_file = "distillation.lock"
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r") as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid():
                logger.error("Another instance of distillation.py (PID %s) is already running.", old_pid)
                return
        except (ValueError, OSError):
            pass

    with open(lock_file, "w") as f:
        f.write(str(os.getpid()))

    try:
        client = genai.Client()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Select articles that have not yet been processed
        try:
            cursor.execute("SELECT id, raw_text FROM articles WHERE (processed = 0 OR processed IS NULL)")
            records = cursor.fetchall()
        except sqlite3.OperationalError:
            logger.error("Database table 'articles' does not exist or db not initialized.")
            return
            
        if not records:
            logger.info("No unprocessed articles found in the database.")
            return
            
        logger.info("Found %d unprocessed articles to distill.", len(records))
        
        for record in records:
            article_id = record["id"]
            raw_text = record["raw_text"]
            
            if not raw_text or not raw_text.strip():
                logger.info("Article %s has no text. Marking as processed and skipping.", article_id)
                cursor.execute(
                    "UPDATE articles SET processed = 1 WHERE id = ?",
                    (article_id,)
                )
                conn.commit()
                continue
                
            logger.info("Processing article %s...", article_id)
            try:
                # generate_summary_and_category automatically handles structured parsing and retries
                parsed_result = generate_summary_and_category(client, raw_text)
                
                # Update the database
                cursor.execute(
                    """
                    UPDATE articles 
                    SET summary = ?, industry_tag = ?, processed = 1 
                    WHERE id = ?
                    """,
                    (parsed_result.summary, parsed_result.industry_tag, article_id)
                )
                conn.commit()
                logger.info("Successfully completed distillation for article %s.", article_id)
                
            except Exception as e:
                logger.error("Failed to process article %s: %s", article_id, e)
                conn.rollback()
                
    except sqlite3.Error as db_err:
        logger.error("Database error occurred: %s", db_err)
    finally:
        if 'conn' in locals() and conn:
            conn.close()
        if os.path.exists(lock_file):
            os.remove(lock_file)


if __name__ == "__main__":
    logger.info("Starting distillation pipeline...")
    distillation_job()