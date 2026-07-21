// DocMirror Go SDK — Type Definitions
//
// Auto-generated from OpenAPI spec at docs/openapi/openapi.json.
// DMIR (DocMirror Intermediate Representation) schema v1.0.

package docmirror

import "time"

// ── Top-Level Response ──

// ParseResponse is the top-level API response envelope.
type ParseResponse struct {
	Code       int              `json:"code"`
	Message    string           `json:"message"`
	APIVersion string           `json:"api_version"`
	RequestID  string           `json:"request_id"`
	Timestamp  time.Time        `json:"timestamp"`
	Data       *ParseResultData `json:"data,omitempty"`
	Error      *APIError        `json:"error,omitempty"`
	Meta       map[string]any   `json:"meta,omitempty"`
}

// ParseResultData is the DMIR business payload.
type ParseResultData struct {
	DMIRVersion string           `json:"dmir_version"`
	Document    *DocumentSection `json:"document,omitempty"`
	Quality     *QualitySection  `json:"quality,omitempty"`
	Evidence    *EvidenceSection `json:"evidence,omitempty"`
}

// APIError contains error details.
type APIError struct {
	Type   string `json:"type"`
	Detail string `json:"detail"`
}

// ── Document Section ──

type DocumentSection struct {
	Type       string            `json:"type,omitempty"`
	Properties map[string]string `json:"properties,omitempty"`
	Pages      []PageSection     `json:"pages,omitempty"`
	FullText   string            `json:"full_text,omitempty"`
}

type PageSection struct {
	PageNumber int            `json:"page_number"`
	WidthPt    float64        `json:"width_pt"`
	HeightPt   float64        `json:"height_pt"`
	Texts      []TextBlock    `json:"texts,omitempty"`
	Tables     []TableBlock   `json:"tables,omitempty"`
	KeyValues  []KeyValuePair `json:"key_values,omitempty"`
}

type TextBlock struct {
	Content      string `json:"content"`
	Level        string `json:"level"`
	ReadingOrder int    `json:"reading_order"`
}

type TableBlock struct {
	TableID  string    `json:"table_id"`
	Headers  []string  `json:"headers,omitempty"`
	DataRows []DataRow `json:"data_rows,omitempty"`
	Method   string    `json:"method,omitempty"`
}

type DataRow struct {
	Cells   []CellValue `json:"cells,omitempty"`
	RowType string      `json:"row_type,omitempty"`
}

type CellValue struct {
	Text     string `json:"text,omitempty"`
	DataType string `json:"data_type,omitempty"`
}

type KeyValuePair struct {
	Key     string `json:"key"`
	Value   string `json:"value"`
	GroupID string `json:"group_id,omitempty"`
}

// ── Quality Section ──

type QualitySection struct {
	Confidence       float64  `json:"confidence"`
	TrustScore       float64  `json:"trust_score"`
	ValidationPassed bool     `json:"validation_passed"`
	Warnings         []string `json:"warnings,omitempty"`
}

// ── Evidence Section ──

type EvidenceSection struct {
	Ledger map[string]EvidenceEntry `json:"ledger,omitempty"`
}

type EvidenceEntry struct {
	Type       string  `json:"type"`
	Confidence float64 `json:"confidence"`
	Method     string  `json:"method"`
}

// ── Health Response ──

type HealthResponse struct {
	Status        string  `json:"status"`
	Version       string  `json:"version"`
	Timestamp     string  `json:"timestamp"`
	UptimeSeconds float64 `json:"uptime_seconds,omitempty"`
}

// ── Parse Options ──

type ParseOptions struct {
	Mode            string `json:"mode,omitempty"`
	Edition         string `json:"edition,omitempty"`
	Pages           string `json:"pages,omitempty"`
	MaxPages        int    `json:"max_pages,omitempty"`
	Workers         string `json:"workers,omitempty"`
	IncludeText     bool   `json:"include_text,omitempty"`
	IncludeGeometry bool   `json:"include_geometry,omitempty"`
	Format          string `json:"format,omitempty"`
	DocTypeHint     string `json:"doc_type_hint,omitempty"`
}

// ── Community Bundle 3.0 ──

// CommunityBundle is the self-contained Community structured API response.
type CommunityBundle struct {
	Schema   CommunitySchema        `json:"schema"`
	Document map[string]any         `json:"document"`
	Sections []map[string]any       `json:"sections"`
	Datasets []CommunityDataset     `json:"datasets"`
	Files    map[string]string      `json:"files"`
	Warnings []map[string]any       `json:"warnings"`
}

type CommunitySchema struct {
	Name         string `json:"name"`
	Version      string `json:"version"`
	Edition      string `json:"edition"`
	Domain       string `json:"domain"`
	SupportLevel string `json:"support_level"`
}

type CommunityDataset struct {
	ID            string                `json:"id"`
	Name          string                `json:"name"`
	Label         string                `json:"label"`
	Type          string                `json:"type"`
	SectionID     string                `json:"section_id"`
	CSV           string                `json:"csv"`
	RowCount      int                   `json:"row_count"`
	Grain         string                `json:"grain"`
	PrimaryKey    string                `json:"primary_key"`
	SchemaVersion string               `json:"schema_version"`
	Status        string                `json:"status"`
	Columns       []CommunityColumn     `json:"columns"`
	Completeness CommunityCompleteness `json:"completeness"`
	Rows          []CommunityRecord     `json:"rows"`
}

type CommunityColumn struct {
	Key               string `json:"key"`
	Label             string `json:"label"`
	Type              string `json:"type"`
	Unit              string `json:"unit,omitempty"`
	Nullable          bool   `json:"nullable"`
	RawAvailable      bool   `json:"raw_available"`
	EvidenceAvailable bool   `json:"evidence_available"`
}

type CommunityCompleteness struct {
	ExpectedRowCount int    `json:"expected_row_count"`
	EmittedRowCount  int    `json:"emitted_row_count"`
	OmittedRowCount  int    `json:"omitted_row_count"`
	Verified         bool   `json:"verified"`
	Basis            string `json:"basis"`
}

type CommunityRecord struct {
	RecordID     string         `json:"record_id"`
	Normalized   map[string]any `json:"normalized"`
	CanonicalRaw map[string]any `json:"canonical_raw"`
	Raw          map[string]any `json:"raw"`
	Source       map[string]any `json:"source"`
	Confidence   any            `json:"confidence,omitempty"`
	Review       map[string]any `json:"review,omitempty"`
}
