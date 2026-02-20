---
description: Code style guide and architecture mandates for this workspace.
---

@rule code-style-guide

# Code Style Guide

When writing or modifying code in this workspace, strictly adhere to the following rules:

1. **Python Version & Styling**: 
   - Use **Python 3.11+**.
   - Strictly adhere to **PEP 8** styling guidelines.

2. **Modular Architecture**:
   - Maintain a clean, modular architecture.
   - You must use separate files for logically distinct components. In particular, cleanly separate **ingestion**, **LLM logic**, and **UI** into their own distinct files or modules.

3. **API Resilience**:
   - **Always** implement **exponential backoff** for any and all external API calls to ensure resilience against rate limits and transient network failures.
