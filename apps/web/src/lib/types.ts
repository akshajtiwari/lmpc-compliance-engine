export type Principal = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  jurisdiction: string | null;
  is_legal_reviewer: boolean;
  permissions: string[];
};

export type ScanSummary = {
  id: string;
  client_uuid: string;
  captured_at: string;
  created_at: string;
  mode: string;
  category: string;
  status: string;
  overall: string | null;
  coverage_asserted: boolean;
  officer_id: string;
  jurisdiction_id: string;
  brand: string | null;
  manufacturer: string | null;
};

export type Declaration = {
  id: string;
  field: string;
  text: string;
  confidence: number;
  panel: string;
  corrected_by?: string | null;
};

export type Evaluation = {
  id: string;
  check: string;
  clause: string;
  outcome: string;
  reason: string;
  citation?: Record<string, unknown>;
  evidence?: Record<string, unknown>;
  is_override?: boolean;
};

export type Scan = {
  scan_id: string;
  client_uuid: string;
  captured_at: string;
  mode: string;
  category: string;
  status: string;
  overall: string | null;
  coverage_asserted: boolean;
  officer_id: string;
  jurisdiction_id: string;
  buyer_type: string;
  package_shape: string;
  panels_captured: string[];
  decision_explanation: {
    heading: string;
    summary: string;
    next_step: string;
    processing_stage: string;
    ocr_ran: boolean;
  } | null;
  images: Array<{ panel: string; url: string; sha256: string; width: number; height: number }>;
  declarations: Declaration[];
  evaluations: Evaluation[];
};

export type UserAccount = {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  role: string;
  jurisdiction_id: string | null;
  department: string | null;
  is_active: boolean;
  is_legal_reviewer: boolean;
  last_login_at: string | null;
  created_at: string | null;
};

export type Enrollment = {
  enrollment_id: string;
  user: UserAccount;
  server_url: string;
  server_fingerprint: string;
  token: string;
  expires_at: string;
  enrollment_uri: string;
};

export type RuleDetail = {
  check: string;
  title: string;
  clause: string;
  requirement: string;
  method: string;
  evidence_needed: string;
  effective_from: string | null;
  authority: Record<string, unknown>;
  important_limits: string[];
  outcomes: Record<string, string>;
  non_normative_notice: string;
};
