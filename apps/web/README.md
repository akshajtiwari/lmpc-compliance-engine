# LMPC Workbench

The web workbench manages inspections, evidence review, accounts, field-device enrollment and reports. It is intentionally a separate interface from the phone capture app.

```bash
cp .env.example .env.local
npm install
npm run dev
```

Start the LMPC API on port 8000 first. Next.js proxies `/api/v1/*` to `LMPC_API_ORIGIN`, keeping the refresh cookie same-origin in the browser.
