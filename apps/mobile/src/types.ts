export type Principal = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  jurisdiction: string | null;
  permissions: string[];
};

export type Session = {
  serverUrl: string;
  fingerprint: string;
  accessToken: string;
  refreshToken: string;
  user: Principal;
};

export type AccountScope = {
  accountId: string;
  serverFingerprint: string;
};

export type FrameQualityReport = {
  source: "CAMERA" | "GALLERY";
  sharpness: number;
  mean_luma: number;
  glare_fraction: number;
  warnings: string[];
};

export type PanelLabel = "FRONT" | "BACK" | "SIDE_1" | "SIDE_2" | "SCALE_REF"
  | "LISTING" | `LISTING_${2 | 3 | 4 | 5 | 6}`;

export type CapturedPanel = {
  panel: PanelLabel;
  uri: string;
  source: "CAMERA" | "GALLERY";
  quality?: FrameQualityReport;
};

// Corner marks in ORIGINAL image pixel coordinates, clockwise from the first
// corner of the long edge. The server's scale module re-derives everything.
export type ScaleReference = {
  type: "NONE" | "ISO_ID1_CARD";
  data?: {
    observed_px?: number;
    quad?: number[][];
    panel_quad?: number[][];
  };
};

export type Draft = {
  clientUuid: string;
  capturedAt: string;
  category: string;
  buyerType: "RETAIL" | "INDUSTRIAL" | "INSTITUTIONAL";
  packageShape: "RECTANGULAR" | "CYLINDRICAL" | "IRREGULAR";
  coverageAsserted: boolean;
  panels: CapturedPanel[];
  mode?: "PHYSICAL_PACKAGE" | "ECOMMERCE_LISTING";
  scaleReference?: ScaleReference;
  listing?: {text: string; url: string | null};
};

export type Finding = {
  id: string;
  check: string;
  clause: string;
  outcome: string;
  reason: string;
};

export type ScanResult = {
  scan_id: string;
  status: string;
  overall: string | null;
  captured_at: string;
  category: string;
  buyer_type: string;
  decision_explanation: {
    heading: string;
    summary: string;
    next_step: string;
    processing_stage: string;
    ocr_ran: boolean;
  } | null;
  evaluations: Finding[];
  images?: {panel: string}[];
};

export type RuleDetail = {
  check: string;
  title: string;
  clause: string;
  requirement: string;
  method: string;
  evidence_needed: string;
  important_limits: string[];
  outcomes: Record<string, string>;
  non_normative_notice: string;
};

export type ReportSummary = {
  id: string;
  version: number;
  overall_status: string;
  finalized_at: string;
};

export type LocalInspection = {
  client_uuid: string;
  scan_id: string | null;
  captured_at: string;
  category: string;
  overall: string | null;
  state: "QUEUED" | "UPLOADING" | "COMPLETE" | "FAILED";
  error: string | null;
  draft_json: string;
  attempts: number;
  next_attempt_at: string | null;
  last_attempt_at: string | null;
  synced_at: string | null;
  account_id: string | null;
  server_fingerprint: string | null;
  updated_at: string;
};
