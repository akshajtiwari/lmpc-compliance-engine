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

export type CapturedPanel = {
  panel: "FRONT" | "BACK" | "SIDE_1" | "SIDE_2";
  uri: string;
  source: "CAMERA" | "GALLERY";
};

export type Draft = {
  clientUuid: string;
  capturedAt: string;
  category: string;
  buyerType: "RETAIL" | "INDUSTRIAL" | "INSTITUTIONAL";
  packageShape: "RECTANGULAR" | "CYLINDRICAL" | "IRREGULAR";
  coverageAsserted: boolean;
  panels: CapturedPanel[];
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
