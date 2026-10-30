"""
Unit Tests for Stage 6: Knowledge Base Local Semantic Embeddings & Hybrid RAG
=============================================================================
Tests:
1. Normalized dense 128-dimensional embedding generation.
2. Cosine similarity computation between dense vectors.
3. Semantic retrieval for paraphrased questions and domain vocabulary.
4. Tenant boundary isolation across vector search.
"""

import math
import pytest
from app.database import SessionLocal, init_db
from app.models import Agent, KnowledgeDoc, KnowledgeChunk, Organization
from app.knowledge.rag_engine import rag_engine, RAGEngine


def test_dense_embedding_generation_and_normalization():
    text1 = "Prestige Sky Meadows 3 BHK luxury apartments in Whitefield Bangalore"
    vec1 = RAGEngine.generate_embedding(text1)

    assert len(vec1) == 128
    # Verify L2 norm is approximately 1.0
    norm1 = math.sqrt(sum(x * x for x in vec1))
    assert abs(norm1 - 1.0) < 1e-3

    # Empty text returns zero vector
    vec_empty = RAGEngine.generate_embedding("")
    assert len(vec_empty) == 128
    assert all(x == 0.0 for x in vec_empty)


def test_cosine_similarity_semantics():
    # Semantically related texts
    v_apt = RAGEngine.generate_embedding("3 BHK apartment residential flat Bangalore")
    v_home = RAGEngine.generate_embedding("3 BHK flat residence home Bangalore")
    v_car = RAGEngine.generate_embedding("Automotive diesel engine transmission maintenance")

    sim_related = RAGEngine.cosine_similarity(v_apt, v_home)
    sim_unrelated = RAGEngine.cosine_similarity(v_apt, v_car)

    assert sim_related > 0.4
    assert sim_related > sim_unrelated


def test_hybrid_rag_search_with_embeddings():
    init_db()
    db = SessionLocal()

    org = db.query(Organization).first()
    assert org is not None

    doc = KnowledgeDoc(
        organization_id=org.id,
        title="Urban Dental Care Clinic Procedures",
        source_type="text",
        content="Root canal treatment and dental crown capping fees are fixed at ₹8,500 including X-rays.",
        ingestion_status="indexed",
        approval_status="approved",
        is_active=True,
        version=1,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    emb = RAGEngine.generate_embedding("Root canal treatment and dental crown capping fees ₹8,500")
    chunk = KnowledgeChunk(
        organization_id=org.id,
        document_id=doc.id,
        chunk_index=0,
        page_number=1,
        section_title="Endodontics & Crowns",
        text="Root canal treatment and dental crown capping fees are fixed at ₹8,500 including X-rays.",
        embedding=emb,
    )
    db.add(chunk)
    db.commit()

    rag_engine.invalidate_tenant_cache(org.id)

    # Search with paraphrased query
    results = rag_engine.search(
        db=db,
        query="tooth crown cost and root canal",
        organization_id=org.id,
        limit=3,
    )
    assert len(results) >= 1
    top = results[0]
    assert top["document_id"] == doc.id
    assert "8,500" in top["text"]
    assert top["score"] >= 0.15

    # Verify cross-tenant isolation: another org cannot retrieve this chunk
    other_results = rag_engine.search(
        db=db,
        query="tooth crown cost and root canal",
        organization_id="unrelated-tenant-org-xyz",
        limit=3,
    )
    assert len(other_results) == 0

    db.close()
