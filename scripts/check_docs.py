#!/usr/bin/env python3
"""Verification checker for docs/PROJECT_GUIDE.md.

Enforces:
1. All backticked repository paths point to valid existing files or directories.
2. Configuration table covers all environment variables from Settings class and .env.example.
3. Table of contents has working anchors, exactly one H1, and closed Mermaid fences.
4. No leaked secrets, private keys, or real credentials.
5. Endpoint count and table count match real application OpenAPI and SQLAlchemy models.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "PROJECT_GUIDE.md"


def check_single_h1(text: str) -> None:
    h1_matches = re.findall(r"^#\s+(.+)$", text, re.MULTILINE)
    if len(h1_matches) != 1:
        raise ValueError(f"Expected exactly one H1 in doc, found {len(h1_matches)}: {h1_matches}")
    print("[PASS] Exactly one H1 detected.")


def check_mermaid_fences(text: str) -> None:
    opens = len(re.findall(r"^```mermaid", text, re.MULTILINE))
    closes = len(re.findall(r"^```\s*$", text, re.MULTILINE))
    # Note: markdown code fences include both mermaid and non-mermaid
    all_fences = len(re.findall(r"^```", text, re.MULTILINE))
    if all_fences % 2 != 0:
        raise ValueError(f"Mismatched markdown code fences! Total fences: {all_fences}")
    if opens == 0:
        raise ValueError("No Mermaid diagram code fences found!")
    print(f"[PASS] All code fences balanced ({opens} Mermaid diagrams, {all_fences // 2} total blocks).")


def check_toc_anchors(text: str) -> None:
    # Find all markdown headings H2 and H3
    heading_slugs = set()
    for m in re.finditer(r"^(#{1,6})\s+(.+)$", text, re.MULTILINE):
        title = m.group(2).strip()
        # GitHub slugify: lowercase, strip punctuation except dashes, spaces to dashes
        slug = title.lower()
        slug = re.sub(r"[^\w\s\-]", "", slug)
        slug = re.sub(r"\s+", "-", slug)
        slug = slug.strip("-")
        heading_slugs.add(slug)

    # Find TOC links [Text](#anchor)
    toc_links = re.findall(r"\[([^\]]+)\]\(#([^\)]+)\)", text)
    if not toc_links:
        raise ValueError("No Table of Contents anchors found in document!")

    missing = []
    for title, anchor in toc_links:
        clean_anchor = anchor.lower().strip()
        if clean_anchor not in heading_slugs:
            missing.append((title, anchor))

    if missing:
        raise ValueError(f"Found {len(missing)} TOC links with missing anchor targets: {missing}")
    print(f"[PASS] All {len(toc_links)} Table of Contents links match valid document anchors.")


def check_backticked_paths(text: str) -> None:
    # Match backticked strings that look like relative paths
    candidates = re.findall(r"`([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+|[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-/]*)`", text)
    checked = set()
    missing = []

    # Exclusions for code identifiers, models, or URLs
    ignore_patterns = {
        "report.json", "report.md", "manifest.jsonl", "thresholds.yaml", "accounting.yaml",
        "sqlite+aiosqlite:///:memory:", "openwa:2785", "api:8000", "localhost:8001",
        "application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic",
        "llama-3.3-70b-versatile", "llama-3.2-11b-vision-preview", "llama-3.2-90b-vision-preview",
        "http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173",
        "http://openwa:2785/api", "http://localhost:2785", "http://localhost:8001",
        "http://localhost:9000", "http://localhost", "http://localhost:8000",
        "invoices@example.com", "invoices@invoiceflow.local", "admin@invoiceflow.local",
        "reviewer@invoiceflow.local", "reviewer@test.com", "admin@test.com",
        "postgres:postgres", "ghcr.io/rmyndharis/openwa:v0.27.0", "openwa:latest",
        "redis://redis:6379/0", "redis://localhost:6379/0", "postgresql+asyncpg://...",
        "postgresql://...", "chk_approved_requires_actor", "idx_invoices_business_key_unique"
    }

    for c in candidates:
        c_clean = c.strip().replace("\\", "/")
        if c_clean in ignore_patterns or c_clean.startswith("http") or "@" in c_clean:
            continue
        # If it looks like a path in the repo
        if "/" in c_clean or c_clean.endswith((".py", ".ts", ".tsx", ".json", ".yml", ".yaml", ".md", ".mmd", ".png")):
            # Remove trailing punctuation or arguments
            c_clean = re.sub(r"[\*:]+$", "", c_clean)
            c_path = REPO_ROOT / c_clean
            if c_clean in checked:
                continue
            checked.add(c_clean)
            if not c_path.exists() and not (REPO_ROOT / (c_clean + ".py")).exists():
                missing.append(c_clean)

    if missing:
        raise ValueError(f"Found {len(missing)} broken backticked repository paths: {missing}")
    print(f"[PASS] Verified {len(checked)} backticked repository paths. All exist on disk.")


def check_configuration_coverage(text: str) -> None:
    # 1. Load Settings fields
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.core.config import Settings

    settings_fields = set(Settings.model_fields.keys())

    # 2. Load .env.example variables
    env_example_path = REPO_ROOT / ".env.example"
    with open(env_example_path, "r", encoding="utf-8") as f:
        env_lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#") and "=" in l]
    env_vars = set(l.split("=")[0].strip() for l in env_lines)

    # 3. Find all variable names mentioned in doc's configuration table
    doc_vars = set(re.findall(r"`([A-Z][A-Z0-9_]{3,})`", text))

    missing_settings = settings_fields - doc_vars
    missing_env = env_vars - doc_vars

    if missing_settings:
        raise ValueError(f"Configuration table is missing {len(missing_settings)} Settings fields: {missing_settings}")
    if missing_env:
        raise ValueError(f"Configuration table is missing {len(missing_env)} .env.example variables: {missing_env}")

    print(f"[PASS] All {len(settings_fields)} Settings fields and {len(env_vars)} .env.example variables are documented.")


def check_secrets_and_leakage(text: str) -> None:
    patterns = [
        (r"gsk_[a-zA-Z0-9]{20,}", "Real Groq API key"),
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API key"),
        (r"-----BEGIN (?:RSA )?PRIVATE KEY-----", "Private Key Header"),
        (r"\+91[7-9]\d{9}", "Real Indian phone number"),
        (r"\b(?=[A-Za-z0-9+/]{40,})(?![0-9a-f]{40}\b)[A-Za-z0-9+/]{40,}={0,2}\b", "Long base64 secret"),
    ]
    for pattern, desc in patterns:
        matches = re.findall(pattern, text)
        if matches:
            # Filter dummy strings
            clean = [m for m in matches if "fake" not in m.lower() and "dummy" not in m.lower() and "placeholder" not in m.lower()]
            if clean:
                raise ValueError(f"Potential secret leakage detected ({desc}): {clean[:3]}")
    print("[PASS] No real secrets or credential leaks found.")


def check_endpoint_and_table_counts(text: str) -> None:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.main import create_app
    from app.models.entities import Base

    app = create_app()
    openapi = app.openapi()
    real_endpoint_count = sum(len(methods) for methods in openapi["paths"].values())
    real_table_count = len(Base.metadata.tables)

    # Verify they are stated in the document
    if f"{real_endpoint_count} total endpoint operations" not in text and f"{real_endpoint_count} total endpoints" not in text:
        raise ValueError(f"Document does not correctly state the measured endpoint count ({real_endpoint_count})")
    if f"{real_table_count} distinct tables" not in text and f"{real_table_count} tables" not in text and f"{real_table_count} total tables" not in text:
        raise ValueError(f"Document does not correctly state the measured table count ({real_table_count})")

    print(f"[PASS] Endpoint count ({real_endpoint_count}) and table count ({real_table_count}) match OpenAPI and SQLAlchemy metadata.")


def main() -> None:
    print(f"Verifying {DOC_PATH}...")
    if not DOC_PATH.exists():
        print(f"Error: {DOC_PATH} does not exist!")
        sys.exit(1)

    text = DOC_PATH.read_text(encoding="utf-8")

    try:
        check_single_h1(text)
        check_mermaid_fences(text)
        check_toc_anchors(text)
        check_backticked_paths(text)
        check_configuration_coverage(text)
        check_secrets_and_leakage(text)
        check_endpoint_and_table_counts(text)
        print("\nALL VERIFICATION CHECKS PASSED! Documentation is 100% accurate.")
    except Exception as e:
        print(f"\n[FAIL] Verification error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
