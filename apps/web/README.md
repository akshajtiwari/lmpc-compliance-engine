# LMPC Workbench

The web workbench manages inspections, evidence review, accounts, field-device enrollment and reports. It is intentionally a separate interface from the phone capture app.

```bash
cp .env.example .env.local
npm install
npm run dev
```

Start the LMPC API on port 8000 first. Next.js proxies `/api/v1/*` to `LMPC_API_ORIGIN`, keeping the refresh cookie same-origin in the browser.

After signing in with `scans:create`, use **Inspections → New inspection** to upload
non-guided package photographs or an e-commerce listing. Listing inspections require the
visible product-page declaration text and one to six screenshots; an optional HTTP(S)
source URL is retained with the immutable evidence. Use the separate LMPC Field Android
app when guided capture and a complete physical-package coverage assertion are required.
