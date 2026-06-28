// DocMirror Go SDK — Type Definitions
//
// Auto-generated from OpenAPI spec at docs/openapi/openapi.json.
// DMIR (DocMirror Intermediate Representation) schema v1.0.

package docmirror

import "time"

// ── Top-Level Response ──

// ParseResponse is the top-level API response envelope.
type ParseResponse struct {
	Code        int                `json:"code"`
	Message     string             `json:"message"`
	APIVersion  string             `json:"api_version"`
	RequestID   string             `json:"request_id"`
	Timestamp   time.Time          `json:"timestamp"`
	Data        *ParseResultData   `json:"data,omitempty"`
	Error       *APIError          `json:"error,omitempty"`
	Meta        map[string]any     `json:"meta,omitempty"`
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
	PageNumber int             `json:"page_number"`
	WidthPt    float64         `json:"width_pt"`
	HeightPt   float64         `json:"height_pt"`
	Texts      []TextBlock     `json:"texts,omitempty"`
	Tables     []TableBlock    `json:"tables,omitempty"`
	KeyValues  []KeyValuePair  `json:"key_values,omitempty"`
}

type TextBlock struct {
	Content      string `json:"content"`
	Level        string `json:"level"`
	ReadingOrder int    `json:"reading_order"`
}

type TableBlock struct {
	TableID string    `json:"table_id"`
	Headers []string  `json:"headers,omitempty"`
	DataRows []DataRow `json:"data_rows,omitempty"`
	Method  string    `json:"method,omitempty"`
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
	Status       string  `json:"status"`
	Version      string  `json:"version"`
	Timestamp    string  `json:"timestamp"`
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
