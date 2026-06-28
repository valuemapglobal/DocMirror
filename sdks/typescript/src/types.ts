/**
 * DocMirror TypeScript SDK — Type Definitions
 *
 * Auto-generated from OpenAPI spec at docs/openapi/openapi.json.
 * DMIR (DocMirror Intermediate Representation) schema v1.0.
 *
 * @module @docmirror/sdk
 */

// ── Top-Level Response ──

/** API response envelope */
export interface ParseResponse {
  /** HTTP status code (200 or 422) */
  code: number;
  /** 'success' or 'error' */
  message: string;
  /** API version string */
  api_version: string;
  /** Request tracing ID (UUID) */
  request_id: string;
  /** ISO 8601 UTC response time */
  timestamp: string;
  /** Business payload — present on success */
  data?: ParseResultData | null;
  /** Error details — present on failure */
  error?: ApiError | null;
  /** Parser diagnostics and provenance */
  meta?: Record<string, unknown> | null;
}

/** DMIR payload */
export interface ParseResultData {
  /** DMIR schema version */
  dmir_version: string;
  /** Document-level section */
  document?: DocumentSection | null;
  /** Quality metrics */
  quality?: QualitySection | null;
  /** Evidence provenance ledger */
  evidence?: EvidenceSection | null;
}

/** Error details */
export interface ApiError {
  type: string;
  detail: string;
  [key: string]: unknown;
}

// ── Document Section ──

export interface DocumentSection {
  /** Classified document type (bank_statement, invoice, etc.) */
  type?: string | null;
  /** Document-level key-value properties */
  properties?: Record<string, string> | null;
  /** Page contents */
  pages?: PageSection[] | null;
  /** Full concatenated text of all pages */
  full_text?: string | null;
}

export interface PageSection {
  /** 1-based page number */
  page_number: number;
  /** Page width in points (1/72 inch) */
  width_pt: number;
  /** Page height in points */
  height_pt: number;
  /** Text blocks in reading order */
  texts?: TextBlock[] | null;
  /** Extracted tables */
  tables?: TableBlock[] | null;
  /** Extracted key-value pairs */
  key_values?: KeyValuePair[] | null;
}

export interface TextBlock {
  /** Text content */
  content: string;
  /** Structural level: h1-h6, p, li, caption, footnote */
  level: string;
  /** Reading order position (0-based) */
  reading_order: number;
}

export interface TableBlock {
  /** Unique table ID */
  table_id: string;
  /** Column headers */
  headers?: string[] | null;
  /** Data rows */
  data_rows?: DataRow[] | null;
  /** Extraction method: "lattice", "stream", "hybrid", "heuristic" */
  method?: string | null;
}

export interface DataRow {
  /** Cell values */
  cells?: CellValue[] | null;
  /** Row type: "header", "data", "subtotal", "total", "blank" */
  row_type?: string | null;
}

export interface CellValue {
  /** Cell text content */
  text?: string | null;
  /** Inferred data type: "text", "number", "date", "money", "percentage", "empty" */
  data_type?: string | null;
}

export interface KeyValuePair {
  /** Key field name */
  key: string;
  /** Extracted value */
  value: string;
  /** Logical grouping ID */
  group_id?: string | null;
}

// ── Quality Section ──

export interface QualitySection {
  /** Overall parse confidence (0-1) */
  confidence: number;
  /** Trust score considering warnings and evidence */
  trust_score: number;
  /** Whether all quality gates passed */
  validation_passed: boolean;
  /** Quality warnings */
  warnings?: string[] | null;
}

// ── Evidence Section ──

export interface EvidenceSection {
  /** Evidence ledger entries keyed by evidence ID */
  ledger?: Record<string, EvidenceEntry> | null;
}

export interface EvidenceEntry {
  /** Evidence type: "bbox", "ocr_confidence", "page_canvas", "heuristic", etc. */
  type: string;
  /** Confidence of this evidence (0-1) */
  confidence: number;
  /** Extraction method that produced this evidence */
  method: string;
}

// ── Health ──

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
  uptime_seconds?: number | null;
}

// ── Parse Options ──

export interface ParseOptions {
  /** Parse mode: "auto", "fast", "balanced", "accurate", "forensic" */
  mode?: string;
  /** Output edition: "community", "enterprise", "finance", or "all" */
  edition?: string;
  /** Page ranges, 1-based: "1-3,8,10-" */
  pages?: string;
  /** Maximum pages after applying pages filter */
  max_pages?: number;
  /** Total worker budget */
  workers?: number | string;
  /** Include full markdown text in response */
  include_text?: boolean;
  /** Include table/cell geometry */
  include_geometry?: boolean;
  /** Requested output formats */
  format?: string;
  /** Manual document type hint */
  doc_type_hint?: string;
  /** API key (overrides constructor key) */
  api_key?: string;
}
