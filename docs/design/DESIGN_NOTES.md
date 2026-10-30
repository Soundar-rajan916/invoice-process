# Design Notes: Findeck Layout with Pastel Palette

This document records the visual analysis and design specifications for restyling the InvoiceFlow frontend.
- **Reference A (Layout & Components):** "Findeck" finance dashboard (`docs/design/findeck-reference.jpg`).
- **Reference B (Colour Palette):** HR dashboard with pastel cards (`docs/design/palette-reference.png`).
- **Strict Rule:** Change design only. Zero logic, route, API, text, or test assertion changes. Do not use Findeck's green anywhere.

---

## 1. Reference A: Layout, Spacing, Radii & Typography (from `findeck-reference.jpg`)

- **Overall Feel:** Clean, airy, high-precision finance dashboard.
- **Layout Architecture:**
  - Fixed left sidebar (~240–248 px wide) on `--bg-card` surface, separated from main area by 1px hairline border (`--border`).
  - Main content area on `--bg-app` with 24–32 px padding.
  - Layered surface depth:
    - Layer 0 (Base app background): `--bg-app` (`#ECEDF1`)
    - Layer 1 (Cards, sidebar): `--bg-card` (`#F7F7F9`)
    - Layer 2 (Inner cells, inputs, table rows, chips): `--bg-inset` (`#FFFFFF`)
  - Cards in consistent grids with 16 px gap (`gap-4`).
- **Radii Scale:**
  - Cards: ~16 px (`rounded-2xl` / `--radius-card`)
  - Buttons & Inputs: ~10–12 px (`rounded-xl` / `--radius-btn`)
  - Pills & Badges: Fully rounded (`rounded-full` / `--radius-pill`)
- **Typography Scale (Inter Variable):**
  - Page Title: 22–24 px semibold (`text-xl` to `text-2xl`)
  - Card Title / Group Heading: 14–15 px medium (`text-sm font-semibold`)
  - Body Text: 14 px regular (`text-sm`)
  - Labels & Table Headers: 12 px medium (`text-xs font-medium text-secondary`)
  - KPI Big Value: 24–28 px semibold (`text-2xl` or `text-3xl font-bold`)
  - Tabular Numerals: `font-variant-numeric: tabular-nums` for all currencies, IDs, and quantities.

---

## 2. Reference B: Sampled Colour Palette (from `palette-reference.png`)

Sampled using Pillow patch-frequency analysis from `docs/design/palette-reference.png`:

### Surfaces & Borders
- `--bg-app`: `#ECEDF1` (page canvas behind cards)
- `--bg-card`: `#F7F7F9` (cards and sidebar background)
- `--bg-inset`: `#FFFFFF` (inputs, table rows, chips, and inner cards)
- `--bg-disabled`: `#F0F1F3` (disabled elements and non-working cells)
- `--border`: `#E3E4EA` (hairlines, dividers, subtle borders)

### Ink & Text
- `--ink`: `#292929` (primary buttons, active tab pill, logo mark)
- `--ink-hover`: `#3D3D3F` (hover state for ink buttons)
- `--text`: `#1D1E20` (headings, values, and primary body)
- `--text-secondary`: `#535353` (labels, table header titles)
- `--text-muted`: `#666668` (helper descriptions, breadcrumb crumbs)

### Pastel Accents (used as fills with `--ink` #292929 text)
- `--accent`: `#9BA1F9` (periwinkle: active nav badge, selected status, processing)
- `--success`: `#A0E89E` (mint: approved, active status, matching totals)
- `--danger`: `#FE8287` (coral: rejected, failed, mismatches, delete actions)
- `--warning`: `#FFAC6F` (orange: needs review, resend requested, pending)

### Soft Tints (for panels, banner backgrounds, and soft badges)
- `--accent-soft`: `#EEEEF8` (lavender: duplicate panel, count pills)
- `--success-soft`: `#EEF5EE` (mint tint: approved panels, success notices)
- `--danger-soft`: `#F7EBED` (blush tint: validation error panels, issues)
- `--warning-soft`: `#FFF1E4` (orange tint: validation warning panels)

### Strong Contrast Variants (for text, icons, focus rings, borders on light surfaces)
- `--accent-strong`: `#4B52D8` (links, focus rings, active text) - Contrast ~5.6:1
- `--success-strong`: `#1E7B3A` (success text/icons on light surface) - Contrast ~5.0:1
- `--danger-strong`: `#B3262B` (error text/icons on light surface) - Contrast ~6.1:1
- `--warning-strong`: `#A84E00` (warning text/icons on light surface) - Contrast ~5.2:1

### Palette Usage Rules
- **Pastels are fills, not text colours.** Text on pastel fills is always `--ink` (`#292929`). Never white text on pastels.
- **Strong variants for text/icons on light backgrounds:** Any status text rendered directly on `--bg-card` or `--bg-inset` uses the `*-strong` variant.
- **No Findeck Green:** The emerald green from Reference A is completely replaced by Reference B's `--ink` and `--accent` / `--success` tokens.

---

## 3. Frontend Inventory

### Routes & Pages (`web/src/pages/`)
1. `/login` -> `Login.tsx`: Authentication screen (email, password, submit button, error alerts).
2. `/queue` -> `ReviewQueue.tsx`: Primary queue with search, status filters, sorting, stats bar, and invoices table.
3. `/invoices/:id` -> `ReviewDetail.tsx`: Split review workspace with document viewer card on the left, editable form on the right, validation issues, duplicate comparison, and action buttons.
4. `/inbox` -> `Inbox.tsx`: Drag-and-drop file ingestion zone with upload progress and recent invoices table.
5. `/dashboard` -> `Dashboard.tsx`: Operational overview with 4 KPI cards and breakdown tables.
6. `/admin` -> `Admin.tsx`: Supplier directory master, user accounts table, and modal dialogs.

### Shared Components (`web/src/components/`)
1. `Layout.tsx`: Application shell containing sidebar, grouped nav (`WORKSPACE` & `OPERATIONS`), active badges, top breadcrumb bar, user profile card, and logout button.
2. `DocumentViewer.tsx`: Canvas document viewer with toolbar, pan/zoom, page navigation, and thumbnail rail.
3. `AuditTrailFlowchart.tsx`: Visual audit trail drawer showing state machine lifecycle.

---

## 4. Baseline Checks Summary

- **TypeScript Typecheck (`tsc`):** Passed with 0 errors.
- **Frontend Build (`vite build`):** Passed cleanly, dist bundle created.
- **Vitest Suite:** `src/test/ReviewDetail.test.tsx` (4 tests) passed.
- **Backend Pytest Suite:** All 23 tests in `test_validation.py` and `test_api_coverage.py` passed.
