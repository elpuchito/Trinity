"""
TriageForge — RAG Indexer
Indexes the Saleor e-commerce codebase into ChromaDB for agent retrieval.
Uses text-based chunking for Python files and heading-aware chunking for Markdown.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings

logger = logging.getLogger("triageforge.rag.indexer")

# Collection names
CODE_COLLECTION = "saleor_code"
DOCS_COLLECTION = "saleor_docs"

# Default codebase path (relative to backend root)
DEFAULT_CODEBASE_PATH = "/app/ecommerce_codebase/saleor"


def get_chroma_client() -> chromadb.HttpClient:
    """Create a ChromaDB HTTP client."""
    settings = get_settings()
    return chromadb.HttpClient(
        host=settings.chromadb_host,
        port=settings.chromadb_port,
    )


def chunk_python_file(filepath: str, max_chunk_size: int = 1500) -> list[dict]:
    """
    Chunk a Python file by top-level classes and functions.
    
    Strategy:
    - Split on `class ` and `def ` at indentation level 0
    - Keep docstrings with their parent construct
    - Overlap: include the first 2 lines of the next chunk for context
    - Each chunk gets metadata: file_path, chunk_type (class/function/module), name
    """
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if not content.strip():
        return []

    lines = content.split("\n")
    chunks = []
    current_chunk_lines = []
    current_name = os.path.basename(filepath)
    current_type = "module_header"
    chunk_start = 0

    for i, line in enumerate(lines):
        # Detect top-level class or function definition
        if re.match(r'^(class |def )', line) and i > 0:
            # Save the previous chunk
            if current_chunk_lines:
                chunk_text = "\n".join(current_chunk_lines)
                if chunk_text.strip():
                    chunks.append({
                        "content": chunk_text,
                        "metadata": {
                            "file_path": filepath,
                            "chunk_type": current_type,
                            "name": current_name,
                            "start_line": chunk_start + 1,
                            "end_line": i,
                        }
                    })

            # Start new chunk
            current_chunk_lines = [line]
            chunk_start = i

            # Extract name
            match = re.match(r'^(class|def)\s+(\w+)', line)
            if match:
                current_type = match.group(1)
                current_name = match.group(2)
        else:
            current_chunk_lines.append(line)

    # Save the last chunk
    if current_chunk_lines:
        chunk_text = "\n".join(current_chunk_lines)
        if chunk_text.strip():
            chunks.append({
                "content": chunk_text,
                "metadata": {
                    "file_path": filepath,
                    "chunk_type": current_type,
                    "name": current_name,
                    "start_line": chunk_start + 1,
                    "end_line": len(lines),
                }
            })

    # If file is small enough, just return it as one chunk
    if len(chunks) <= 1:
        return [{
            "content": content,
            "metadata": {
                "file_path": filepath,
                "chunk_type": "full_file",
                "name": os.path.basename(filepath),
                "start_line": 1,
                "end_line": len(lines),
            }
        }]

    # Further split any chunks that are too large
    final_chunks = []
    for chunk in chunks:
        if len(chunk["content"]) > max_chunk_size:
            # Split large chunks by paragraph
            sub_chunks = _split_by_size(chunk["content"], max_chunk_size)
            for j, sub in enumerate(sub_chunks):
                final_chunks.append({
                    "content": sub,
                    "metadata": {
                        **chunk["metadata"],
                        "sub_chunk": j,
                    }
                })
        else:
            final_chunks.append(chunk)

    return final_chunks


def chunk_markdown_file(filepath: str, max_chunk_size: int = 2000) -> list[dict]:
    """
    Chunk a Markdown file by headings.
    
    Strategy:
    - Split on ## and ### headings
    - Keep the heading with its content
    - Include parent heading chain for context
    """
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if not content.strip():
        return []

    lines = content.split("\n")
    chunks = []
    current_chunk_lines = []
    current_heading = os.path.basename(filepath)
    parent_heading = ""

    for line in lines:
        heading_match = re.match(r'^(#{1,3})\s+(.+)', line)
        if heading_match and current_chunk_lines:
            # Save previous chunk
            chunk_text = "\n".join(current_chunk_lines)
            if chunk_text.strip():
                chunks.append({
                    "content": chunk_text,
                    "metadata": {
                        "file_path": filepath,
                        "chunk_type": "documentation",
                        "heading": current_heading,
                        "parent_heading": parent_heading,
                    }
                })

            # Update heading context
            level = len(heading_match.group(1))
            if level == 1:
                parent_heading = ""
                current_heading = heading_match.group(2)
            elif level == 2:
                parent_heading = current_heading
                current_heading = heading_match.group(2)
            else:
                current_heading = heading_match.group(2)

            current_chunk_lines = [line]
        else:
            current_chunk_lines.append(line)

    # Save last chunk
    if current_chunk_lines:
        chunk_text = "\n".join(current_chunk_lines)
        if chunk_text.strip():
            chunks.append({
                "content": chunk_text,
                "metadata": {
                    "file_path": filepath,
                    "chunk_type": "documentation",
                    "heading": current_heading,
                    "parent_heading": parent_heading,
                }
            })

    return chunks


def _split_by_size(text: str, max_size: int) -> list[str]:
    """Split text into chunks of max_size characters, breaking at newlines."""
    if len(text) <= max_size:
        return [text]

    chunks = []
    current = []
    current_len = 0

    for line in text.split("\n"):
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > max_size and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        chunks.append("\n".join(current))

    return chunks


async def index_codebase(
    chroma_client: Optional[chromadb.HttpClient] = None,
    codebase_path: str = DEFAULT_CODEBASE_PATH,
) -> dict:
    """
    Index all Python source files from the Saleor codebase into ChromaDB.
    
    Returns dict with: collection_name, documents_indexed, chunks_created
    """
    if chroma_client is None:
        chroma_client = get_chroma_client()

    # Get or create collection
    collection = chroma_client.get_or_create_collection(
        name=CODE_COLLECTION,
        metadata={"description": "Saleor e-commerce Python source code"},
    )

    # Check if already indexed
    existing_count = collection.count()
    if existing_count > 0:
        logger.info(
            "Code collection already has %d documents, skipping indexing",
            existing_count,
        )
        return {
            "collection": CODE_COLLECTION,
            "status": "already_indexed",
            "document_count": existing_count,
        }

    # Find all Python files
    python_files = []
    for root, dirs, files in os.walk(codebase_path):
        # Skip __pycache__ and hidden directories
        dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]
        for f in files:
            if f.endswith(".py") and not f.startswith("__"):
                python_files.append(os.path.join(root, f))

    logger.info("Found %d Python files to index", len(python_files))

    all_documents = []
    all_metadatas = []
    all_ids = []

    for filepath in python_files:
        chunks = chunk_python_file(filepath)
        for i, chunk in enumerate(chunks):
            # Use relative path to avoid ID collisions (multiple modules have models.py, etc.)
            rel_path = os.path.relpath(filepath, codebase_path).replace(os.sep, "_").replace(".", "_")
            doc_id = f"code_{rel_path}_{i}"
            all_documents.append(chunk["content"])
            all_metadatas.append({
                k: str(v) for k, v in chunk["metadata"].items()
            })
            all_ids.append(doc_id)

    if all_documents:
        # Batch insert (ChromaDB handles embedding internally)
        batch_size = 50
        for start in range(0, len(all_documents), batch_size):
            end = min(start + batch_size, len(all_documents))
            collection.add(
                documents=all_documents[start:end],
                metadatas=all_metadatas[start:end],
                ids=all_ids[start:end],
            )

    logger.info(
        "Indexed %d chunks from %d Python files into '%s'",
        len(all_documents), len(python_files), CODE_COLLECTION,
    )

    return {
        "collection": CODE_COLLECTION,
        "status": "indexed",
        "files_processed": len(python_files),
        "chunks_created": len(all_documents),
    }


async def index_docs(
    chroma_client: Optional[chromadb.HttpClient] = None,
    docs_path: Optional[str] = None,
) -> dict:
    """
    Index all Markdown documentation files into ChromaDB.
    
    Returns dict with: collection_name, documents_indexed, chunks_created
    """
    if chroma_client is None:
        chroma_client = get_chroma_client()

    if docs_path is None:
        docs_path = os.path.join(DEFAULT_CODEBASE_PATH, "docs")

    collection = chroma_client.get_or_create_collection(
        name=DOCS_COLLECTION,
        metadata={"description": "Saleor documentation and runbooks"},
    )

    # Check if already indexed
    existing_count = collection.count()
    if existing_count > 0:
        logger.info(
            "Docs collection already has %d documents, skipping indexing",
            existing_count,
        )
        return {
            "collection": DOCS_COLLECTION,
            "status": "already_indexed",
            "document_count": existing_count,
        }

    # Find all Markdown files
    md_files = []
    for root, dirs, files in os.walk(docs_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md"):
                md_files.append(os.path.join(root, f))

    logger.info("Found %d Markdown files to index", len(md_files))

    all_documents = []
    all_metadatas = []
    all_ids = []

    for filepath in md_files:
        chunks = chunk_markdown_file(filepath)
        for i, chunk in enumerate(chunks):
            rel_path = os.path.relpath(filepath, docs_path).replace(os.sep, "_").replace(".", "_")
            doc_id = f"docs_{rel_path}_{i}"
            all_documents.append(chunk["content"])
            all_metadatas.append({
                k: str(v) for k, v in chunk["metadata"].items()
            })
            all_ids.append(doc_id)

    if all_documents:
        batch_size = 50
        for start in range(0, len(all_documents), batch_size):
            end = min(start + batch_size, len(all_documents))
            collection.add(
                documents=all_documents[start:end],
                metadatas=all_metadatas[start:end],
                ids=all_ids[start:end],
            )

    logger.info(
        "Indexed %d chunks from %d Markdown files into '%s'",
        len(all_documents), len(md_files), DOCS_COLLECTION,
    )

    return {
        "collection": DOCS_COLLECTION,
        "status": "indexed",
        "files_processed": len(md_files),
        "chunks_created": len(all_documents),
    }


async def index_all(
    chroma_client: Optional[chromadb.HttpClient] = None,
    codebase_path: str = DEFAULT_CODEBASE_PATH,
) -> dict:
    """Index both code and documentation. Safe to call multiple times."""
    if chroma_client is None:
        chroma_client = get_chroma_client()

    code_result = await index_codebase(chroma_client, codebase_path)
    docs_result = await index_docs(chroma_client, os.path.join(codebase_path, "docs"))

    return {
        "code": code_result,
        "docs": docs_result,
    }
