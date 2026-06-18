# ==========================================
# RAG_APP Package Initialization
# ==========================================

"""
RAG_APP - Hybrid Search RAG Application

A FastAPI-based application for:
- Retrieval-Augmented Generation (RAG)
- SQL Query Analysis  
- Document Processing & Indexing
- LLM Integration with Ollama
- User Authentication
"""

__version__ = "1.0.0"
__author__ = "RAG Development Team"
__description__ = "Hybrid Search RAG Application with FastAPI and Ollama"

# Import main components for easier access
try:
    from db import engine, sessionLocal, Base
    from authentication import verify_password, hash_password
except ImportError as e:
    print(f"⚠️ Warning: Could not import components: {e}")

__all__ = [
    "engine",
    "sessionLocal", 
    "Base",
    "verify_password",
    "hash_password",
]
