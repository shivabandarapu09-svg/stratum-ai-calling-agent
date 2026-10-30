"""
Multi-Tenant Company Knowledge Onboarding, Ingestion, Lifecycle & Isolated Retrieval API
========================================================================================
Implements:
- Company / Tenant workspace onboarding and instructor policy configuration.
- Scoped, SSRF-protected, robots.txt-compliant website ingestion and controlled re-crawling.
- Multi-format document ingestion (PDF, DOCX, CSV, TXT, MD, JSON, HTML) with table & page extraction.
- Prompt-injection detection, sanitization, and quarantine warnings.
- Instructor approval workflow (`pending_review` -> `approved` / `disabled`), source replacement (`version++`),
  and deletion with immediate RAG cache invalidation.
- Strict backend tenant isolation (`X-Tenant-ID` / `organization_id`) and audit logging.
"""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Agent,
    KnowledgeAuditLog,
    KnowledgeChunk,
    KnowledgeDoc,
    Organization,
    TenantWorkspaceProfile,
)
from app.schemas import (
    DocumentFileIngestRequest,
    KnowledgeApprovalRequest,
    KnowledgeAuditLogOut,
    KnowledgeDocCreate,
    KnowledgeDocOut,
    KnowledgeSearchQuery,
    KnowledgeSearchResult,
    KnowledgeSourceReplaceRequest,
    TenantWorkspaceOnboardRequest,
    TenantWorkspaceOut,
    TenantWorkspaceUpdateRequest,
    WebsiteIngestRequest,
)
from app.knowledge.rag_engine import rag_engine
from app.knowledge.ingestion_pipeline import (
    DocumentIngestionError,
    MultiFormatDocumentParser,
    PromptInjectionSanitizer,
    RobotsDisallowedError,
    SSRFGuard,
    SSRFViolationError,
    SafeWebsiteCrawler,
    ScopeViolationError,
)

router = APIRouter(prefix="/knowledge", tags=["Multi-Tenant Knowledge Base & Onboarding"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _log_audit(
    db: Session,
    organization_id: str,
    action: str,
    status_str: str = "success",
    actor: str = "instructor@stratum.ai",
    document_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    entry = KnowledgeAuditLog(
        organization_id=organization_id,
        document_id=document_id,
        actor=actor,
        action=action,
        status=status_str,
        details=details or {},
        created_at=utc_now(),
    )
    db.add(entry)
    db.commit()


def _resolve_tenant_id(
    db: Session,
    explicit_org_id: Optional[str] = None,
    x_tenant_id: Optional[str] = None,
) -> str:
    """
    Resolves and validates the active tenant `organization_id`.
    If both `X-Tenant-ID` header and `explicit_org_id` are supplied and mismatch, raises 403 Forbidden.
    """
    if x_tenant_id and explicit_org_id and x_tenant_id != explicit_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant isolation violation: X-Tenant-ID header does not match requested organization_id.",
        )

    target_id = x_tenant_id or explicit_org_id
    if target_id:
        org = db.query(Organization).filter(Organization.id == target_id).first()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant organization '{target_id}' not found.")
        return org.id

    default_org = db.query(Organization).first()
    if not default_org:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No organization initialized.")
    return default_org.id


def _doc_to_out(d: KnowledgeDoc) -> KnowledgeDocOut:
    return KnowledgeDocOut(
        id=d.id,
        organization_id=d.organization_id,
        title=d.title,
        source_type=d.source_type,
        content=d.content,
        agent_id=d.agent_id,
        source_url=d.source_url,
        canonical_url=d.canonical_url,
        file_name=d.file_name,
        content_hash=d.content_hash,
        version=d.version or 1,
        approval_status=d.approval_status or "approved",
        approved_by=d.approved_by,
        approved_at=d.approved_at,
        is_active=True if d.is_active is None else d.is_active,
        ingestion_status=d.ingestion_status or "indexed",
        error_message=d.error_message,
        prompt_injection_flagged=bool(d.prompt_injection_flagged),
        sanitized_warnings=d.sanitized_warnings or [],
        last_checked_at=d.last_checked_at,
        expires_at=d.expires_at,
        created_at=d.created_at,
        chunks_count=len(d.chunks),
    )


# ==============================================================================
# A. Company / Tenant Workspace Onboarding & Instructor Configuration
# ==============================================================================

@router.get("/tenants", response_model=List[TenantWorkspaceOut])
def list_tenant_workspaces(db: Session = Depends(get_db)):
    profiles = db.query(TenantWorkspaceProfile).order_by(TenantWorkspaceProfile.created_at.asc()).all()
    return profiles


@router.post("/tenants/onboard", response_model=TenantWorkspaceOut, status_code=status.HTTP_201_CREATED)
def onboard_company_tenant(payload: TenantWorkspaceOnboardRequest, db: Session = Depends(get_db)):
    """
    Creates an isolated company/tenant workspace (`Organization` + `TenantWorkspaceProfile` + default `Agent`).
    """
    org = Organization(name=payload.company_name.strip())
    db.add(org)
    db.flush()

    profile = TenantWorkspaceProfile(
        organization_id=org.id,
        company_name=payload.company_name.strip(),
        industry=payload.industry,
        products_services=payload.products_services,
        target_audience=payload.target_audience,
        call_objectives=payload.call_objectives,
        preferred_languages=payload.preferred_languages,
        tone=payload.tone,
        faqs=payload.faqs,
        business_policies=payload.business_policies,
        escalation_rules=payload.escalation_rules,
        instructor_instructions=payload.instructor_instructions,
        allowed_website_domains=payload.allowed_website_domains,
        freshness_policy_hours=payload.freshness_policy_hours,
        auto_recrawl_enabled=payload.auto_recrawl_enabled,
        require_instructor_approval=payload.require_instructor_approval,
        updated_by=payload.instructor_email,
        updated_at=utc_now(),
        created_at=utc_now(),
    )
    db.add(profile)

    # Create a dedicated tenant-isolated AI Agent configured with the company's onboarding rules
    default_lang = payload.preferred_languages[0] if payload.preferred_languages else "en"
    transfer_num = (payload.escalation_rules or {}).get("transfer_number", "+919876543210")
    system_prompt = (
        f"You are the official AI calling specialist for {payload.company_name} ({payload.industry}).\n"
        f"Products & Services: {payload.products_services}\n"
        f"Target Audience: {payload.target_audience}\n"
        f"Call Objectives: {payload.call_objectives}\n"
        f"Tone: {payload.tone}\n"
        f"Instructor Instructions: {payload.instructor_instructions}\n"
        f"Business Policies: {payload.business_policies}\n"
        "Strictly ground all factual answers in the company's approved knowledge base and never invent policies or prices."
    )
    tenant_agent = Agent(
        organization_id=org.id,
        name=f"{payload.company_name.split()[0]} Specialist",
        company=payload.company_name.strip(),
        purpose=payload.call_objectives or f"{payload.industry} Customer & Lead Specialist",
        blueprint="custom",
        personality=payload.tone,
        system_prompt=system_prompt,
        greeting=f"Hello! I am calling from {payload.company_name}. How may I help you today?",
        default_language=default_lang,
        supported_languages=payload.preferred_languages or ["en", "hi", "te", "ta", "ml", "kn"],
        transfer_number=transfer_num,
    )
    db.add(tenant_agent)
    db.commit()
    db.refresh(profile)

    _log_audit(
        db=db,
        organization_id=org.id,
        action="onboard_tenant",
        actor=payload.instructor_email,
        details={"company_name": payload.company_name, "agent_id": tenant_agent.id},
    )
    return profile


@router.get("/tenants/{organization_id}/workspace", response_model=TenantWorkspaceOut)
def get_tenant_workspace(
    organization_id: str,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    resolved_id = _resolve_tenant_id(db, explicit_org_id=organization_id, x_tenant_id=x_tenant_id)
    profile = (
        db.query(TenantWorkspaceProfile)
        .filter(TenantWorkspaceProfile.organization_id == resolved_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Tenant workspace profile not found.")
    return profile


@router.put("/tenants/{organization_id}/workspace", response_model=TenantWorkspaceOut)
def update_tenant_workspace(
    organization_id: str,
    payload: TenantWorkspaceUpdateRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    resolved_id = _resolve_tenant_id(db, explicit_org_id=organization_id, x_tenant_id=x_tenant_id)
    profile = (
        db.query(TenantWorkspaceProfile)
        .filter(TenantWorkspaceProfile.organization_id == resolved_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Tenant workspace profile not found.")

    update_fields = payload.model_dump(exclude_unset=True)
    for k, v in update_fields.items():
        setattr(profile, k, v)
    profile.updated_at = utc_now()
    db.commit()
    db.refresh(profile)
    rag_engine.invalidate_tenant_cache(resolved_id)

    _log_audit(
        db=db,
        organization_id=resolved_id,
        action="update_workspace_profile",
        actor=payload.updated_by,
        details={"updated_fields": list(update_fields.keys())},
    )
    return profile


# ==============================================================================
# B. Website Ingestion & Controlled Re-Crawl (SSRF & Prompt-Injection Protected)
# ==============================================================================

@router.post("/ingest/website", response_model=List[KnowledgeDocOut], status_code=status.HTTP_201_CREATED)
def ingest_website_source(
    payload: WebsiteIngestRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    tenant_id = _resolve_tenant_id(db, explicit_org_id=payload.organization_id, x_tenant_id=x_tenant_id)
    profile = (
        db.query(TenantWorkspaceProfile)
        .filter(TenantWorkspaceProfile.organization_id == tenant_id)
        .first()
    )
    allowed_domains = profile.allowed_website_domains if profile else []

    try:
        crawled_pages, crawl_errors = SafeWebsiteCrawler.crawl(
            start_url=payload.url,
            max_pages=payload.max_pages,
            allowed_scope_prefix=payload.allowed_scope_prefix,
            allowed_domains=allowed_domains if allowed_domains else None,
            simulated_html_pages=payload.simulated_html_pages,
            simulated_robots_txt=payload.simulated_robots_txt,
        )
    except SSRFViolationError as ssrf_exc:
        _log_audit(
            db=db,
            organization_id=tenant_id,
            action="ssrf_blocked",
            status_str="blocked",
            details={"url": payload.url, "reason": str(ssrf_exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ssrf_exc)) from ssrf_exc
    except (ScopeViolationError, RobotsDisallowedError) as scope_exc:
        _log_audit(
            db=db,
            organization_id=tenant_id,
            action="crawl_scope_or_robots_blocked",
            status_str="blocked",
            details={"url": payload.url, "reason": str(scope_exc)},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(scope_exc)) from scope_exc

    if not crawled_pages:
        err_detail = crawl_errors[0]["error"] if crawl_errors else "No indexable pages found."
        _log_audit(
            db=db,
            organization_id=tenant_id,
            action="ingest_website_failed",
            status_str="failed",
            details={"url": payload.url, "errors": crawl_errors},
        )
        raise HTTPException(
            status_code=422,
            detail=f"Website ingestion failed: {err_detail}",
        )

    require_approval = profile.require_instructor_approval if profile else True
    approval_state = "approved" if (payload.auto_approve or not require_approval) else "pending_review"
    freshness_hours = profile.freshness_policy_hours if profile else 168
    expires_at = utc_now() + timedelta(hours=freshness_hours)

    created_docs: List[KnowledgeDocOut] = []
    for page in crawled_pages:
        # Check if canonical_url already exists for this tenant -> update in-place or skip if identical hash
        existing = (
            db.query(KnowledgeDoc)
            .filter(
                KnowledgeDoc.organization_id == tenant_id,
                KnowledgeDoc.canonical_url == page.canonical_url,
            )
            .first()
        )
        if existing:
            if existing.content_hash == page.content_hash:
                existing.last_checked_at = utc_now()
                existing.expires_at = expires_at
                db.commit()
                created_docs.append(_doc_to_out(existing))
                _log_audit(
                    db=db,
                    organization_id=tenant_id,
                    document_id=existing.id,
                    action="ingest_website",
                    details={
                        "canonical_url": page.canonical_url,
                        "version": existing.version,
                        "deduplicated_unchanged": True,
                        "prompt_injection_flagged": page.prompt_injection_flagged,
                    },
                )
                continue
            else:
                # Controlled re-crawl update: increment version and re-index chunks
                existing.version = (existing.version or 1) + 1
                existing.title = page.title
                existing.content = page.content
                existing.content_hash = page.content_hash
                existing.prompt_injection_flagged = page.prompt_injection_flagged
                existing.sanitized_warnings = page.sanitized_warnings
                existing.last_checked_at = utc_now()
                existing.expires_at = expires_at
                db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == existing.id).delete()
                doc_obj = existing
        else:
            doc_obj = KnowledgeDoc(
                organization_id=tenant_id,
                agent_id=payload.agent_id,
                title=page.title,
                source_type="url",
                source_url=page.url,
                canonical_url=page.canonical_url,
                content=page.content,
                content_hash=page.content_hash,
                version=1,
                approval_status=approval_state,
                approved_by="auto_approved" if approval_state == "approved" else None,
                approved_at=utc_now() if approval_state == "approved" else None,
                is_active=True,
                ingestion_status="indexed",
                prompt_injection_flagged=page.prompt_injection_flagged,
                sanitized_warnings=page.sanitized_warnings,
                last_checked_at=utc_now(),
                expires_at=expires_at,
            )
            db.add(doc_obj)
            db.flush()

        # Index sections into tenant-tagged chunks
        chunk_idx = 0
        for sec_title, sec_text in page.sections:
            for piece in rag_engine.chunk_text(sec_text):
                ch = KnowledgeChunk(
                    organization_id=tenant_id,
                    document_id=doc_obj.id,
                    chunk_index=chunk_idx,
                    page_number=1,
                    section_title=sec_title,
                    text=piece,
                    table_data=page.tables[0] if (chunk_idx == 0 and page.tables) else None,
                    content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
                )
                db.add(ch)
                chunk_idx += 1

        db.commit()
        db.refresh(doc_obj)
        created_docs.append(_doc_to_out(doc_obj))

        _log_audit(
            db=db,
            organization_id=tenant_id,
            document_id=doc_obj.id,
            action="ingest_website",
            details={
                "canonical_url": page.canonical_url,
                "version": doc_obj.version,
                "approval_status": doc_obj.approval_status,
                "prompt_injection_flagged": page.prompt_injection_flagged,
                "warnings": page.sanitized_warnings,
            },
        )

    rag_engine.invalidate_tenant_cache(tenant_id)
    return created_docs


# ==============================================================================
# C. Multi-Format Document Ingestion (PDF, DOCX, CSV, TXT, MD, JSON, HTML)
# ==============================================================================

@router.post("/ingest/document", response_model=KnowledgeDocOut, status_code=status.HTTP_201_CREATED)
def ingest_document_source(
    payload: DocumentFileIngestRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    tenant_id = _resolve_tenant_id(db, explicit_org_id=payload.organization_id, x_tenant_id=x_tenant_id)
    raw_bytes: Optional[bytes] = None
    if payload.file_content_base64:
        try:
            raw_bytes = base64.b64decode(payload.file_content_base64)
        except Exception as b64_exc:
            raise HTTPException(status_code=400, detail=f"Invalid base64 file content: {b64_exc}") from b64_exc

    try:
        parsed = MultiFormatDocumentParser.parse_document(
            file_name=payload.file_name,
            raw_bytes=raw_bytes,
            raw_text=payload.raw_text,
            title=payload.title,
        )
    except DocumentIngestionError as doc_err:
        _log_audit(
            db=db,
            organization_id=tenant_id,
            action="upload_document_failed",
            status_str="failed",
            details={"file_name": payload.file_name, "error": str(doc_err)},
        )
        raise HTTPException(status_code=422, detail=str(doc_err)) from doc_err

    profile = (
        db.query(TenantWorkspaceProfile)
        .filter(TenantWorkspaceProfile.organization_id == tenant_id)
        .first()
    )
    require_approval = profile.require_instructor_approval if profile else True
    approval_state = "approved" if (payload.auto_approve or not require_approval) else "pending_review"
    freshness_hours = profile.freshness_policy_hours if profile else 168

    doc_obj = KnowledgeDoc(
        organization_id=tenant_id,
        agent_id=payload.agent_id,
        title=parsed.title,
        source_type=parsed.source_type,
        file_name=parsed.file_name,
        content=parsed.full_text,
        content_hash=parsed.content_hash,
        version=1,
        approval_status=approval_state,
        approved_by="instructor_auto" if approval_state == "approved" else None,
        approved_at=utc_now() if approval_state == "approved" else None,
        is_active=True,
        ingestion_status="indexed",
        prompt_injection_flagged=parsed.prompt_injection_flagged,
        sanitized_warnings=parsed.sanitized_warnings,
        last_checked_at=utc_now(),
        expires_at=utc_now() + timedelta(hours=freshness_hours),
    )
    db.add(doc_obj)
    db.flush()

    chunk_idx = 0
    for unit in parsed.chunks:
        pieces = rag_engine.chunk_text(unit.text)
        for piece in pieces:
            ch = KnowledgeChunk(
                organization_id=tenant_id,
                document_id=doc_obj.id,
                chunk_index=chunk_idx,
                page_number=unit.page_number,
                section_title=unit.section_title,
                text=piece,
                table_data=unit.table_data if chunk_idx == 0 else None,
                content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
            )
            db.add(ch)
            chunk_idx += 1

    db.commit()
    db.refresh(doc_obj)
    rag_engine.invalidate_tenant_cache(tenant_id)

    _log_audit(
        db=db,
        organization_id=tenant_id,
        document_id=doc_obj.id,
        action="upload_document",
        details={
            "file_name": parsed.file_name,
            "source_type": parsed.source_type,
            "chunks_count": chunk_idx,
            "approval_status": approval_state,
            "prompt_injection_flagged": parsed.prompt_injection_flagged,
            "warnings": parsed.sanitized_warnings,
        },
    )
    return _doc_to_out(doc_obj)


@router.post("/upload-file", response_model=KnowledgeDocOut, status_code=status.HTTP_201_CREATED)
async def upload_multipart_document(
    file: UploadFile = File(...),
    organization_id: Optional[str] = Form(default=None),
    agent_id: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
    auto_approve: bool = Form(default=False),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    raw_bytes = await file.read()
    b64_str = base64.b64encode(raw_bytes).decode("utf-8") if raw_bytes else ""
    req = DocumentFileIngestRequest(
        organization_id=organization_id,
        agent_id=agent_id,
        file_name=file.filename or "uploaded.txt",
        file_content_base64=b64_str if raw_bytes else None,
        title=title or file.filename,
        auto_approve=auto_approve,
    )
    return ingest_document_source(payload=req, x_tenant_id=x_tenant_id, db=db)


# ==============================================================================
# D & F. Knowledge Lifecycle, Approval, Replacement, Deletion & Isolated Search
# ==============================================================================

@router.get("", response_model=List[KnowledgeDocOut])
def list_documents(
    organization_id: Optional[str] = Query(default=None),
    approval_status: Optional[str] = Query(default=None),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    tenant_id = _resolve_tenant_id(db, explicit_org_id=organization_id, x_tenant_id=x_tenant_id)
    q = db.query(KnowledgeDoc).filter(KnowledgeDoc.organization_id == tenant_id)
    if approval_status:
        q = q.filter(KnowledgeDoc.approval_status == approval_status)
    docs = q.order_by(KnowledgeDoc.created_at.desc()).all()
    return [_doc_to_out(d) for d in docs]


@router.post("", response_model=KnowledgeDocOut, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: KnowledgeDocCreate,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    tenant_id = _resolve_tenant_id(db, explicit_org_id=payload.organization_id, x_tenant_id=x_tenant_id)
    sanitized_content, inj_flagged, warnings = PromptInjectionSanitizer.sanitize(payload.content)
    if not sanitized_content:
        raise HTTPException(status_code=422, detail="Document content is empty.")

    content_hash = hashlib.sha256(sanitized_content.encode("utf-8")).hexdigest()
    # Direct create_document preserves approved default unless auto_approve is False and tenant requires review
    approval_state = "approved" if payload.auto_approve or payload.organization_id is None else "pending_review"

    doc = KnowledgeDoc(
        organization_id=tenant_id,
        agent_id=payload.agent_id,
        title=payload.title,
        source_type=payload.source_type,
        source_url=payload.source_url,
        file_name=payload.file_name,
        content=sanitized_content,
        content_hash=content_hash,
        version=1,
        approval_status=approval_state,
        approved_by="instructor@stratum.ai" if approval_state == "approved" else None,
        approved_at=utc_now() if approval_state == "approved" else None,
        is_active=True,
        ingestion_status="indexed",
        prompt_injection_flagged=inj_flagged,
        sanitized_warnings=warnings,
        last_checked_at=utc_now(),
    )
    db.add(doc)
    db.flush()

    raw_chunks = rag_engine.chunk_text(sanitized_content)
    for idx, chunk_str in enumerate(raw_chunks):
        ch = KnowledgeChunk(
            organization_id=tenant_id,
            document_id=doc.id,
            chunk_index=idx,
            page_number=1,
            section_title=payload.title,
            text=chunk_str,
            content_hash=hashlib.sha256(chunk_str.encode("utf-8")).hexdigest(),
        )
        db.add(ch)

    db.commit()
    db.refresh(doc)
    rag_engine.invalidate_tenant_cache(tenant_id)
    return _doc_to_out(doc)


@router.post("/{doc_id}/approval", response_model=KnowledgeDocOut)
def approve_or_disable_source(
    doc_id: str,
    payload: KnowledgeApprovalRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if x_tenant_id and doc.organization_id != x_tenant_id:
        _log_audit(
            db=db,
            organization_id=x_tenant_id,
            document_id=doc_id,
            action="cross_tenant_approval_blocked",
            status_str="forbidden",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access denied.")

    action = payload.action.lower().strip()
    if action == "approve":
        doc.approval_status = "approved"
        doc.is_active = True
        doc.approved_by = payload.actor
        doc.approved_at = utc_now()
    elif action == "disable":
        doc.approval_status = "disabled"
        doc.is_active = False
    else:
        raise HTTPException(status_code=400, detail="Unsupported action. Use 'approve' or 'disable'.")

    db.commit()
    db.refresh(doc)
    rag_engine.invalidate_tenant_cache(doc.organization_id)

    _log_audit(
        db=db,
        organization_id=doc.organization_id,
        document_id=doc.id,
        actor=payload.actor,
        action=f"{action}_source",
        details={"title": doc.title, "approval_status": doc.approval_status},
    )
    return _doc_to_out(doc)


@router.put("/{doc_id}", response_model=KnowledgeDocOut)
def replace_knowledge_source(
    doc_id: str,
    payload: KnowledgeSourceReplaceRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    """
    Replaces a source's content, increments its version, re-indexes its chunks,
    and invalidates the tenant RAG cache so old content is never retrieved.
    """
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if x_tenant_id and doc.organization_id != x_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant modification denied.")

    sanitized_content, inj_flagged, warnings = PromptInjectionSanitizer.sanitize(payload.content)
    if not sanitized_content:
        raise HTTPException(status_code=422, detail="Replacement content cannot be empty.")

    if payload.title:
        doc.title = payload.title
    doc.content = sanitized_content
    doc.content_hash = hashlib.sha256(sanitized_content.encode("utf-8")).hexdigest()
    doc.version = (doc.version or 1) + 1
    doc.prompt_injection_flagged = inj_flagged
    doc.sanitized_warnings = warnings
    doc.last_checked_at = utc_now()
    if payload.auto_approve:
        doc.approval_status = "approved"
        doc.is_active = True
        doc.approved_by = payload.actor
        doc.approved_at = utc_now()

    # Delete old chunks and re-index new chunks
    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).delete()
    raw_chunks = rag_engine.chunk_text(sanitized_content)
    for idx, chunk_str in enumerate(raw_chunks):
        ch = KnowledgeChunk(
            organization_id=doc.organization_id,
            document_id=doc.id,
            chunk_index=idx,
            page_number=1,
            section_title=doc.title,
            text=chunk_str,
            content_hash=hashlib.sha256(chunk_str.encode("utf-8")).hexdigest(),
        )
        db.add(ch)

    db.commit()
    db.refresh(doc)
    rag_engine.invalidate_tenant_cache(doc.organization_id)

    _log_audit(
        db=db,
        organization_id=doc.organization_id,
        document_id=doc.id,
        actor=payload.actor,
        action="replace_source",
        details={"version": doc.version, "content_hash": doc.content_hash},
    )
    return _doc_to_out(doc)


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if x_tenant_id and doc.organization_id != x_tenant_id:
        _log_audit(
            db=db,
            organization_id=x_tenant_id,
            document_id=doc_id,
            action="cross_tenant_delete_blocked",
            status_str="forbidden",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant deletion denied.")

    org_id = doc.organization_id
    title = doc.title
    db.delete(doc)
    db.commit()
    rag_engine.invalidate_tenant_cache(org_id)

    _log_audit(
        db=db,
        organization_id=org_id,
        document_id=doc_id,
        action="delete_source",
        details={"title": title},
    )
    return {"status": "success", "message": "Document and indexed chunks deleted, cache invalidated."}


@router.post("/search", response_model=List[KnowledgeSearchResult])
def test_search(
    query_req: KnowledgeSearchQuery,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    tenant_id = _resolve_tenant_id(db, explicit_org_id=query_req.organization_id, x_tenant_id=x_tenant_id)
    results = rag_engine.search(
        db=db,
        query=query_req.query,
        organization_id=tenant_id,
        agent_id=query_req.agent_id,
        limit=query_req.limit,
    )
    return [
        KnowledgeSearchResult(
            document_id=r.get("document_id"),
            document_title=r["document_title"],
            source_type=r.get("source_type", "txt"),
            canonical_url=r.get("canonical_url"),
            page_number=r.get("page_number", 1),
            section_title=r.get("section_title", "General"),
            version=r.get("version", 1),
            citation=r.get("citation", ""),
            text=r["text"],
            score=r["score"],
        )
        for r in results
    ]


@router.get("/audit-logs", response_model=List[KnowledgeAuditLogOut])
def list_knowledge_audit_logs(
    organization_id: Optional[str] = Query(default=None),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
):
    tenant_id = _resolve_tenant_id(db, explicit_org_id=organization_id, x_tenant_id=x_tenant_id)
    logs = (
        db.query(KnowledgeAuditLog)
        .filter(KnowledgeAuditLog.organization_id == tenant_id)
        .order_by(KnowledgeAuditLog.created_at.desc())
        .limit(50)
        .all()
    )
    return logs
