"""
Multi-Tenant Company Knowledge Ingestion Pipeline
=================================================
Provides:
1. `SSRFGuard`: Blocks localhost, RFC1918 private IPs, link-local / cloud metadata endpoints
   (169.254.169.254), CGNAT, IPv6 private/loopback, unsafe URL schemes, and malicious redirects.
2. `PromptInjectionSanitizer`: Detects and neutralizes prompt-injection payloads and hidden HTML
   adversarial instructions embedded in web pages or uploaded documents.
3. `SafeWebsiteCrawler`: Enforces approved domain/path scope, respects `robots.txt` and rate limits,
   extracts canonical URLs, titles, section headings, and tables, and deduplicates pages.
4. `MultiFormatDocumentParser`: Extracts text, sections, page numbers, and tables from TXT, CSV,
   MD, JSON, HTML, DOCX (Word XML), and PDF (including scanned-PDF OCR detection).
"""

import base64
import csv
import hashlib
import io
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx


class SSRFViolationError(ValueError):
    """Raised when a URL or redirect target violates SSRF security rules."""


class RobotsDisallowedError(PermissionError):
    """Raised when robots.txt disallows crawling the requested URL."""


class ScopeViolationError(PermissionError):
    """Raised when a URL falls outside the tenant's approved website scope."""


class DocumentIngestionError(ValueError):
    """Raised when a document is unsupported, empty, corrupt, or requires OCR."""


# ==============================================================================
# 1. SSRF Protection Guard
# ==============================================================================

FORBIDDEN_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "metadata",
    "instance-data",
    "169.254.169.254",
    "0.0.0.0",
}

ALLOWED_SCHEMES = {"http", "https"}
CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


class SSRFGuard:
    """
    Validates URLs and resolved IP addresses against Server-Side Request Forgery (SSRF).
    """

    @classmethod
    def validate_ip_string(cls, ip_str: str) -> None:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise SSRFViolationError(f"Invalid IP address format: {ip_str}") from exc

        if (
            ip_obj.is_loopback
            or ip_obj.is_private
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
            or (isinstance(ip_obj, ipaddress.IPv4Address) and ip_obj in CGNAT_NETWORK)
        ):
            raise SSRFViolationError(
                f"SSRF Blocked: IP address {ip_str} belongs to a restricted internal/private/metadata range."
            )

    @classmethod
    def validate_url(cls, url: str, resolve_dns: bool = False) -> urllib.parse.ParseResult:
        if not url or not isinstance(url, str):
            raise SSRFViolationError("Empty or invalid URL.")

        parsed = urllib.parse.urlparse(url.strip())
        scheme = (parsed.scheme or "").lower()
        if scheme not in ALLOWED_SCHEMES:
            raise SSRFViolationError(
                f"SSRF Blocked: Unsupported URL scheme '{scheme}'. Only http and https are permitted."
            )

        if not parsed.netloc or not parsed.hostname:
            raise SSRFViolationError("SSRF Blocked: URL is missing a valid hostname.")

        if parsed.username or parsed.password:
            raise SSRFViolationError("SSRF Blocked: Credentials embedded in URL are not permitted.")

        hostname = parsed.hostname.lower().strip(".")
        if (
            hostname in FORBIDDEN_HOSTNAMES
            or hostname.endswith(".local")
            or hostname.endswith(".internal")
            or hostname.endswith(".localhost")
        ):
            raise SSRFViolationError(f"SSRF Blocked: Forbidden internal hostname '{hostname}'.")

        # Catch integer or hex encoded IPv4 literals first (e.g., 2130706433 or 0x7f000001)
        if re.match(r"^(0x[0-9a-f]+|\d+)$", hostname):
            raise SSRFViolationError(f"SSRF Blocked: Numeric/hex IP literal '{hostname}' is not permitted.")

        # Check if hostname is a literal IPv4/IPv6 address
        try:
            ipaddress.ip_address(hostname)
            is_ip_literal = True
        except ValueError:
            is_ip_literal = False

        if is_ip_literal:
            cls.validate_ip_string(hostname)
            return parsed

        if resolve_dns:
            try:
                addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if scheme == "https" else 80))
                for family, _, _, _, sockaddr in addr_info:
                    resolved_ip = sockaddr[0]
                    cls.validate_ip_string(resolved_ip)
            except SSRFViolationError:
                raise
            except socket.gaierror as exc:
                raise SSRFViolationError(f"DNS resolution failed for host '{hostname}': {exc}") from exc

        return parsed


# ==============================================================================
# 2. Prompt-Injection Detection & Sanitization
# ==============================================================================

PROMPT_INJECTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"ignore\s+(?:all\s+)?(?:previous|prior|above|system|earlier)\s+(?:instructions|prompts|rules|directives|guidelines)",
            re.IGNORECASE,
        ),
        "directive_override_ignore_previous",
    ),
    (
        re.compile(
            r"disregard\s+(?:all\s+)?(?:previous|prior|system|safety|company)\s+(?:instructions|rules|policies|prompts)",
            re.IGNORECASE,
        ),
        "directive_override_disregard_rules",
    ),
    (
        re.compile(
            r"(?:system\s*prompt\s*override|new\s*system\s*instructions|developer\s*mode\s*enabled|act\s*as\s*an\s*unrestricted)",
            re.IGNORECASE,
        ),
        "system_prompt_hijack",
    ),
    (
        re.compile(
            r"(?:reveal|print|output|repeat)\s+(?:your\s+)?(?:system\s+prompt|hidden\s+instructions|api\s+keys|secret)",
            re.IGNORECASE,
        ),
        "system_prompt_exfiltration",
    ),
    (
        re.compile(
            r"(?:approve\s+(?:a\s+)?(?:90|100)%\s+discount|tell\s+the\s+customer\s+everything\s+is\s+free|bypass\s+caller\s+verification)",
            re.IGNORECASE,
        ),
        "business_policy_hijack",
    ),
]


class PromptInjectionSanitizer:
    """
    Scans extracted text from websites and documents for embedded prompt injections,
    strips adversarial instructions, and flags warnings for instructor review.
    """

    @classmethod
    def sanitize(cls, text: str) -> Tuple[str, bool, List[str]]:
        if not text:
            return "", False, []

        sanitized = text
        warnings: List[str] = []

        # Strip raw <script>, <style>, and hidden inline styles if any HTML slipped into raw text
        hidden_html_pattern = re.compile(
            r"<[^>]+style\s*=\s*['\"][^'\"]*(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0|font-size\s*:\s*0)[^'\"]*['\"][^>]*>.*?</[^>]+>",
            re.IGNORECASE | re.DOTALL,
        )
        if hidden_html_pattern.search(sanitized):
            warnings.append("hidden_html_css_payload_removed")
            sanitized = hidden_html_pattern.sub(" ", sanitized)

        for pattern, label in PROMPT_INJECTION_PATTERNS:
            if pattern.search(sanitized):
                warnings.append(label)
                sanitized = pattern.sub("[REDACTED_UNTRUSTED_INSTRUCTION]", sanitized)

        is_flagged = len(warnings) > 0
        return sanitized.strip(), is_flagged, warnings


# ==============================================================================
# 3. HTML Content, Canonical URL, Heading & Table Extractor
# ==============================================================================

class StructuredHTMLParser(HTMLParser):
    """
    Extracts clean text, `<title>`, `<link rel="canonical">`, section headings (`h1`-`h3`),
    hyperlinks (`<a href>`), and structured tables (`<table>`) while ignoring `<script>`,
    `<style>`, `<noscript>`, and hidden DOM elements.
    """

    def __init__(self):
        super().__init__()
        self.title: str = ""
        self.canonical_url: Optional[str] = None
        self.links: List[str] = []
        self.sections: List[Tuple[str, str]] = []  # (section_title, text)
        self.tables: List[List[List[str]]] = []

        self._ignore_depth: int = 0
        self._in_title: bool = False
        self._in_heading: bool = False
        self._current_section_title: str = "Overview"
        self._current_section_buf: List[str] = []
        self._heading_buf: List[str] = []

        self._in_table: bool = False
        self._current_table: List[List[str]] = []
        self._current_row: List[str] = []
        self._current_cell: List[str] = []
        self._in_cell: bool = False
        self.hidden_element_detected: bool = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_l = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        # Check hidden styles (often used to hide prompt injection in web pages)
        style_val = attr_dict.get("style", "").lower()
        if any(
            h in style_val
            for h in ["display:none", "display: none", "visibility:hidden", "visibility: hidden", "opacity:0", "font-size:0"]
        ) or "hidden" in attr_dict:
            self.hidden_element_detected = True
            self._ignore_depth += 1
            return

        if self._ignore_depth > 0:
            self._ignore_depth += 1
            return

        if tag_l in ("script", "style", "noscript", "svg", "iframe"):
            self._ignore_depth = 1
            return

        if tag_l == "title":
            self._in_title = True
        elif tag_l == "link":
            rel = attr_dict.get("rel", "").lower()
            href = attr_dict.get("href", "").strip()
            if "canonical" in rel and href:
                self.canonical_url = href
        elif tag_l == "a":
            href = attr_dict.get("href", "").strip()
            if href:
                self.links.append(href)
        elif tag_l in ("h1", "h2", "h3"):
            self._flush_section()
            self._in_heading = True
            self._heading_buf = []
        elif tag_l == "table":
            self._in_table = True
            self._current_table = []
        elif tag_l == "tr" and self._in_table:
            self._current_row = []
        elif tag_l in ("td", "th") and self._in_table:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if self._ignore_depth > 0:
            self._ignore_depth -= 1
            return

        if tag_l == "title":
            self._in_title = False
        elif tag_l in ("h1", "h2", "h3") and self._in_heading:
            self._in_heading = False
            heading_txt = " ".join(" ".join(self._heading_buf).split()).strip()
            if heading_txt:
                self._current_section_title = heading_txt
        elif tag_l in ("td", "th") and self._in_cell:
            self._in_cell = False
            cell_txt = " ".join(" ".join(self._current_cell).split()).strip()
            self._current_row.append(cell_txt)
        elif tag_l == "tr" and self._in_table:
            if any(self._current_row):
                self._current_table.append(self._current_row)
                self._current_section_buf.append(" | ".join(self._current_row))
        elif tag_l == "table" and self._in_table:
            self._in_table = False
            if self._current_table:
                self.tables.append(self._current_table)

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        if self._in_title:
            self.title = (self.title + " " + cleaned).strip()
        elif self._in_heading:
            self._heading_buf.append(cleaned)
        elif self._in_cell:
            self._current_cell.append(cleaned)
        else:
            self._current_section_buf.append(cleaned)

    def _flush_section(self) -> None:
        body = " ".join(" ".join(self._current_section_buf).split()).strip()
        if body:
            self.sections.append((self._current_section_title, body))
        self._current_section_buf = []

    def finalize(self) -> None:
        self._flush_section()


# ==============================================================================
# 4. Safe Website Crawler (Scoped, Robots.txt-Compliant, Deduplicating)
# ==============================================================================

@dataclass
class CrawledPageResult:
    url: str
    canonical_url: str
    title: str
    content: str
    content_hash: str
    sections: List[Tuple[str, str]]
    tables: List[List[List[str]]]
    prompt_injection_flagged: bool
    sanitized_warnings: List[str]
    last_checked_at: datetime


class SafeWebsiteCrawler:
    """
    Crawls only permitted pages within an approved domain/path scope, enforces SSRF protections,
    respects `robots.txt`, deduplicates canonical URLs & content hashes, and sanitizes prompt injections.
    """

    USER_AGENT = "StratumKnowledgeBot/3.0 (+https://stratum.ai/bot)"

    @classmethod
    def normalize_canonical_url(cls, base_url: str, candidate_url: Optional[str] = None) -> str:
        target = urllib.parse.urljoin(base_url, candidate_url) if candidate_url else base_url
        parsed = SSRFGuard.validate_url(target, resolve_dns=False)
        clean_path = parsed.path or "/"
        if len(clean_path) > 1 and clean_path.endswith("/"):
            clean_path = clean_path.rstrip("/")
        return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), clean_path, "", parsed.query, ""))

    @classmethod
    def is_within_scope(
        cls,
        target_url: str,
        root_parsed: urllib.parse.ParseResult,
        allowed_scope_prefix: Optional[str] = None,
        allowed_domains: Optional[List[str]] = None,
    ) -> bool:
        try:
            parsed = SSRFGuard.validate_url(target_url, resolve_dns=False)
        except SSRFViolationError:
            return False

        host = (parsed.hostname or "").lower()
        root_host = (root_parsed.hostname or "").lower()

        if allowed_domains:
            norm_domains = [d.lower().strip() for d in allowed_domains if d.strip()]
            if norm_domains and not any(host == d or host.endswith("." + d) for d in norm_domains):
                return False
        elif host != root_host:
            return False

        if allowed_scope_prefix:
            if not (parsed.path or "/").startswith(allowed_scope_prefix):
                return False
        else:
            root_dir = root_parsed.path.rsplit("/", 1)[0] if "/" in root_parsed.path else ""
            if root_dir and not (parsed.path or "/").startswith(root_dir):
                return False

        return True

    @classmethod
    def check_robots_txt(
        cls,
        url: str,
        robots_txt_content: Optional[str] = None,
    ) -> bool:
        rp = urllib.robotparser.RobotFileParser()
        if robots_txt_content is not None:
            rp.parse(robots_txt_content.splitlines())
            return rp.can_fetch(cls.USER_AGENT, url) and rp.can_fetch("*", url)
        return True

    @classmethod
    def crawl(
        cls,
        start_url: str,
        max_pages: int = 3,
        allowed_scope_prefix: Optional[str] = None,
        allowed_domains: Optional[List[str]] = None,
        simulated_html_pages: Optional[Dict[str, str]] = None,
        simulated_robots_txt: Optional[str] = None,
    ) -> Tuple[List[CrawledPageResult], List[Dict[str, str]]]:
        """
        Crawls up to `max_pages` within scope.
        Returns `(crawled_pages, errors)`.
        """
        root_parsed = SSRFGuard.validate_url(start_url, resolve_dns=(simulated_html_pages is None))
        if not cls.is_within_scope(start_url, root_parsed, allowed_scope_prefix, allowed_domains):
            raise ScopeViolationError(f"Start URL '{start_url}' is outside the tenant's allowed website domains/scope.")

        # Fetch live robots.txt if not simulated
        robots_text = simulated_robots_txt
        if robots_text is None and simulated_html_pages is None:
            robots_url = f"{root_parsed.scheme}://{root_parsed.netloc}/robots.txt"
            try:
                with httpx.Client(timeout=3.0, follow_redirects=False) as client:
                    r_resp = client.get(robots_url, headers={"User-Agent": cls.USER_AGENT})
                    if r_resp.status_code == 200:
                        robots_text = r_resp.text
            except Exception:
                robots_text = ""

        queue: List[str] = [cls.normalize_canonical_url(start_url)]
        visited_urls: Set[str] = set()
        seen_hashes: Set[str] = set()
        results: List[CrawledPageResult] = []
        errors: List[Dict[str, str]] = []

        while queue and len(results) < max(1, min(max_pages, 10)):
            current_url = queue.pop(0)
            if current_url in visited_urls:
                continue
            visited_urls.add(current_url)

            # 1. SSRF & Scope check
            try:
                SSRFGuard.validate_url(current_url, resolve_dns=(simulated_html_pages is None))
            except SSRFViolationError as ssrf_err:
                errors.append({"url": current_url, "error": str(ssrf_err)})
                continue

            if not cls.is_within_scope(current_url, root_parsed, allowed_scope_prefix, allowed_domains):
                errors.append({"url": current_url, "error": "Out of approved crawl scope"})
                continue

            # 2. Robots.txt check
            if not cls.check_robots_txt(current_url, robots_text):
                errors.append({"url": current_url, "error": "Blocked by robots.txt policy"})
                continue

            # 3. Fetch HTML (from simulated map or live HTTP with safe redirect validation)
            raw_html = ""
            if simulated_html_pages is not None:
                raw_html = simulated_html_pages.get(current_url) or simulated_html_pages.get(start_url, "")
                if not raw_html:
                    errors.append({"url": current_url, "error": "404 Not Found in page map"})
                    continue
                # Support simulated redirect header prefix `REDIRECT: <target_url>`
                if raw_html.startswith("REDIRECT:"):
                    redirect_target = raw_html.split("REDIRECT:", 1)[1].strip()
                    resolved_redirect = urllib.parse.urljoin(current_url, redirect_target)
                    # Validate redirect target against SSRF and Scope!
                    SSRFGuard.validate_url(resolved_redirect, resolve_dns=False)
                    if not cls.is_within_scope(resolved_redirect, root_parsed, allowed_scope_prefix, allowed_domains):
                        raise ScopeViolationError(f"Unsafe redirect to out-of-scope URL: {resolved_redirect}")
                    queue.insert(0, cls.normalize_canonical_url(resolved_redirect))
                    continue
            else:
                try:
                    raw_html, current_url = cls._fetch_url_safely(current_url, root_parsed, allowed_scope_prefix, allowed_domains)
                except (SSRFViolationError, ScopeViolationError) as sec_err:
                    raise sec_err
                except Exception as fetch_err:
                    errors.append({"url": current_url, "error": str(fetch_err)})
                    continue

            # 4. Parse HTML structure
            parser = StructuredHTMLParser()
            parser.feed(raw_html)
            parser.finalize()

            canonical = cls.normalize_canonical_url(current_url, parser.canonical_url)
            if canonical != current_url and canonical in visited_urls:
                continue
            visited_urls.add(canonical)

            combined_sections = []
            for sec_title, sec_body in parser.sections:
                combined_sections.append(f"[{sec_title}]\n{sec_body}")
            full_text = "\n\n".join(combined_sections).strip()
            if not full_text:
                errors.append({"url": current_url, "error": "Empty or non-textual HTML page"})
                continue

            # 5. Prompt-Injection Sanitization
            sanitized_text, inj_flagged, warnings = PromptInjectionSanitizer.sanitize(full_text)
            if parser.hidden_element_detected:
                inj_flagged = True
                if "hidden_dom_element_stripped" not in warnings:
                    warnings.append("hidden_dom_element_stripped")

            content_hash = hashlib.sha256(sanitized_text.encode("utf-8")).hexdigest()
            if content_hash in seen_hashes:
                # Duplicate content detected across different URLs -> skip duplicate indexing
                continue
            seen_hashes.add(content_hash)

            sanitized_sections: List[Tuple[str, str]] = []
            for sec_title, sec_body in parser.sections:
                clean_sec, _, _ = PromptInjectionSanitizer.sanitize(sec_body)
                if clean_sec:
                    sanitized_sections.append((sec_title, clean_sec))

            results.append(
                CrawledPageResult(
                    url=current_url,
                    canonical_url=canonical,
                    title=parser.title or canonical,
                    content=sanitized_text,
                    content_hash=content_hash,
                    sections=sanitized_sections,
                    tables=parser.tables,
                    prompt_injection_flagged=inj_flagged,
                    sanitized_warnings=warnings,
                    last_checked_at=datetime.now(timezone.utc),
                )
            )

            # Enqueue discovered in-scope links
            for href in parser.links:
                try:
                    next_url = cls.normalize_canonical_url(current_url, href)
                    if (
                        next_url not in visited_urls
                        and cls.is_within_scope(next_url, root_parsed, allowed_scope_prefix, allowed_domains)
                    ):
                        queue.append(next_url)
                except Exception:
                    continue

        return results, errors

    @classmethod
    def _fetch_url_safely(
        cls,
        url: str,
        root_parsed: urllib.parse.ParseResult,
        allowed_scope_prefix: Optional[str],
        allowed_domains: Optional[List[str]],
    ) -> Tuple[str, str]:
        """Fetches URL with manual per-hop redirect inspection to prevent redirect-based SSRF."""
        current = url
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            for _ in range(4):
                SSRFGuard.validate_url(current, resolve_dns=True)
                if not cls.is_within_scope(current, root_parsed, allowed_scope_prefix, allowed_domains):
                    raise ScopeViolationError(f"Redirect target '{current}' is outside approved scope.")

                resp = client.get(current, headers={"User-Agent": cls.USER_AGENT})
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location")
                    if not loc:
                        raise DocumentIngestionError("Redirect response missing Location header.")
                    current = urllib.parse.urljoin(current, loc)
                    continue
                if resp.status_code in (401, 403):
                    raise DocumentIngestionError(f"Access restricted ({resp.status_code}) for {current}")
                if resp.status_code == 429:
                    raise DocumentIngestionError(f"Rate limited (429 Too Many Requests) by {current}")
                resp.raise_for_status()
                return resp.text, current
        raise DocumentIngestionError("Exceeded maximum safe redirect hops (4).")


# ==============================================================================
# 5. Multi-Format Document Parser (PDF, DOCX, CSV, TXT, MD, JSON, HTML)
# ==============================================================================

SUPPORTED_DOCUMENT_EXTENSIONS = {"txt", "md", "csv", "json", "html", "htm", "docx", "pdf", "faq"}


@dataclass
class ParsedChunkUnit:
    page_number: int
    section_title: str
    text: str
    table_data: Optional[List[List[str]]] = None


@dataclass
class ParsedDocumentResult:
    file_name: str
    source_type: str
    title: str
    full_text: str
    content_hash: str
    chunks: List[ParsedChunkUnit]
    prompt_injection_flagged: bool
    sanitized_warnings: List[str]


class MultiFormatDocumentParser:
    """
    Extracts text, section titles, page numbers, and tables from supported enterprise document formats.
    """

    @classmethod
    def parse_document(
        cls,
        file_name: str,
        raw_bytes: Optional[bytes] = None,
        raw_text: Optional[str] = None,
        title: Optional[str] = None,
    ) -> ParsedDocumentResult:
        if not file_name or "." not in file_name:
            ext = "txt"
        else:
            ext = file_name.rsplit(".", 1)[-1].lower().strip()

        if ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
            raise DocumentIngestionError(
                f"Unsupported file format '.{ext}'. Supported formats: {', '.join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))}."
            )

        if raw_bytes is None and (raw_text is None or not raw_text.strip()):
            raise DocumentIngestionError(f"Document '{file_name}' is empty or unreadable.")
        if raw_bytes is not None and len(raw_bytes) == 0 and not raw_text:
            raise DocumentIngestionError(f"Document '{file_name}' contains 0 bytes.")

        doc_title = title or file_name

        if ext in ("txt", "md", "faq"):
            text_val = raw_text if raw_text is not None else cls._decode_bytes(raw_bytes or b"")
            units = cls._parse_text_or_markdown(text_val, doc_title)
        elif ext == "csv":
            text_val = raw_text if raw_text is not None else cls._decode_bytes(raw_bytes or b"")
            units = cls._parse_csv(text_val, doc_title)
        elif ext == "json":
            text_val = raw_text if raw_text is not None else cls._decode_bytes(raw_bytes or b"")
            units = cls._parse_json(text_val, doc_title)
        elif ext in ("html", "htm"):
            text_val = raw_text if raw_text is not None else cls._decode_bytes(raw_bytes or b"")
            units = cls._parse_html(text_val, doc_title)
        elif ext == "docx":
            units = cls._parse_docx(raw_bytes, raw_text, doc_title)
        elif ext == "pdf":
            units = cls._parse_pdf(raw_bytes, raw_text, doc_title)
        else:
            raise DocumentIngestionError(f"Unsupported file extension: .{ext}")

        if not units:
            raise DocumentIngestionError(f"No readable text or tables could be extracted from '{file_name}'.")

        # Sanitize all extracted units against prompt injection
        all_warnings: List[str] = []
        any_flagged = False
        sanitized_units: List[ParsedChunkUnit] = []
        full_text_parts: List[str] = []

        for u in units:
            clean_txt, flagged, warns = PromptInjectionSanitizer.sanitize(u.text)
            if flagged:
                any_flagged = True
                for w in warns:
                    if w not in all_warnings:
                        all_warnings.append(w)
            if clean_txt:
                sanitized_units.append(
                    ParsedChunkUnit(
                        page_number=u.page_number,
                        section_title=u.section_title,
                        text=clean_txt,
                        table_data=u.table_data,
                    )
                )
                full_text_parts.append(clean_txt)

        full_text_combined = "\n\n".join(full_text_parts).strip()
        if not full_text_combined:
            raise DocumentIngestionError(f"Document '{file_name}' contained no valid text after sanitization.")

        content_hash = hashlib.sha256(full_text_combined.encode("utf-8")).hexdigest()
        return ParsedDocumentResult(
            file_name=file_name,
            source_type=ext,
            title=doc_title,
            full_text=full_text_combined,
            content_hash=content_hash,
            chunks=sanitized_units,
            prompt_injection_flagged=any_flagged,
            sanitized_warnings=all_warnings,
        )

    @staticmethod
    def _decode_bytes(data: bytes) -> str:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("utf-16")
            except UnicodeDecodeError as exc:
                raise DocumentIngestionError("File encoding is corrupt or non-textual binary data.") from exc

    @classmethod
    def _parse_text_or_markdown(cls, text: str, default_section: str) -> List[ParsedChunkUnit]:
        clean = text.strip()
        if not clean:
            raise DocumentIngestionError("Text file is empty.")

        sections: List[ParsedChunkUnit] = []
        current_sec = default_section
        buf: List[str] = []

        for line in clean.splitlines():
            s_line = line.strip()
            if s_line.startswith("#"):
                if buf:
                    sections.append(ParsedChunkUnit(page_number=1, section_title=current_sec, text=" ".join(buf)))
                    buf = []
                current_sec = s_line.lstrip("#").strip() or default_section
            elif s_line:
                buf.append(s_line)

        if buf:
            sections.append(ParsedChunkUnit(page_number=1, section_title=current_sec, text=" ".join(buf)))
        return sections

    @classmethod
    def _parse_csv(cls, text: str, doc_title: str) -> List[ParsedChunkUnit]:
        reader = csv.reader(io.StringIO(text.strip()))
        rows = [[cell.strip() for cell in row] for row in reader if any(cell.strip() for cell in row)]
        if not rows:
            raise DocumentIngestionError("CSV file contains no rows.")

        headers = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else rows
        formatted_lines = []
        for idx, r in enumerate(data_rows, start=1):
            pairs = [f"{headers[i] if i < len(headers) else f'Col{i+1}'}: {val}" for i, val in enumerate(r) if val]
            formatted_lines.append(f"Row {idx} — " + " | ".join(pairs))

        summary_text = "\n".join(formatted_lines)
        return [
            ParsedChunkUnit(
                page_number=1,
                section_title=f"{doc_title} (Table)",
                text=summary_text,
                table_data=rows,
            )
        ]

    @classmethod
    def _parse_json(cls, text: str, doc_title: str) -> List[ParsedChunkUnit]:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DocumentIngestionError(f"Invalid JSON document: {exc}") from exc

        flat_text = json.dumps(obj, ensure_ascii=False, indent=2)
        return [ParsedChunkUnit(page_number=1, section_title=doc_title, text=flat_text)]

    @classmethod
    def _parse_html(cls, text: str, doc_title: str) -> List[ParsedChunkUnit]:
        parser = StructuredHTMLParser()
        parser.feed(text)
        parser.finalize()
        units: List[ParsedChunkUnit] = []
        for idx, (sec_title, sec_body) in enumerate(parser.sections):
            units.append(
                ParsedChunkUnit(
                    page_number=1,
                    section_title=sec_title or doc_title,
                    text=sec_body,
                    table_data=parser.tables[0] if (idx == 0 and parser.tables) else None,
                )
            )
        return units

    @classmethod
    def _parse_docx(
        cls, raw_bytes: Optional[bytes], raw_text: Optional[str], doc_title: str
    ) -> List[ParsedChunkUnit]:
        if raw_text and not raw_bytes:
            return cls._parse_text_or_markdown(raw_text, doc_title)
        if not raw_bytes:
            raise DocumentIngestionError("Empty DOCX payload.")

        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                if "word/document.xml" not in zf.namelist():
                    raise DocumentIngestionError("Invalid DOCX archive: missing word/document.xml.")
                xml_bytes = zf.read("word/document.xml")
        except zipfile.BadZipFile as exc:
            raise DocumentIngestionError("Corrupt or unreadable DOCX file (not a valid OpenXML zip archive).") from exc

        root = ET.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        paragraphs: List[str] = []
        for p in root.findall(".//w:p", ns):
            texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
            line = "".join(texts).strip()
            if line:
                paragraphs.append(line)

        tables_extracted: List[List[List[str]]] = []
        for tbl in root.findall(".//w:tbl", ns):
            t_rows: List[List[str]] = []
            for tr in tbl.findall(".//w:tr", ns):
                row_cells: List[str] = []
                for tc in tr.findall(".//w:tc", ns):
                    cell_txt = "".join([t.text for t in tc.findall(".//w:t", ns) if t.text]).strip()
                    row_cells.append(cell_txt)
                if any(row_cells):
                    t_rows.append(row_cells)
                    paragraphs.append(" | ".join(row_cells))
            if t_rows:
                tables_extracted.append(t_rows)

        combined = "\n".join(paragraphs).strip()
        if not combined:
            raise DocumentIngestionError("DOCX file contains no extractable text or tables.")

        return [
            ParsedChunkUnit(
                page_number=1,
                section_title=doc_title,
                text=combined,
                table_data=tables_extracted[0] if tables_extracted else None,
            )
        ]

    @classmethod
    def _parse_pdf(
        cls, raw_bytes: Optional[bytes], raw_text: Optional[str], doc_title: str
    ) -> List[ParsedChunkUnit]:
        if raw_text and not raw_bytes:
            return cls._parse_text_or_markdown(raw_text, doc_title)
        if not raw_bytes or not raw_bytes.startswith(b"%PDF"):
            raise DocumentIngestionError("Unreadable or invalid PDF file: missing %PDF header.")

        # Extract text per page from PDF streams (supports uncompressed & FlateDecode streams)
        page_texts: List[str] = []
        stream_pattern = re.compile(rb"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)

        for match in stream_pattern.finditer(raw_bytes):
            raw_stream = match.group(1)
            decoded_stream = raw_stream
            try:
                decoded_stream = zlib.decompress(raw_stream)
            except Exception:
                pass

            # Extract PDF literal strings inside (...) Tj or [...] TJ blocks
            literals = re.findall(rb"\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*Tj", decoded_stream)
            tj_arrays = re.findall(rb"\[(.*?)\]\s*TJ", decoded_stream, re.DOTALL)
            for arr in tj_arrays:
                literals.extend(re.findall(rb"\(([^()\\]*(?:\\.[^()\\]*)*)\)", arr))

            if literals:
                page_str = " ".join(
                    lit.decode("utf-8", errors="ignore").replace(r"\(", "(").replace(r"\)", ")")
                    for lit in literals
                ).strip()
                if page_str:
                    page_texts.append(page_str)

        if not page_texts:
            # Check if this is a scanned image-only PDF
            if b"/Subtype /Image" in raw_bytes or b"/Image" in raw_bytes or b"/Page" in raw_bytes:
                raise DocumentIngestionError(
                    "OCR_REQUIRED: Scanned/image-only PDF detected with no extractable text layer. Please enable OCR or upload a text-searchable PDF/DOCX."
                )
            raise DocumentIngestionError("Unreadable PDF: no text streams found.")

        units: List[ParsedChunkUnit] = []
        for idx, p_text in enumerate(page_texts, start=1):
            units.append(
                ParsedChunkUnit(
                    page_number=idx,
                    section_title=f"{doc_title} - Page {idx}",
                    text=p_text,
                )
            )
        return units
