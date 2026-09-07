# Technical Specification — Legal Metrology (Packaged Commodities) Compliance Checking System

**Version:** 1.0 (build-ready draft)
**Prepared:** September 2026
**Companion document:** `legal-metrology-compliance-system-engineering-plan.md` (strategy/phasing — this document is the implementation-level spec)

> **Legal disclaimer for the build team:** All rule thresholds, table values, and clause references below are compiled from public secondary sources (Bare Act text, government FAQs, legal commentary) for engineering planning purposes. Before any rule is hardcoded or shipped as a compliance check, the exact clause text and current numeric values **must be verified against the notified Legal Metrology (Packaged Commodities) Rules, 2011 and all amendments** (2017, 2021, 2022, 2023, 2025) by a legal reviewer, and re-verified whenever a new amendment is gazetted. Anywhere a value below is uncertain, it is marked `[VERIFY]`.

---

## Table of Contents

1. System Overview & Goals
2. Functional Requirements (numbered, testable)
3. Non-Functional Requirements
4. Regulatory Rule Specification (the domain model)
5. System Architecture
6. Database Schema (complete DDL-level detail)
7. API Specification
8. Module Specifications
   - 8.1 Image Capture & Upload
   - 8.2 Vision/OCR Pipeline
   - 8.3 Declaration Extraction & Field Classification
   - 8.4 Rule Engine
   - 8.5 Compliance Verdict & Report Generation
   - 8.6 Repository & Search
   - 8.7 Dashboard & Analytics
   - 8.8 Auth & RBAC
9. Frontend Specification (web)
10. Mobile App Specification
11. Synchronization Design (rules DB, offline mobile, external product data)
12. Infrastructure & Deployment
13. Security Specification
14. Testing Strategy & Acceptance Criteria
15. Repository / Project Structure
16. Sprint-Level Delivery Plan
17. Glossary

---

## 1. System Overview & Goals

**Purpose:** Automate first-pass detection of Legal Metrology (Packaged Commodities) Rules, 2011 (LMPC) violations on packaged commodity labels and e-commerce listings, producing officer-reviewable, exportable compliance reports, backed by a searchable inspection repository and enforcement dashboards.

**Primary users:**
- Field Officer — captures scans (mobile, sometimes offline), submits for review.
- Reviewing Officer — verifies/overrides system verdicts, finalizes reports.
- Admin — manages users, rule versions, product categories, jurisdictions.
- Auditor (read-only) — views reports/history for audits.

**Success criteria (v1):**
- A field officer can photograph a package and receive a structured, evidence-backed compliance verdict within a target of &lt; 30 seconds (async, non-blocking) for the presence/format checks, and font-size checks when a scale reference is supplied.
- Every verdict traces to a specific rule clause and an extracted evidence region — no unexplained pass/fail.
- Every finalized report is exportable as PDF and DOCX and retrievable via search within 2 seconds for a typical query.
- False "violation" verdicts on genuinely compliant labels are minimized by defaulting low-confidence extractions to `NEEDS_MANUAL_REVIEW` rather than `FAIL`.

---

## 2. Functional Requirements

Numbered so each can become a ticket/acceptance test.

**FR-1 — Image Capture**
- FR-1.1 Web app: drag-and-drop or file-picker upload of 1–6 images per scan (front/PDP, back, sides).
- FR-1.2 Mobile app: in-app camera capture with guided framing overlay per package face.
- FR-1.3 System accepts JPEG/PNG/HEIC, max 20MB per image, auto-converts HEIC to JPEG server-side.
- FR-1.4 User may supply a scale reference: (a) manual package dimensions (L×W×H in cm), or (b) an in-frame reference marker/card, or (c) skip (system marks font-size checks `NOT_APPLICABLE — no scale reference`).
- FR-1.5 E-commerce mode: user supplies a listing URL; system fetches page, screenshots product image gallery, extracts visible declaration text from page DOM in addition to image OCR.

**FR-2 — OCR & Extraction**
- FR-2.1 System detects the package boundary and estimates which face is the Principal Display Panel (PDP) per Rule 7 area rules (rectangular = one face; cylindrical = 40% of surface area; irregular = 40% of total surface area).
- FR-2.2 System detects all text regions and OCRs them with per-region confidence scores.
- FR-2.3 System supports English + at least Hindi OCR at launch; architecture must allow adding further Indic scripts without redesign.
- FR-2.4 System classifies each OCR'd text block into one of the defined declaration field types (§4.2) or `unclassified`.
- FR-2.5 When a scale reference is present, system converts detected glyph bounding-box height from pixels to millimetres.

**FR-3 — Rule Evaluation**
- FR-3.1 System evaluates every applicable rule from the active rule-set against the extracted fields and returns, per rule: `PASS | FAIL | NOT_APPLICABLE | NEEDS_MANUAL_REVIEW`.
- FR-3.2 System applies category-specific exemptions (bulk packages, medical devices, food-FSSAI overlap, etc.) before evaluating a rule.
- FR-3.3 System applies the e-commerce-specific rule subset (Rule 6(10) — all mandatory declarations except month/year of packing) when scan mode = e-commerce.
- FR-3.4 Every rule evaluation stores the evidence used (bounding box, extracted value, computed measurement, rule clause id, rule version id).

**FR-4 — Review & Override**
- FR-4.1 Reviewing officer can view all evaluations for a scan with evidence overlaid on the image.
- FR-4.2 Reviewing officer can override any individual rule verdict, and must supply a free-text reason for the override.
- FR-4.3 Overrides are stored as new immutable records, not edits to the original — verdict history is fully reconstructable.
- FR-4.4 Reviewing officer finalizes the report, locking it (further changes require a new report version).

**FR-5 — Reporting**
- FR-5.1 System generates a PDF compliance report containing: product identification, scan metadata, per-rule verdict table with clause citations, evidence images with highlighted regions, officer notes, and reviewer sign-off.
- FR-5.2 System generates an editable DOCX version with identical content.
- FR-5.3 Reports are versioned; re-finalizing produces report v2, v3, etc., all retained.

**FR-6 — Repository & Search**
- FR-6.1 All scans and reports are stored against a `Product` entity, deduplicated by (manufacturer + brand + barcode) where available.
- FR-6.2 Users can search by manufacturer, brand, category, date range, violation type, officer, jurisdiction, and free text.
- FR-6.3 Search results are paginated and exportable as CSV.

**FR-7 — Dashboards**
- FR-7.1 Field officer dashboard: their pending/draft/synced scans.
- FR-7.2 Admin/reviewing officer dashboard: violation-rate trend, top violation types, top non-compliant manufacturers/categories, inspection throughput, geographic breakdown (if geotagged).
- FR-7.3 Dashboards support date-range and jurisdiction filters.

**FR-8 — Auth & Access Control**
- FR-8.1 Role-based access (Field Officer, Reviewing Officer, Admin, Auditor) enforced at the API layer, not just UI.
- FR-8.2 Jurisdiction-scoped visibility: officers see only scans within their assigned region unless granted broader access.
- FR-8.3 All authentication events and permission-denied events are logged.

**FR-9 — Rule Management (Admin)**
- FR-9.1 Admin can view all rule versions, their effective date ranges, and diff between versions.
- FR-9.2 Admin can create a new draft rule version and publish it with an effective date.
- FR-9.3 Publishing a new rule version does not alter already-finalized reports.

**FR-10 — Offline Mobile**
- FR-10.1 Mobile app queues scans created without connectivity and syncs automatically on reconnect.
- FR-10.2 Sync status (draft/queued/syncing/synced/conflict) is visible per scan.

---

## 3. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Performance | Scan submission acknowledged &lt; 2s; full OCR+rule pipeline result available &lt; 30s (async, p95) for a 6-image scan |
| Scalability | Horizontally scalable OCR/rule workers behind a job queue; target 10,000 scans/day at pilot scale, design not to hit a hard ceiling below 100,000/day |
| Availability | 99.5% for web/API during business hours (pilot); mobile app fully functional offline for capture |
| Explainability | Every verdict must reference a specific rule clause id and evidence; no unexplained ML-only verdicts reach a finalized report |
| Auditability | Append-only history on `RuleEvaluation`, `ComplianceReport` versions, and `AuditLog`; nothing legally relevant is hard-deleted |
| Data residency | Deployable on-prem or on an empanelled/government-approved cloud; no hard dependency on a single foreign cloud provider's proprietary services |
| Localization | UI and OCR must support English + Hindi at minimum; field labels/report templates translatable |
| Accessibility | Web dashboard meets WCAG 2.1 AA for core officer workflows |
| Security | Encryption at rest (DB, object storage) and in transit (TLS 1.2+); RBAC enforced server-side; see §13 |

---

## 4. Regulatory Rule Specification (Domain Model)

This section is the bridge between law and code — every field and check below becomes a row in `RuleDefinition` (§6) or a field-type in the extraction schema.

### 4.1 Declaration fields (derived from Rule 6) `[VERIFY against current Bare Act + 2023/2025 amendments]`

| Field code | Description | Format notes | Applies to |
|---|---|---|---|
| `manufacturer_block` | Name & address of manufacturer/packer/importer | Free text block; must include a complete postal address | All (food exception per Explanation III interacts with FSSAI) |
| `country_of_origin` | Country of origin | Format: "Made in &lt;Country&gt;" or "Country of Origin: &lt;Country&gt;" | Imported goods only |
| `generic_name` | Common/generic name of commodity | Free text | All |
| `net_quantity` | Net quantity by weight/volume/number | Numeral + SI unit; unit depends on category (g/kg, ml/l, N/U for count) | All |
| `mfg_date` | Month & year of manufacture/packing/import | MM/YYYY or month name + year; may be word or numeral form | Physical packages (exempt from e-commerce per Rule 6(10)) |
| `mrp` | Maximum Retail Price, inclusive of all taxes | Currency symbol/prefix "MRP Rs." + numeral + suffix "(inclusive of all taxes)" | All |
| `unit_sale_price` | Price per standard unit | "Rs._ per g" or "Rs._ per kg" (analogous for volume) — mandatory format effective 1 Apr 2022 `[VERIFY]` | Non-exempt packages; exempt if net qty ≤ 10g/10ml (Rule 26) |
| `consumer_care` | Consumer care name, address, phone/email | Phone and/or email required; address may reference manufacturer block per FAQ Q.48 `[VERIFY]` | All |
| `dimensions` | Length/area dimensions where relevant (textiles, cable, sheets) | Metric units | Category-specific |

### 4.2 Field classification taxonomy (used by the extraction/NLP module)

Each OCR'd text block is classified into exactly one of: `manufacturer_block`, `country_of_origin`, `generic_name`, `net_quantity`, `mfg_date`, `mrp`, `unit_sale_price`, `consumer_care`, `dimensions`, `brand_name` (non-mandatory but useful for dedup), `other_marketing_text`, `unclassified`.

### 4.3 Principal Display Panel (PDP) area calculation `[VERIFY exact formula wording]`

```
IF package_shape == RECTANGULAR:
    PDP_area_cm2 = height_cm * width_cm   # of the single largest face
ELIF package_shape == CYLINDRICAL_OR_PIPE:
    PDP_area_cm2 = 0.40 * total_surface_area_cm2
ELSE:  # irregular
    PDP_area_cm2 = 0.40 * total_surface_area_cm2

# Exclusions: top, bottom, flange at top/bottom of cans, and shoulder/neck of bottles/jars
# are excluded from the surface-area calculation.
```
`package_shape` is either user-selected at scan time (dropdown: rectangular / cylindrical / irregular) or inferred from a shape-detection pass on the image; user selection should be allowed to override the inferred value.

### 4.4 Font/numeral size thresholds (Rule 7, Tables I & II) `[VERIFY exact breakpoints and current values — 2017 amendment revised these; commonly-cited implementation bands shown below for structure only]`

Illustrative structure (values must be confirmed against the notified table text before use):

| PDP area band | Minimum numeral height (MRP / net qty numerals) | Minimum letter height (general declarations) |
|---|---|---|
| Small (e.g., ≤ 100 cm²) | ~2 mm `[VERIFY]` | 1 mm (general minimum per 2017 amendment) `[VERIFY]` |
| Medium (e.g., 100–500 cm²) | ~4 mm `[VERIFY]` | 1 mm |
| Large (e.g., &gt; 500 cm²) | ~6 mm `[VERIFY]` | 1 mm |

Additional rules to encode regardless of exact numbers:
- Width-to-height ratio of any letter/numeral ≥ 1/3, except numeral "1" and letters "i", "I", "l" (Rule 7(3)).
- Blown/molded/embossed/perforated lettering: minimum height 2 mm (vs 1 mm for printed) `[VERIFY]`.
- Isolation zone around the quantity declaration: clear space above/below ≥ 1× numeral height, and left/right ≥ 2× numeral height, free of other printed matter.
- The numeral-size requirement applies to the MRP **value** only, not to prefix "MRP Rs." or suffix "(inclusive of all taxes)" — per official FAQ.
- Small packages (capacity ≤ 5 cm³): PDP may be a card/tape affixed to the package instead of printed on the package itself; packages with area &gt; 10 cm³ must follow Table I `[VERIFY exact cm³ vs cm² wording — likely a typo in source material, confirm against Bare Act]`.

### 4.5 Category exemptions & special regimes `[VERIFY current list — amended periodically]`

| Category / condition | Treatment |
|---|---|
| Packages &gt; 25 kg or &gt; 25 L | Exempt from Chapter II declaration requirements |
| Cement, fertilizer, agricultural produce in bags &gt; 50 kg | Exempt |
| Medical devices (post-2025 amendment) | Governed by Medical Devices Rules, 2017 (CDSCO) instead of LMPC font/placement rules; Rule 33 relaxation does not apply where Medical Devices Rules apply |
| Food articles | MRP, net weight, consumer care details follow LMPC; other declarations follow FSSAI/Prevention of Food Adulteration regime |
| E-commerce listings (Rule 6(10)) | All mandatory declarations required except month/year of manufacture/packing |
| Net quantity ≤ 10 g / 10 ml | Exempt from unit sale price declaration (Rule 26) |
| Garments/hosiery sold loose (post-2023 amendment) | Must show internationally recognized size indicators (S/M/L/XL/XXL/XXXL) plus metric size in cm/m |

### 4.6 Rule specification schema (machine-readable)

```yaml
rule_id: string                # e.g. LMPC-R6-MRP-PRESENCE
clause: string                 # e.g. "Rule 6(1)(f)"
title: string
description: string
applies_to: [physical_package, ecommerce_listing]
category_exemptions: [string]  # category codes this rule does NOT apply to
check_type: enum               # presence | format_regex | numeric_threshold | numeric_threshold_lookup | cross_field_consistency
field: string                  # field code from §4.2
params:                        # check-type-specific parameters
  regex: string                # for format_regex
  lookup_table_ref: string     # for numeric_threshold_lookup (references §4.4 table by version)
  input_key: string            # e.g. pdp_area_cm2
  min_ratio: number            # e.g. width/height >= 0.333
effective_from: date
effective_to: date|null
version: integer
source_notification: string    # gazette notification reference
created_by: user_id
approved_by: user_id
```

---

## 5. System Architecture

### 5.1 Component list

| Component | Responsibility | Tech |
|---|---|---|
| Web App | Officer/admin UI | Next.js + TypeScript + Tailwind |
| Mobile App | Field capture, offline queueing | React Native + local SQLite/WatermelonDB |
| API Gateway | AuthN/Z, routing, rate limiting | FastAPI (or Nginx/Kong in front of FastAPI services) |
| Scan Orchestration Service | Accepts scan submissions, enqueues jobs, tracks status | FastAPI + Celery/Redis |
| Vision/OCR Worker | Detection, OCR, scale calibration | Python (PaddleOCR/Tesseract, OpenCV, a detector model) |
| Extraction/NLP Worker | Field classification & normalization | Python (regex + rule-based parsers, optional transformer NER) |
| Rule Engine Service | Evaluates rule-set against extracted fields | Python, rules loaded from `RuleDefinition` table |
| Report Generation Service | Renders PDF/DOCX from verdict object | Python (WeasyPrint/ReportLab, python-docx) |
| Repository/Search Service | Product/scan history, search | PostgreSQL (+ `pg_trgm`; Elasticsearch/OpenSearch if scale requires) |
| Dashboard/Analytics Service | Aggregation queries, chart data endpoints | FastAPI + materialized views or a small OLAP layer |
| Regulatory Watch Service | Crawls for LMPC notifications, drafts rule changes | Python scheduled job (cron/Celery beat) |
| Auth Service | User/role/session management | FastAPI + JWT, Postgres-backed; pluggable SSO |
| Object Storage | Images, generated reports | S3-compatible (AWS S3 or MinIO) |
| Primary DB | Structured data | PostgreSQL |
| Job Queue / Cache | Async processing, caching | Redis |

### 5.2 Request flow — a single scan (happy path)

```
1. Client (web/mobile) → POST /scans  (multipart images + metadata)
2. Scan Orchestration Service:
     - validates payload, creates Scan row (status=RECEIVED)
     - uploads images to object storage
     - enqueues job: {scan_id} → OCR queue
     - returns 202 Accepted {scan_id, status_url}
3. Vision/OCR Worker (async):
     - fetches images from object storage
     - runs PDP detection + area estimation
     - runs text detection + OCR → raw text blocks with bbox + confidence
     - if scale reference present: computes glyph height in mm
     - writes results, updates Scan status=OCR_COMPLETE
     - enqueues job → Extraction queue
4. Extraction/NLP Worker (async):
     - classifies each text block into a field type
     - normalizes values (dates, currency, units)
     - writes ExtractedDeclaration rows
     - updates Scan status=EXTRACTION_COMPLETE
     - enqueues job → Rule Engine queue
5. Rule Engine Service (async):
     - loads active RuleDefinition set for scan's effective date + category
     - evaluates each rule against ExtractedDeclaration rows
     - writes RuleEvaluation rows (PASS/FAIL/NOT_APPLICABLE/NEEDS_MANUAL_REVIEW + evidence)
     - updates Scan status=EVALUATION_COMPLETE
6. Client polls GET /scans/{id} or receives a websocket/push notification
     - reviewing officer opens scan, sees evidence overlay + verdicts
7. Reviewing officer confirms/overrides → POST /scans/{id}/report
     - Report Generation Service renders PDF+DOCX, stores to object storage
     - Scan status=FINALIZED
```

### 5.3 Data flow diagram (textual)

```
[Camera/Upload] -> [Object Storage: raw images]
                 -> [OCR Worker] -> [ExtractedDeclaration rows in Postgres]
                                  -> [Rule Engine] -> [RuleEvaluation rows]
                                                    -> [ComplianceReport row + PDF/DOCX in Object Storage]
[RuleDefinition table] <-> [Regulatory Watch Service] (draft proposals, admin-approved)
[Product/Scan repository] <-> [Search index] <-> [Dashboard aggregation queries]
```

---

## 6. Database Schema (PostgreSQL — full detail)

```sql
-- ===== Users & Access =====
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    role VARCHAR(30) NOT NULL CHECK (role IN ('FIELD_OFFICER','REVIEWING_OFFICER','ADMIN','AUDITOR')),
    jurisdiction_id UUID REFERENCES jurisdictions(id),
    department VARCHAR(150),
    password_hash TEXT,               -- null if SSO-only
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE jurisdictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL,        -- e.g. "Lucknow District"
    state VARCHAR(100) NOT NULL,
    parent_jurisdiction_id UUID REFERENCES jurisdictions(id)
);

-- ===== Product / Manufacturer =====
CREATE TABLE manufacturers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    registered_address TEXT,
    extracted_from_scan_id UUID,       -- first scan this manufacturer record was derived from, if not from an external registry
    external_registry_ref VARCHAR(100),-- e.g. GS1 company prefix, if matched
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_name VARCHAR(255),
    manufacturer_id UUID REFERENCES manufacturers(id),
    category_code VARCHAR(50) NOT NULL REFERENCES commodity_categories(code),
    barcode VARCHAR(50),
    declared_net_quantity VARCHAR(50),
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    dedup_key VARCHAR(500) GENERATED ALWAYS AS (
        lower(coalesce(brand_name,'') || '|' || coalesce(manufacturer_id::text,'') || '|' || coalesce(barcode,''))
    ) STORED,
    UNIQUE (dedup_key)
);

CREATE TABLE commodity_categories (
    code VARCHAR(50) PRIMARY KEY,      -- e.g. 'FOOD', 'COSMETIC', 'CEMENT', 'TEXTILE', 'MEDICAL_DEVICE', 'GENERIC'
    name VARCHAR(150) NOT NULL,
    fssai_overlap BOOLEAN DEFAULT FALSE,
    default_exemptions JSONB           -- list of exemption codes applicable by default
);

-- ===== Scans =====
CREATE TABLE scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES products(id),   -- nullable until linked/deduped
    officer_id UUID NOT NULL REFERENCES users(id),
    jurisdiction_id UUID REFERENCES jurisdictions(id),
    mode VARCHAR(20) NOT NULL CHECK (mode IN ('PHYSICAL_PACKAGE','ECOMMERCE_LISTING')),
    ecommerce_url TEXT,
    package_shape VARCHAR(20) CHECK (package_shape IN ('RECTANGULAR','CYLINDRICAL','IRREGULAR')),
    scale_reference_type VARCHAR(20) CHECK (scale_reference_type IN ('MANUAL_DIMENSIONS','MARKER','BARCODE_LOOKUP','NONE')),
    scale_reference_data JSONB,        -- e.g. {"length_cm":10,"width_cm":7.5,"height_cm":15}
    pdp_area_cm2 NUMERIC(10,2),
    status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED'
        CHECK (status IN ('RECEIVED','OCR_IN_PROGRESS','OCR_COMPLETE','EXTRACTION_COMPLETE',
                           'EVALUATION_COMPLETE','UNDER_REVIEW','FINALIZED','SYNC_CONFLICT')),
    client_uuid UUID UNIQUE,           -- idempotency key from mobile client, offline-created
    captured_at TIMESTAMPTZ,           -- when photo(s) actually taken (may predate sync)
    synced_at TIMESTAMPTZ,
    geo_lat NUMERIC(9,6),
    geo_lng NUMERIC(9,6),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE scan_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    panel_label VARCHAR(20),           -- 'FRONT_PDP','BACK','SIDE','TOP','BOTTOM'
    storage_key TEXT NOT NULL,         -- object storage path
    upload_status VARCHAR(20) DEFAULT 'PENDING' CHECK (upload_status IN ('PENDING','UPLOADING','UPLOADED','FAILED')),
    width_px INT, height_px INT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===== Extraction =====
CREATE TABLE extracted_declarations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    scan_image_id UUID REFERENCES scan_images(id),
    field_type VARCHAR(40) NOT NULL,   -- see §4.2 taxonomy
    raw_text TEXT,
    normalized_value JSONB,            -- e.g. {"amount": 199.00, "currency":"INR"} for mrp
    bbox_x INT, bbox_y INT, bbox_w INT, bbox_h INT,
    ocr_confidence NUMERIC(4,3),       -- 0.000–1.000
    classification_confidence NUMERIC(4,3),
    glyph_height_px NUMERIC(8,2),
    glyph_height_mm NUMERIC(6,2),      -- null if no scale reference
    is_on_pdp BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_extracted_scan ON extracted_declarations(scan_id);

-- ===== Rules =====
CREATE TABLE rule_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_code VARCHAR(60) NOT NULL,    -- e.g. LMPC-R6-MRP-PRESENCE (stable across versions)
    version INT NOT NULL,
    clause VARCHAR(100),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    applies_to VARCHAR(20)[] NOT NULL, -- {'PHYSICAL_PACKAGE','ECOMMERCE_LISTING'}
    category_exemptions VARCHAR(50)[] DEFAULT '{}',
    check_type VARCHAR(30) NOT NULL CHECK (check_type IN
        ('presence','format_regex','numeric_threshold','numeric_threshold_lookup','cross_field_consistency')),
    field VARCHAR(40),
    params JSONB NOT NULL DEFAULT '{}',
    effective_from DATE NOT NULL,
    effective_to DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','SUPERSEDED')),
    source_notification VARCHAR(255),
    created_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (rule_code, version)
);

CREATE TABLE rule_change_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_code VARCHAR(60) NOT NULL,
    old_version INT,
    new_version INT NOT NULL,
    diff_summary TEXT,
    changed_by UUID REFERENCES users(id),
    changed_at TIMESTAMPTZ DEFAULT now()
);

-- ===== Evaluation =====
CREATE TABLE rule_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    rule_definition_id UUID NOT NULL REFERENCES rule_definitions(id),
    outcome VARCHAR(25) NOT NULL CHECK (outcome IN ('PASS','FAIL','NOT_APPLICABLE','NEEDS_MANUAL_REVIEW')),
    evidence_declaration_id UUID REFERENCES extracted_declarations(id),
    evidence_detail JSONB,             -- computed values, thresholds compared, etc.
    evaluated_at TIMESTAMPTZ DEFAULT now(),
    is_override BOOLEAN DEFAULT FALSE,
    override_of_evaluation_id UUID REFERENCES rule_evaluations(id),
    override_reason TEXT,
    overridden_by UUID REFERENCES users(id)
);
CREATE INDEX idx_evaluations_scan ON rule_evaluations(scan_id);

-- ===== Reports =====
CREATE TABLE compliance_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id),
    version INT NOT NULL,
    overall_status VARCHAR(20) NOT NULL CHECK (overall_status IN ('COMPLIANT','NON_COMPLIANT','PARTIAL_REVIEW_NEEDED')),
    pdf_storage_key TEXT,
    docx_storage_key TEXT,
    reviewed_by UUID REFERENCES users(id),
    review_notes TEXT,
    finalized_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (scan_id, version)
);

-- ===== Audit =====
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    actor_id UUID REFERENCES users(id),
    action VARCHAR(50) NOT NULL,       -- CREATE, UPDATE, OVERRIDE, FINALIZE, LOGIN, PERMISSION_DENIED
    diff JSONB,
    occurred_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);

-- ===== External product data cache =====
CREATE TABLE external_product_cache (
    barcode VARCHAR(50) PRIMARY KEY,
    source VARCHAR(50) NOT NULL,       -- e.g. 'GS1_INDIA'
    payload JSONB NOT NULL,
    last_synced_at TIMESTAMPTZ DEFAULT now(),
    ttl_expires_at TIMESTAMPTZ
);

-- ===== Search support =====
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_manufacturers_name_trgm ON manufacturers USING gin (name gin_trgm_ops);
CREATE INDEX idx_products_brand_trgm ON products USING gin (brand_name gin_trgm_ops);
```

---

## 7. API Specification

Base path: `/api/v1`. All authenticated endpoints require `Authorization: Bearer <JWT>`. Responses are JSON unless noted.

### 7.1 Auth
| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | `{email, password}` → `{access_token, refresh_token, user}` |
| POST | `/auth/refresh` | `{refresh_token}` → new `access_token` |
| POST | `/auth/logout` | Invalidates refresh token |
| GET | `/auth/me` | Current user profile + role + jurisdiction |

### 7.2 Scans
| Method | Path | Description |
|---|---|---|
| POST | `/scans` | Create a scan. Multipart: `images[]`, `mode`, `package_shape`, `scale_reference`, `client_uuid` (for offline idempotency), `ecommerce_url` (if applicable). Returns `202 {scan_id, status}` |
| GET | `/scans/{id}` | Full scan detail: images, extracted declarations, rule evaluations, current status |
| GET | `/scans` | List/search scans. Query params: `manufacturer`, `brand`, `category`, `status`, `date_from`, `date_to`, `officer_id`, `jurisdiction_id`, `violation_type`, `q` (free text), `page`, `page_size` |
| PATCH | `/scans/{id}` | Update mutable metadata (e.g., link to a `product_id`, correct `package_shape`) |
| POST | `/scans/{id}/reevaluate` | Re-run rule engine (e.g., after a rule version update) — creates new `rule_evaluations` batch, does not touch a finalized report |

### 7.3 Evaluations & Review
| Method | Path | Description |
|---|---|---|
| GET | `/scans/{id}/evaluations` | List rule evaluations with evidence |
| POST | `/scans/{id}/evaluations/{eval_id}/override` | `{outcome, reason}` → creates an override record, `overridden_by` = current user |

### 7.4 Reports
| Method | Path | Description |
|---|---|---|
| POST | `/scans/{id}/report` | Finalize report for current evaluation state → generates PDF/DOCX, returns `ComplianceReport` |
| GET | `/reports/{id}` | Report metadata |
| GET | `/reports/{id}/download?format=pdf|docx` | Signed download URL or streamed file |
| GET | `/products/{id}/reports` | All report history for a product |

### 7.5 Rules (Admin)
| Method | Path | Description |
|---|---|---|
| GET | `/rules` | List rule definitions, filterable by `status`, `rule_code`, `effective_date` |
| GET | `/rules/{rule_code}/versions` | Version history + diffs |
| POST | `/rules` | Create a DRAFT rule definition |
| POST | `/rules/{id}/approve` | Admin/legal approval → status `ACTIVE`, sets `effective_from`, supersedes prior active version |
| GET | `/rules/watch/pending` | Draft rules generated by the Regulatory Watch Service awaiting review |

### 7.6 Dashboard
| Method | Path | Description |
|---|---|---|
| GET | `/dashboard/summary` | Counts: scans today/week/month, pending reviews, violation rate |
| GET | `/dashboard/violations-by-type` | Aggregated chart data |
| GET | `/dashboard/top-non-compliant` | Manufacturers/categories ranked by violation count |
| GET | `/dashboard/geo` | Geotagged scan density (if available) |

### 7.7 Sync (mobile-specific)
| Method | Path | Description |
|---|---|---|
| POST | `/sync/scans/batch` | Batch-submit queued offline scans, each with `client_uuid`; server returns per-item status (`created`, `duplicate_ignored`, `conflict`) |
| GET | `/sync/status?since={timestamp}` | Pull server-side changes relevant to the officer's jurisdiction since last sync (for report-status updates etc.) |

Standard error shape:
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "...", "details": [...] } }
```

---

## 8. Module Specifications

### 8.1 Image Capture & Upload
- Client-side: compress images to a max dimension (e.g., 2400px long edge) before upload to control bandwidth/storage, while preserving enough resolution for OCR of small print (test empirically — do not over-compress, since font-size checks depend on resolution).
- Server-side: validate MIME type and magic bytes (not just extension), strip EXIF GPS unless explicitly consented/needed for the `geo_lat/geo_lng` fields, virus-scan uploads before persisting.
- HEIC → JPEG conversion via a server-side library (e.g., `pillow-heif`) since iOS devices default to HEIC.

### 8.2 Vision/OCR Pipeline
Pipeline stages (each independently testable):
1. **Package/PDP detection** — object detection model (e.g., a fine-tuned YOLOv8) trained to draw a box around the visible package and classify orientation; fallback: user manually crops if detection confidence is low.
2. **Shape-aware area estimation** — combine `package_shape` (user-selected or inferred) with `scale_reference_data` to compute `pdp_area_cm2` per the formula in §4.3.
3. **Text detection** — a scene-text detector (e.g., DBNet/CRAFT via PaddleOCR's detection module) to get line/word-level bounding boxes.
4. **OCR** — recognition model per detected box; run English and Hindi recognition passes and keep the higher-confidence result per box (or a language-id pre-pass).
5. **Glyph height measurement** — for boxes classified later as `mrp` or `net_quantity` numerals (font-size-critical fields), measure bbox height in px, convert to mm using the scale factor derived from `scale_reference_data` (px-per-cm computed from the known package dimension visible in frame).
6. **Confidence gating** — any OCR result below a configurable threshold (e.g., 0.75) is tagged for `NEEDS_MANUAL_REVIEW` regardless of what the rule engine would otherwise conclude.

### 8.3 Declaration Extraction & Field Classification
- **Anchor-based classification (first pass, no ML training data required):**
  - `mrp`: regex for `MRP`, `M.R.P`, `₹`, `Rs.` near a numeral, "inclusive of all taxes".
  - `net_quantity`: regex for `Net Qty`, `Net Wt`, `Net Vol`, unit tokens (g, kg, ml, l, N, U).
  - `mfg_date`: regex/date-parser for month names or MM/YYYY patterns near "Mfg", "Pkd", "Best Before", "Use By".
  - `consumer_care`: regex for phone number patterns, email patterns, "Consumer Care", "Customer Care".
  - `country_of_origin`: regex for "Made in", "Country of Origin".
  - `manufacturer_block`: heuristic — largest contiguous text block containing a PIN code pattern and not matching other anchors.
- **Fallback/refinement (later phase):** a layout-aware classifier (e.g., LayoutLMv3-style) trained on labeled scan data collected during the pilot, for blocks the regex pass leaves `unclassified`.
- **Normalization:** parse currency to `{amount, currency}`; parse dates to ISO; parse quantities to `{value, unit}` with unit canonicalization (e.g., "gm" → "g").
- **Cross-field consistency checks** (feed the rule engine): e.g., unit_sale_price should be mathematically consistent with mrp / net_quantity within a tolerance — a large mismatch is itself a flag.

### 8.4 Rule Engine
- Loads all `rule_definitions` where `status='ACTIVE'` and `effective_from <= scan.captured_at <= coalesce(effective_to, 'infinity')`.
- For each rule: check `applies_to` matches scan mode; check scan's product category is not in `category_exemptions`; then dispatch by `check_type`:
  - `presence`: does at least one `extracted_declarations` row with `field_type = rule.field` and `classification_confidence >= threshold` exist? else `FAIL` (or `NEEDS_MANUAL_REVIEW` if any unclassified block scored close to threshold).
  - `format_regex`: does `normalized_value`/`raw_text` match `params.regex`? 
  - `numeric_threshold`: compare a computed numeric value (e.g., width/height ratio) against `params.min_ratio`.
  - `numeric_threshold_lookup`: look up the required threshold from `params.lookup_table_ref` keyed by `scan.pdp_area_cm2`, compare against `glyph_height_mm`; if `glyph_height_mm` is null (no scale reference) → `NOT_APPLICABLE` with a note "manual verification required".
  - `cross_field_consistency`: evaluate a small expression comparing two or more fields (e.g., unit price vs MRP/quantity).
- Writes one `rule_evaluations` row per rule per scan, with `evidence_detail` capturing the actual numbers compared (critical for the PDF report and for legal defensibility).
- Idempotent: re-running (`POST /scans/{id}/reevaluate`) is safe and produces a fresh batch; does not delete prior evaluations (needed for audit trail if a report was already generated off them).

### 8.5 Compliance Verdict & Report Generation
- `overall_status` derivation: `NON_COMPLIANT` if any rule evaluation is `FAIL`; `PARTIAL_REVIEW_NEEDED` if none are `FAIL` but at least one is `NEEDS_MANUAL_REVIEW`; else `COMPLIANT`.
- PDF template sections: cover page (product, scan id, date, officer, jurisdiction), summary verdict, per-rule table (clause, description, outcome, evidence snippet), annotated images (bounding boxes drawn per evidence region), reviewer sign-off block, footer with report id + version + generation timestamp (for chain-of-custody).
- DOCX generated from the same verdict object via a shared template-rendering function (not a PDF→DOCX conversion) so both are independently editable/legible.
- Store both files in object storage under `reports/{scan_id}/{version}/report.pdf` and `.docx`; store only the `storage_key` in DB, never raw bytes.

### 8.6 Repository & Search
- Deduplication on `products.dedup_key` (generated column) at insert-time; scan-linking flow: after extraction, attempt to match `manufacturer_block` + `brand_name` + `barcode` against existing `products`; if no confident match, create a new `products` row and let a reviewing officer merge duplicates manually if discovered later (`PATCH /scans/{id}` to relink).
- Search v1: PostgreSQL full-text + `pg_trgm` fuzzy matching on manufacturer/brand names, indexed columns for category/date/status filters. Migrate to OpenSearch only if query latency degrades at scale — avoid running two search systems from day one.

### 8.7 Dashboard & Analytics
- Use materialized views refreshed on a schedule (e.g., every 15 min) for heavy aggregate queries (violation-by-type, top-offenders) rather than computing on every dashboard load.
- Jurisdiction-based row-level filtering applied consistently in every aggregate query (an officer should never see another jurisdiction's raw data unless their role permits it).

### 8.8 Auth & RBAC
- JWT access token (short-lived, e.g., 15 min) + refresh token (longer-lived, revocable, stored hashed).
- Role permissions enforced via a central policy table/decorator on every endpoint — e.g., only `REVIEWING_OFFICER`/`ADMIN` can call the override/finalize endpoints; `AUDITOR` is read-only across the board.
- Jurisdiction scoping enforced as a query filter derived from the authenticated user's `jurisdiction_id`, applied server-side (never trust a client-supplied jurisdiction filter for access control, only for narrowing).
- Design the auth service with a pluggable provider interface so departmental SSO/AD integration can be added without reworking RBAC logic.

---

## 9. Frontend Specification (Web)

**Pages:**
- `/login`
- `/dashboard` — role-aware summary + charts (FR-7)
- `/scans` — searchable/filterable list (FR-6)
- `/scans/new` — upload flow: image upload → mode selection → package shape + scale reference input → submit
- `/scans/[id]` — scan detail: image viewer with bounding-box overlay toggle, per-rule verdict table, override controls (role-gated)
- `/scans/[id]/report` — report preview + finalize + download buttons
- `/products/[id]` — product compliance history across all scans
- `/admin/rules` — rule version list, diff viewer, draft review queue (from Regulatory Watch Service)
- `/admin/users` — user/role/jurisdiction management

**Key components:**
- `ImageAnnotationViewer` — renders an image with clickable bounding boxes tied to `extracted_declarations`, color-coded by rule outcome.
- `VerdictTable` — rule code, clause, outcome badge, evidence snippet, override action.
- `ScaleReferenceInput` — dimension entry form / marker-detection preview.
- `ComplianceTrendChart`, `TopOffendersTable`, `GeoHeatmap` — dashboard widgets.

State/data: TanStack Query for server state (scan status polling), minimal global state otherwise; WebSocket or polling (every 3–5s while `status` is in an in-progress state) for live scan-processing updates.

---

## 10. Mobile App Specification

- **Stack:** React Native, local persistence via WatermelonDB or SQLite (op-based, supports offline queries and later sync).
- **Screens:** Login, Scan capture (guided multi-angle camera flow with an on-screen framing guide per panel), Scale reference entry (numeric input or marker overlay), My Scans (draft/queued/synced/conflict status list), Scan detail (read-only verdict view for officers without reviewing rights).
- **Offline behavior:** every capture creates a locally-persisted `Scan` + `ScanImage` records with a client-generated UUID; a background sync task (triggered on connectivity regain, plus periodic retry) pushes queued scans via `/sync/scans/batch`; images upload via resumable/chunked upload separately from metadata so a large photo doesn't block the whole batch.
- **Conflict UI:** if the server reports `conflict` for a synced item (only possible on report-edit scenarios, not new scan creation — see §11.2), surface a merge screen rather than silently discarding either version.

---

## 11. Synchronization Design

*(Full detail already elaborated in the companion engineering plan §11; summarized here for spec completeness — implement exactly as follows.)*

**11.1 Legal Rules DB:** Regulatory Watch Service (scheduled crawler) creates `rule_definitions` rows with `status='DRAFT'`; only an Admin/legal reviewer calling `POST /rules/{id}/approve` moves a rule to `status='ACTIVE'` with a set `effective_from`; the previous active version for that `rule_code` is set to `status='SUPERSEDED'` with `effective_to` = new rule's `effective_from`. A `rule_change_log` row is written on every transition.

**11.2 Offline mobile scans:** New scans use client-generated UUIDs (`scans.client_uuid`, unique constraint) as idempotency keys — safe to retry. Report edits (the only shared-mutable case) use optimistic concurrency: `compliance_reports` and `rule_evaluations` overrides check the client's last-seen version/timestamp against the server's current one on write; a mismatch returns `409 Conflict` with the current server state, and the client surfaces the merge screen (§10) rather than overwriting.

**11.3 External product data:** `external_product_cache` keyed by barcode, populated by on-demand lookups at scan time (cache miss → live API call → cache write with `ttl_expires_at`) plus an optional nightly batch refresh job for high-traffic barcodes. Cached data pre-fills UI fields for officer convenience only; it is never written into `extracted_declarations` or used directly by the rule engine — only OCR-extracted, image-evidenced data feeds a verdict.

---

## 12. Infrastructure & Deployment

**Containerization:** every service (API, OCR worker, extraction worker, rule engine worker, report generator, regulatory watch job) is a separate Docker image sharing a common base image for Python dependencies.

**Local dev:** `docker-compose.yml` bringing up: `api`, `worker-ocr`, `worker-extraction`, `worker-rules`, `worker-reports`, `postgres`, `redis`, `minio` (S3-compatible local storage), `web` (Next.js dev server).

**CI/CD (GitHub Actions):**
- On PR: lint (ruff/eslint), type-check (mypy/tsc), unit tests, build Docker images.
- On merge to main: run integration tests against a docker-compose test stack, push images to registry, deploy to staging.
- Manual approval gate for production deploy (appropriate for a government system).

**Production topology (target):**
- API + web behind a load balancer / reverse proxy (Nginx or a managed ALB).
- Worker pools (OCR, extraction, rule engine, reports) as independently scalable deployments (Kubernetes `Deployment` + `HorizontalPodAutoscaler` keyed on queue depth, or simpler managed container service if Kubernetes is overkill for pilot scale).
- Managed/self-hosted PostgreSQL with automated backups (point-in-time recovery) and read replica for dashboard/reporting queries at scale.
- Object storage with versioning enabled (protects generated reports from accidental overwrite).
- Deployment target for pilot: cloud VPC; production target: on-prem or MeitY/NIC-empanelled cloud per data-residency requirements (§3).

**Observability:** structured logging (JSON) from every service, centralized (e.g., an ELK/OpenSearch stack or a managed log service), request tracing across the async pipeline (correlate by `scan_id`), metrics (queue depth, OCR latency p50/p95, rule-engine error rate) exported to a dashboard (Grafana/Prometheus or equivalent).

---

## 13. Security Specification

- **Transport:** TLS 1.2+ everywhere; HSTS on web app.
- **At rest:** DB encryption at rest (managed DB feature or disk-level encryption); object storage server-side encryption.
- **AuthN:** JWT access + refresh tokens; refresh tokens revocable and stored hashed; password policy enforced (min length, complexity) if not using SSO; support MFA for Admin role at minimum.
- **AuthZ:** enforced server-side on every endpoint (§8.8); never rely on UI hiding alone.
- **Input validation:** strict schema validation (Pydantic) on every API input; file upload validation (§8.1).
- **PII/sensitive handling:** manufacturer/consumer-care contact details are business data (not personal-sensitive in the privacy sense), but officer/user accounts and any citizen complaint data (future phase) must follow standard PII handling — minimize retention, restrict access by role.
- **Audit logging:** every login, permission-denied event, override, and finalize action logged to `audit_log` (§6), retained per the organization's records-retention policy (likely multi-year given legal use).
- **Dependency hygiene:** automated dependency vulnerability scanning in CI (e.g., `pip-audit`, `npm audit`, Docker image scanning).
- **Secrets management:** no secrets in source control; use environment injection via a secrets manager (Vault, cloud-native secrets manager, or at minimum encrypted `.env` handling in CI/CD).

---

## 14. Testing Strategy & Acceptance Criteria

| Layer | Approach |
|---|---|
| Unit tests | Rule engine check-type dispatch logic (each `check_type` tested with synthetic `extracted_declarations` fixtures covering PASS/FAIL/NOT_APPLICABLE/NEEDS_MANUAL_REVIEW); regex/normalization parsers tested against a curated set of real-world label text variants |
| OCR/extraction accuracy | A held-out labeled test set of package images (manually annotated ground-truth declarations) — track field-level precision/recall and glyph-height measurement error (mm) against ground truth; set a minimum acceptance bar before a pipeline change ships (e.g., ≥90% presence-detection recall on mandatory fields before enabling auto-verdicts for a field) |
| Integration tests | Full pipeline run (upload → OCR → extraction → rule evaluation → report) against a docker-compose test stack using fixture images |
| API contract tests | Schema validation against the OpenAPI spec generated from FastAPI |
| E2E tests | Web app critical flows (Playwright/Cypress): login → new scan → review → finalize → download report; search and filter flows |
| Mobile offline tests | Simulate airplane-mode capture → reconnect → verify sync, idempotency (duplicate submission does not create a duplicate scan), and conflict-surfacing on a simulated concurrent report edit |
| Rule-versioning tests | Verify a scan captured before a rule amendment continues to evaluate against the old rule version on re-fetch, while a new scan uses the new version |
| Security tests | RBAC boundary tests (each role attempting every endpoint, expect correct 200/403), auth token expiry/refresh flow, file upload fuzzing (oversized/malformed files rejected) |
| Load tests | Simulate pilot-scale concurrent scan submissions; measure queue depth and worker autoscaling behavior |

---

## 15. Repository / Project Structure (suggested)

```
legal-metrology-compliance/
├── apps/
│   ├── web/                     # Next.js app
│   └── mobile/                  # React Native app
├── services/
│   ├── api/                     # FastAPI gateway + scan orchestration
│   ├── worker-ocr/
│   ├── worker-extraction/
│   ├── worker-rules/
│   ├── worker-reports/
│   ├── regulatory-watch/
│   └── auth/
├── packages/
│   ├── shared-types/             # TS types shared web/mobile, generated from OpenAPI
│   └── rule-schema/               # Python + JSON-schema for RuleDefinition, shared by rule engine + admin UI
├── infra/
│   ├── docker-compose.yml
│   ├── k8s/                       # manifests, if used
│   └── ci/                        # GitHub Actions workflows
├── docs/
│   ├── engineering-plan.md
│   ├── technical-spec.md          # this document
│   └── rule-catalog/              # per-rule legal citation + review sign-off records
└── tests/
    ├── fixtures/                  # sample label images + ground-truth annotations
    └── e2e/
```

---

## 16. Sprint-Level Delivery Plan (elaborates Phase 0–2 of the engineering plan)

| Sprint | Focus | Key deliverables |
|---|---|---|
| 1 | Foundations | Repo scaffold, CI skeleton, DB schema migration, auth service, jurisdiction/user admin CRUD |
| 2 | Legal rule digitization | `rule_definitions` seeded with Rule 6/7 presence+format checks (`[VERIFY]`ed by legal reviewer), rule admin UI (view/approve) |
| 3 | Upload + manual-review MVP | Image upload API + web upload UI, manual field-confirmation UI (no auto-extraction yet), presence/format rule evaluation only |
| 4 | Report generation | PDF/DOCX report templates, finalize/version flow, download endpoints |
| 5 | OCR pipeline v1 | Text detection + OCR integration, field classification (regex/anchor pass), confidence gating |
| 6 | Scale calibration + font checks | Manual dimension entry, PDP area calc, glyph-height-mm computation, numeric_threshold_lookup checks |
| 7 | Repository + search | Product dedup, search/filter UI, CSV export |
| 8 | Review/override workflow | Evidence overlay viewer, override endpoint + audit trail, finalize gating by role |
| 9 | Mobile app v1 | Capture flow, local storage, basic online-only submit |
| 10 | Offline sync | Client UUID idempotency, batch sync endpoint, conflict surfacing |
| 11 | E-commerce ingestion | URL scraping, DOM text extraction, ecommerce rule variant |
| 12 | Dashboards | Materialized views, chart endpoints, dashboard UI |
| 13 | Regulatory Watch Service | Crawler + draft rule creation + admin review queue |
| 14 | Hardening & pilot | Security review, load test, accessibility pass, pilot deployment with a real enforcement unit, feedback loop |

---

## 17. Glossary

- **LMPC Rules** — Legal Metrology (Packaged Commodities) Rules, 2011.
- **PDP** — Principal Display Panel; the package face where mandatory declarations must appear.
- **MRP** — Maximum Retail Price.
- **Rule version** — a specific, dated, immutable snapshot of a single rule's check logic.
- **Verdict / Rule Evaluation** — the PASS/FAIL/NOT_APPLICABLE/NEEDS_MANUAL_REVIEW outcome of one rule against one scan.
- **Client UUID** — an idempotency key generated on-device at scan creation, used to make offline-to-online sync safe against retries.
- **Regulatory Watch Service** — the scheduled job that monitors for new LMPC notifications and drafts (never auto-publishes) rule updates.

---

*This spec is implementation-ready for the sprint plan in §16, with the explicit caveat that every `[VERIFY]` marker in §4 must be closed out with a legal reviewer before the corresponding rule ships as an automated check.*
