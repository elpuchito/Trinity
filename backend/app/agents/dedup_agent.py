"""
Trinity — Dedup Agent
Detects duplicate or related incidents using embedding similarity via ChromaDB.
"""

import logging
from uuid import UUID
from typing import Optional

import chromadb

from app.rag.indexer import get_chroma_client

logger = logging.getLogger("triageforge.agents.dedup")

# Name for the incidents embedding collection
INCIDENTS_COLLECTION = "triageforge_incidents"

# Similarity threshold for flagging duplicates
DUPLICATE_THRESHOLD = 0.85
RELATED_THRESHOLD = 0.70


async def run_dedup(state: dict) -> dict:
    """
    Check if the incoming incident is a duplicate of an existing one.
    
    Uses ChromaDB to store and compare incident embeddings.
    A new incident is classified as:
    - Duplicate: similarity > 0.85 with an existing open incident
    - Related: similarity between 0.70 and 0.85
    - Unique: similarity < 0.70
    """
    logger.info("🔄 Dedup Agent: Checking for duplicates...")
    
    incident_id = state.get("incident_id", "unknown")
    title = state.get("structured_title", state.get("raw_title", ""))
    description = state.get("structured_description", state.get("raw_description", ""))
    affected_service = state.get("affected_service", "unknown")
    
    # Compose the text to embed
    incident_text = f"[{affected_service}] {title}: {description}"
    
    try:
        chroma_client = get_chroma_client()
        collection = chroma_client.get_or_create_collection(
            name=INCIDENTS_COLLECTION,
            metadata={"description": "Trinity incident embeddings for dedup"},
        )
        
        current_count = collection.count()
        
        if current_count == 0:
            # No existing incidents to compare against — add this one and return
            logger.info("No existing incidents for dedup comparison, adding first entry")
            collection.add(
                documents=[incident_text],
                ids=[incident_id],
                metadatas=[{
                    "incident_id": incident_id,
                    "title": title[:200],
                    "affected_service": affected_service,
                    "status": "open",
                }],
            )
            state["is_duplicate"] = False
            state["duplicate_of_id"] = None
            state["similarity_scores"] = []
            state["related_incidents"] = []
            return state
        
        # Query for similar incidents
        results = collection.query(
            query_texts=[incident_text],
            n_results=min(5, current_count),
            include=["documents", "metadatas", "distances"],
        )
        
        similarity_scores = []
        is_duplicate = False
        duplicate_of_id = None
        related_incidents = []
        
        if results and results["documents"] and results["documents"][0]:
            for doc, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                # Convert L2 distance to similarity
                similarity = max(0.0, 1.0 - (distance / 2.0))
                existing_id = meta.get("incident_id", "unknown")
                
                # Skip comparing against self
                if existing_id == incident_id:
                    continue
                
                score_entry = {
                    "incident_id": existing_id,
                    "title": meta.get("title", ""),
                    "similarity": round(similarity, 4),
                    "status": meta.get("status", "unknown"),
                }
                similarity_scores.append(score_entry)
                
                if similarity >= DUPLICATE_THRESHOLD and meta.get("status") != "closed":
                    is_duplicate = True
                    duplicate_of_id = existing_id
                    logger.warning(
                        "⚠️ Duplicate detected! %.2f similarity with incident %s",
                        similarity, existing_id,
                    )
                elif similarity >= RELATED_THRESHOLD:
                    related_incidents.append(score_entry)
        
        # Add this incident to the collection for future comparisons
        collection.add(
            documents=[incident_text],
            ids=[incident_id],
            metadatas=[{
                "incident_id": incident_id,
                "title": title[:200],
                "affected_service": affected_service,
                "status": "open",
            }],
        )
        
        state["is_duplicate"] = is_duplicate
        state["duplicate_of_id"] = duplicate_of_id
        state["similarity_scores"] = similarity_scores
        state["related_incidents"] = related_incidents
        
        logger.info(
            "✅ Dedup Agent: is_duplicate=%s, %d related incidents found",
            is_duplicate, len(related_incidents),
        )
        
    except Exception as e:
        logger.error("Dedup agent failed: %s", e)
        state["is_duplicate"] = False
        state["duplicate_of_id"] = None
        state["similarity_scores"] = []
        state["related_incidents"] = []
    
    return state
