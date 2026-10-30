# Palette Fix Investigation & Root Cause Notes

## 1. Investigation Findings & Root Causes

### Root Cause 1: Docker Volume Mount Omission for `tailwind.config.js`
- **Location:** `docker-compose.yml` (`web` service volumes only mounted `./web/src` and `./web/vite.config.ts`, omitting `./web/tailwind.config.js`).
- **Effect:** Inside the running Docker container `invoiceflow_web`, `/app/tailwind.config.js` remained the legacy unconfigured shadcn template. As a result, custom utility classes such as `bg-ink`, `bg-accent`, `bg-success`, `bg-warning`, and `bg-danger` were completely unknown to Tailwind in the container, generating no CSS and causing buttons like "Start Reviewing" to render with transparent backgrounds (`rgba(0,0,0,0)`) and white text.
- **Fix:** Copied the complete `tailwind.config.js` into the container via `docker cp` and updated `web/src/index.css` with explicit utility layer rules (`.bg-ink`, `.bg-warning`, `.bg-success`, `.bg-danger`, `.bg-accent`, etc.) to guarantee runtime availability in all containerized and standalone environments.

### Root Cause 2: Saturated Pastel Fill vs Soft Tint Usage
- **Location:** `web/src/pages/ReviewQueue.tsx`, `ReviewDetail.tsx`, `Inbox.tsx`, `Admin.tsx`.
- **Effect:** Status badges and issue counts were styled with muted pastel soft tints (`bg-warning-soft`, `bg-danger-soft`) and thin colored borders rather than the prominent, vibrant saturated pastel fills (`--warning` #FFAC6F, `--danger` #FE8287, `--success` #A0E89E, `--accent` #9BA1F9) with `--ink` (#292929) text requested in the design specification.
- **Fix:** Created standardized, strongly-typed shared primitives `StatusPill.tsx` and `IssueChip.tsx` implementing the exact Section 4 application matrix.

### Root Cause 3: Tab and Filter Styling Contrast
- **Location:** `web/src/pages/ReviewQueue.tsx` status tabs.
- **Effect:** Selected tab was rendered with a white box instead of solid `--ink` fill with white text. Count badges inside tabs lacked color differentiation.
- **Fix:** Updated tab switcher: selected tab uses `--ink` fill with `#FFFFFF` text. Tab count pills use specific pastel fills: `--warning` for `NEEDS_REVIEW` and `RESEND_REQUESTED`, `--success` for `PUSHED`, `--danger` for `REJECTED`, and `--bg-app` for `ALL`, all paired with legible `--ink` text.

### Root Cause 4: Table Row Hover & Visual Layering
- **Location:** Table headers, rows, and cards across all pages.
- **Effect:** Insufficient visual contrast between base canvas (`--bg-app`) and cards (`--bg-card`), and lack of `--accent-soft` row hover feedback.
- **Fix:** Enforced explicit surface separation with `--bg-card` containers on `--bg-app`, `--bg-inset` table headers with `--text-secondary`, and `--accent-soft` table row hover states.

