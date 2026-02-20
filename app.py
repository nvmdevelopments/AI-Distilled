import streamlit as st
import pandas as pd
import sqlite3
import os

# Configuration
DB_PATH = "articles.db"

# Page setup
st.set_page_config(
    page_title="AI Distillate Feed",
    page_icon="📰",
    layout="centered"
)


@st.cache_data(ttl=60) # Cache the function's return value for 60 seconds
def load_data():
    """Connect to the database and retrieve processed articles."""
    try:
        conn = sqlite3.connect(DB_PATH)
        # Query only processed rows
        query = "SELECT * FROM articles WHERE processed = 1"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except sqlite3.Error as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame() # Return empty DataFrame on error
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_executive_summary():
    """Retrieve the latest executive summary from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT * FROM executive_summaries ORDER BY generated_at DESC LIMIT 1"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except sqlite3.Error:
        # Table might not exist yet or other DB error
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading executive summary: {e}")
        return pd.DataFrame()


def main():
    st.title("📰 AI Distillate News Feed")
    st.markdown("A highly synthesized executive overview of automated AI news.")

    # Load data
    df = load_data()
    exec_summary_df = load_executive_summary()

    if df.empty:
        st.warning("No processed articles found in the database. Run the ingestion and distillation pipelines first.")
        return

    # Setup tabs
    tab1, tab2 = st.tabs(["🚀 Executive Summary", "📋 Raw Source Feed"])

    # --- TAB 1: Executive Summary ---
    with tab1:
        if not exec_summary_df.empty:
            summary_row = exec_summary_df.iloc[0]
            generated_at = summary_row.get('generated_at', 'Unknown time')
            
            st.caption(f"Last Generated: {generated_at}")
            
            # --- Audio Player ---
            audio_path = summary_row.get('audio_path')
            if pd.notna(audio_path) and isinstance(audio_path, str):
                if os.path.exists(audio_path):
                    st.audio(audio_path, format="audio/mp3")
                else:
                    st.warning("Audio file not found on disk.")
            
            st.header("1. What's new today")
            st.write(summary_row.get('whats_new_today', 'No data.'))
            st.divider()
            
            st.header("2. Model and tooling updates")
            st.write(summary_row.get('model_updates', 'No data.'))
            st.divider()
            
            st.header("3. Key Takeaways")
            st.write(summary_row.get('key_takeaways', 'No data.'))
        else:
            st.info("No Executive Summary generated yet. Please run the `synthesizer.py` pipeline.")

    # --- TAB 2: Raw Source Feed ---
    with tab2:
        # Sidebar filtering (Only relevant for Raw Feed)
        st.sidebar.header("Filter Source Feed")
        
        # Get unique industry tags for the multiselect
        unique_tags = sorted([tag for tag in df['industry_tag'].unique() if pd.notna(tag)])
        
        selected_tags = st.sidebar.multiselect(
            "Select Industry Tags:",
            options=unique_tags,
            default=[] 
        )

        if selected_tags:
            filtered_df = df[df['industry_tag'].isin(selected_tags)]
        else:
            filtered_df = df

        st.sidebar.markdown(f"**Showing {len(filtered_df)} of {len(df)} raw articles.**")

        if filtered_df.empty:
             st.info("No articles match the selected filters.")
        else:
             for index, row in filtered_df.iterrows():
                 with st.container():
                     title = row.get('title', 'Untitled')
                     url = row.get('url', '#')
                     st.subheader(f"[{title}]({url})")

                     tag = row.get('industry_tag', 'Uncategorized')
                     st.caption(f"Tag: {tag}")

                     summary = row.get('summary', 'No summary available.')
                     st.markdown(summary)

                     audio_path = row.get('audio_path')
                     if pd.notna(audio_path) and isinstance(audio_path, str):
                         if os.path.exists(audio_path):
                             st.audio(audio_path)
                     
                     st.markdown("---")


if __name__ == "__main__":
    main()
