# Findeck Design System - Visual Restyle Notes

## 1. Visual Analysis of `findeck-reference.jpg`

The reference screenshot represents a clean, airy, high-precision finance dashboard ("Findeck").
Key visual attributes:
- **Layout:** Standard viewport app with fixed left sidebar (~240px) on light subtle background, separated by a 1px border. Main content occupies the remaining viewport with ~24-32px padding on an off-white canvas.
- **Card Styling:** Solid white cards (`#FFFFFF`) with 1px subtle border (`#E6EAE7`), ~14-16px rounded corners (`rounded-2xl`), 20px padding, and very subtle or no drop-shadow (`shadow-xs` / `shadow-2xs`).
- **Accent Color:** Vibrant emerald green (`#00A843` / `#12B800`) used for primary call-to-actions, logo marks, active indicators, and positive trends.
- **Typography:** Inter sans-serif typeface, tabular numbers for numeric/financial data, dark slate (`#0F1A12`) primary text, and muted slate (`#6B766F`) for secondary descriptions.

### Sampled Colors (Pillow `getpixel` sampling from reference)
- `--bg-app`: `#F7F8FA` (Content viewport background behind cards)
- `--bg-sidebar`: `#F2F3F7` (Left sidebar navigation background)
- `--bg-card`: `#FFFFFF` (Surface background for cards and tables)
- `--border`: `#E6EAE7` (1px subtle border)
- `--text`: `#0F1A12` (Primary dark text)
- `--text-muted`: `#6B766F` (Secondary / helper text)
- `--accent`: `#12B800` / `#00A843` (Primary emerald green)
- `--accent-hover`: `#0FA000` / `#009B3A` (Darker green on hover)
- `--accent-soft`: `#DFF4E1` (Soft green pill / delta background)
- `--accent-soft-border`: `#BFE6B8` (Border for soft green elements)
- `--danger`: `#D93636` (Error / negative trend red)
- `--danger-soft`: `#FFEAE6` (Soft red pill background)
- `--warning`: `#F5A524` (Warning / pending status amber)
- `--warning-soft`: `#FEF7DB` (Soft amber pill background)
- `--info`: `#2563EB` (Processing / informational blue)
- `--info-soft`: `#E8EFFD` (Soft blue pill background)

---

## 2. Frontend Inventory

### Routes & Pages (`web/src/pages/`)
1. `/login` -> `Login.tsx`: User authentication screen with email and password fields.
2. `/queue` -> `ReviewQueue.tsx`: Primary queue listing invoices awaiting review, with filters, search, sorting, and table.
3. `/invoices/:id` -> `ReviewDetail.tsx`: Dual-pane verification workspace with DocumentViewer and editable extraction form.
4. `/inbox` -> `Inbox.tsx`: Drag-and-drop ingestion zone with batch upload results and recent invoices table.
5. `/dashboard` -> `Dashboard.tsx`: Metrics and operational analytics overview.
6. `/admin` -> `Admin.tsx`: Supplier directory management, user roles, and system configuration (admin-only).

### Shared Components (`web/src/components/`)
1. `Layout.tsx`: Main app shell (sidebar, top bar, breadcrumb, outlet).
2. `DocumentViewer.tsx`: Document viewer with zoom, pan, rotate, and page navigation controls.
3. `AuditTrailFlowchart.tsx`: Interactive audit timeline and state machine transitions.

---

## 3. Scope & Constraints

- **Strict zero-functional-change policy**: All existing features, API calls, hooks, schemas, state, and workflows remain 100% intact.
- **Forbidden additions**: No fake "Upgrade" banners, no mock heatmaps, no fake financial statement nav items.
- **Preserved user text**: All labels, placeholders, headings, and test IDs remain exactly as they were.
- **Sidebar Groups**: Decorative group headings added: `WORKSPACE` (Review Queue, Inbox) and `OPERATIONS` (Dashboard, Admin).
