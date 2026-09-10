"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import type { Scan } from "@/lib/types";

const CATEGORIES = [
  "GENERIC", "FOOD", "COSMETIC", "CEMENT", "FERTILIZER", "FARM_PRODUCE",
  "TOBACCO", "DRUG_FORMULATION", "MEDICAL_DEVICE", "RESTAURANT_FAST_FOOD",
  "HANDLOOM_THREAD_COIL",
] as const;
const PHYSICAL_PANELS = [
  ["FRONT", "Front / principal display"],
  ["BACK", "Back"],
  ["SIDE_1", "Side panel 1"],
  ["SIDE_2", "Side panel 2"],
] as const;
type PhysicalPanel = typeof PHYSICAL_PANELS[number][0];
type Mode = "PHYSICAL_PACKAGE" | "ECOMMERCE_LISTING";

export default function NewInspectionPage() {
  const { api } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("PHYSICAL_PACKAGE");
  const [capturedAt, setCapturedAt] = useState(localDate());
  const [category, setCategory] = useState("GENERIC");
  const [buyerType, setBuyerType] = useState("RETAIL");
  const [packageShape, setPackageShape] = useState("RECTANGULAR");
  const [physicalFiles, setPhysicalFiles] = useState<Partial<Record<PhysicalPanel, File>>>({});
  const [listingFiles, setListingFiles] = useState<File[]>([]);
  const [listingUrl, setListingUrl] = useState("");
  const [listingText, setListingText] = useState("");
  const [isImported, setIsImported] = useState(false);
  const [isMolded, setIsMolded] = useState(false);
  const [otherLaw, setOtherLaw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  function chooseMode(value: Mode) {
    setMode(value);
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setStatus("Preparing evidence…");
    let scanId = "";
    try {
      const evidence = mode === "PHYSICAL_PACKAGE"
        ? PHYSICAL_PANELS.flatMap(([panel]) => physicalFiles[panel]
          ? [{ panel, file: physicalFiles[panel] }] : [])
        : listingFiles.map((file, index) => ({
          panel: index === 0 ? "LISTING" : `LISTING_${index + 1}`,
          file,
        }));
      if (!evidence.length) throw new Error("Add at least one evidence image.");
      if (evidence.length > 6) throw new Error("A maximum of six evidence images is allowed.");
      if (mode === "ECOMMERCE_LISTING" && !listingText.trim()) {
        throw new Error("Paste the declarations visible on the product listing.");
      }

      const form = new FormData();
      form.append("client_uuid", crypto.randomUUID());
      form.append("captured_at", capturedAt);
      form.append("mode", mode);
      form.append("category", category);
      form.append("buyer_type", buyerType);
      form.append("package_shape", packageShape);
      form.append("coverage_asserted", "false");
      form.append("scale_reference", JSON.stringify({ type: "NONE" }));
      form.append("dimensions", "{}");
      form.append("flags", JSON.stringify({
        is_imported: isImported,
        is_molded: isMolded,
        other_law_requires_same_info: otherLaw,
      }));
      form.append("geo", "{}");
      form.append("ecommerce", JSON.stringify(mode === "ECOMMERCE_LISTING"
        ? { url: listingUrl.trim() || null, listing_text: listingText.trim() }
        : {}));
      const hashes = await Promise.all(evidence.map(({ file }) => sha256(file)));
      evidence.forEach(({ panel, file }, index) => {
        form.append("panels", panel);
        form.append("images", file, file.name);
        form.append("image_sha256", hashes[index]);
      });

      setStatus("Uploading immutable evidence…");
      const created = await api<Scan>("/scans", { method: "POST", body: form });
      scanId = created.scan_id;
      setStatus("Running OCR and deterministic rules…");
      if (!created.evaluations.length) {
        await api<Scan>(`/scans/${scanId}/process`, { method: "POST" });
      }
      router.push(`/scans/${scanId}`);
    } catch (cause) {
      if (scanId) {
        router.push(`/scans/${scanId}`);
      } else {
        setError(cause instanceof Error ? cause.message : "Could not create inspection");
        setStatus("");
      }
    } finally {
      setBusy(false);
    }
  }

  return <AppShell>
    <div className="page-head">
      <div>
        <p className="eyebrow">New evidence</p>
        <h1>Create inspection</h1>
        <p>Upload package photographs or capture an e-commerce product listing for server-side analysis.</p>
      </div>
      <Link className="button secondary" href="/scans">Cancel</Link>
    </div>
    <form className="inspection-form" onSubmit={submit}>
      <section className="card grid">
        <div>
          <p className="eyebrow">Step 1</p>
          <h2>Inspection source</h2>
        </div>
        <div className="mode-picker" role="radiogroup" aria-label="Inspection source">
          <label className={`mode-option ${mode === "PHYSICAL_PACKAGE" ? "selected" : ""}`}>
            <input type="radio" name="mode" value="PHYSICAL_PACKAGE"
              checked={mode === "PHYSICAL_PACKAGE"} onChange={() => chooseMode("PHYSICAL_PACKAGE")} />
            <span><strong>Packaged commodity</strong><small>Photographs taken or received for desk review</small></span>
          </label>
          <label className={`mode-option ${mode === "ECOMMERCE_LISTING" ? "selected" : ""}`}>
            <input type="radio" name="mode" value="ECOMMERCE_LISTING"
              checked={mode === "ECOMMERCE_LISTING"} onChange={() => chooseMode("ECOMMERCE_LISTING")} />
            <span><strong>E-commerce listing</strong><small>Product-page screenshots plus the visible declaration text</small></span>
          </label>
        </div>
        <div className="form-grid three">
          <Field label="Inspection date" htmlFor="captured-at">
            <input id="captured-at" className="input" type="date" value={capturedAt}
              max={localDate()} onChange={(event) => setCapturedAt(event.target.value)} required />
          </Field>
          <Field label="Commodity category" htmlFor="category">
            <select id="category" className="select" value={category}
              onChange={(event) => setCategory(event.target.value)}>
              {CATEGORIES.map((value) => <option key={value}>{value}</option>)}
            </select>
          </Field>
          <Field label="Buyer type" htmlFor="buyer-type">
            <select id="buyer-type" className="select" value={buyerType}
              onChange={(event) => setBuyerType(event.target.value)}>
              {["RETAIL", "INDUSTRIAL", "INSTITUTIONAL"].map((value) =>
                <option key={value}>{value}</option>)}
            </select>
          </Field>
        </div>
        {buyerType !== "RETAIL" && <div className="notice">
          Applicability may stop before OCR for this buyer type. Select it only when it
          describes the actual sale, not the product category.
        </div>}
      </section>

      <section className="card grid">
        <div>
          <p className="eyebrow">Step 2</p>
          <h2>{mode === "PHYSICAL_PACKAGE" ? "Package evidence" : "Listing evidence"}</h2>
        </div>
        {mode === "PHYSICAL_PACKAGE" ? <>
          <div className="notice">
            This desktop path is non-guided and never claims that every package surface was
            captured. Use LMPC Field when complete physical coverage must support an absence finding.
          </div>
          <Field label="Package shape" htmlFor="package-shape">
            <select id="package-shape" className="select" value={packageShape}
              onChange={(event) => setPackageShape(event.target.value)}>
              {["RECTANGULAR", "CYLINDRICAL", "IRREGULAR"].map((value) =>
                <option key={value}>{value}</option>)}
            </select>
          </Field>
          <div className="file-grid">
            {PHYSICAL_PANELS.map(([panel, label]) => <label className="file-slot" key={panel}>
              <strong>{label}</strong>
              <span>{physicalFiles[panel]?.name || (panel === "FRONT" ? "Required" : "Optional")}</span>
              <input type="file" accept="image/jpeg,image/png,image/heic,image/heif"
                required={panel === "FRONT"} onChange={(event) => setPhysicalFiles((current) => ({
                  ...current, [panel]: event.target.files?.[0],
                }))} />
            </label>)}
          </div>
        </> : <>
          <div className="form-grid">
            <Field label="Product-page URL (optional)" htmlFor="listing-url">
              <input id="listing-url" className="input" type="url" value={listingUrl}
                placeholder="https://shop.example/product"
                onChange={(event) => setListingUrl(event.target.value)} />
            </Field>
            <Field label="Visible declaration text" htmlFor="listing-text">
              <textarea id="listing-text" className="textarea listing-input" value={listingText}
                maxLength={50000} required
                placeholder={"Paste only text visible to the shopper, preserving line breaks.\nExample: MRP ₹45 (incl. of all taxes)"}
                onChange={(event) => setListingText(event.target.value)} />
              <span className="field-help">{listingText.length.toLocaleString("en-IN")} / 50,000 characters</span>
            </Field>
            <Field label="Listing screenshots (1–6)" htmlFor="listing-images">
              <input id="listing-images" className="input" type="file" multiple required
                accept="image/jpeg,image/png,image/heic,image/heif"
                onChange={(event) => setListingFiles(Array.from(event.target.files ?? []))} />
              <span className="field-help">
                {listingFiles.length ? `${listingFiles.length} screenshot(s) selected` : "Capture the displayed declarations as supporting evidence."}
              </span>
            </Field>
          </div>
        </>}
      </section>

      <section className="card grid">
        <div>
          <p className="eyebrow">Step 3</p>
          <h2>Applicable package facts</h2>
          <p className="muted small">These are officer-supplied facts and remain separate from extracted label declarations.</p>
        </div>
        <div className="check-grid">
          <Check label="Imported package" checked={isImported} change={setIsImported} />
          <Check label="Declaration moulded or embossed" checked={isMolded} change={setIsMolded} />
          <Check label="Same information required under another law" checked={otherLaw} change={setOtherLaw} />
        </div>
      </section>

      {error && <div className="error" role="alert">{error}</div>}
      {status && <div className="notice" role="status" aria-live="polite">{status}</div>}
      <div className="form-actions">
        <span className="muted small">Images are hash-verified and stored before processing begins.</span>
        <button className="button primary" disabled={busy}>
          {busy ? "Processing…" : "Create and analyse"}
        </button>
      </div>
    </form>
  </AppShell>;
}

function Field({ label, htmlFor, children }: {
  label: string; htmlFor: string; children: React.ReactNode;
}) {
  return <div className="field"><label htmlFor={htmlFor}>{label}</label>{children}</div>;
}

function Check({ label, checked, change }: {
  label: string; checked: boolean; change: (value: boolean) => void;
}) {
  return <label className="check-option">
    <input type="checkbox" checked={checked}
      onChange={(event) => change(event.target.checked)} />
    <span>{label}</span>
  </label>;
}

async function sha256(file: File) {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")).join("");
}

function localDate() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}
