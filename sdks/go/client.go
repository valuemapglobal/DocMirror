// DocMirror Go SDK — Client
//
// Typed HTTP client for the DocMirror Universal Document Parsing API.
// Supports file upload, batch processing, and health checks.
//
// Usage:
//
//	client := docmirror.NewClient("http://localhost:8000", "sk-...")
//	result, err := client.ParseDocument("statement.pdf", nil)
//	if err != nil { log.Fatal(err) }
//	fmt.Printf("Document type: %s\n", result.Data.Document.Type)

package docmirror

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"time"
)

// ── Constants ──

const (
	DefaultBaseURL = "http://localhost:8000"
	DefaultTimeout = 120 * time.Second
	Version        = "0.2.0"
)

// ── Client ──

// Client is a typed HTTP client for the DocMirror API.
type Client struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

// NewClient creates a new DocMirror API client.
func NewClient(baseURL, apiKey string) *Client {
	if baseURL == "" {
		baseURL = DefaultBaseURL
	}
	return &Client{
		baseURL: baseURL,
		apiKey:  apiKey,
		httpClient: &http.Client{
			Timeout: DefaultTimeout,
		},
	}
}

// NewClientWithHTTP creates a new client with a custom HTTP client.
func NewClientWithHTTP(baseURL, apiKey string, httpClient *http.Client) *Client {
	c := NewClient(baseURL, apiKey)
	c.httpClient = httpClient
	return c
}

// ── Public Methods ──

// ParseDocument uploads and parses a single document file.
func (c *Client) ParseDocument(filePath string, opts *ParseOptions) (*ParseResponse, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("docmirror: cannot open file %s: %w", filePath, err)
	}
	defer file.Close()

	var buf bytes.Buffer
	w := multipart.NewWriter(&buf)

	// File field
	part, err := w.CreateFormFile("file", filepath.Base(filePath))
	if err != nil {
		return nil, fmt.Errorf("docmirror: failed to create form file: %w", err)
	}
	if _, err := io.Copy(part, file); err != nil {
		return nil, fmt.Errorf("docmirror: failed to copy file: %w", err)
	}

	// Mode field
	if opts != nil && opts.Mode != "" {
		if err := w.WriteField("mode", opts.Mode); err != nil {
			return nil, fmt.Errorf("docmirror: failed to write mode field: %w", err)
		}
	}
	w.Close()

	u, _ := url.Parse(c.baseURL + "/v1/parse")
	c.addQueryParams(u, opts)

	req, err := http.NewRequest("POST", u.String(), &buf)
	if err != nil {
		return nil, fmt.Errorf("docmirror: failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", w.FormDataContentType())
	c.setAuthHeader(req)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("docmirror: request failed: %w", err)
	}
	defer resp.Body.Close()

	return c.decodeResponse(resp)
}

// ParseDocumentBatch uploads and parses multiple documents in batch.
func (c *Client) ParseDocumentBatch(filePaths []string, opts *ParseOptions) (*ParseResponse, error) {
	var buf bytes.Buffer
	w := multipart.NewWriter(&buf)

	for _, fp := range filePaths {
		file, err := os.Open(fp)
		if err != nil {
			return nil, fmt.Errorf("docmirror: cannot open file %s: %w", fp, err)
		}
		defer file.Close()

		part, err := w.CreateFormFile("files", filepath.Base(fp))
		if err != nil {
			return nil, fmt.Errorf("docmirror: failed to create form file: %w", err)
		}
		if _, err := io.Copy(part, file); err != nil {
			return nil, fmt.Errorf("docmirror: failed to copy file: %w", err)
		}
	}

	if opts != nil && opts.Mode != "" {
		if err := w.WriteField("mode", opts.Mode); err != nil {
			return nil, fmt.Errorf("docmirror: failed to write mode: %w", err)
		}
	}
	w.Close()

	u, _ := url.Parse(c.baseURL + "/v1/parse/batch")
	c.addQueryParams(u, opts)
	// Batch endpoint doesn't use all query params
	q := u.Query()
	q.Del("include_text")
	q.Del("format")
	u.RawQuery = q.Encode()

	req, err := http.NewRequest("POST", u.String(), &buf)
	if err != nil {
		return nil, fmt.Errorf("docmirror: failed to create batch request: %w", err)
	}
	req.Header.Set("Content-Type", w.FormDataContentType())
	c.setAuthHeader(req)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("docmirror: batch request failed: %w", err)
	}
	defer resp.Body.Close()

	return c.decodeResponse(resp)
}

// ParseFileOnServer parses a file already present on the DocMirror server.
func (c *Client) ParseFileOnServer(serverPath string, opts *ParseOptions) (*ParseResponse, error) {
	body := map[string]string{"path": serverPath}
	bodyBytes, _ := json.Marshal(body)

	u, _ := url.Parse(c.baseURL + "/v1/parse/file")
	c.addQueryParams(u, opts)

	req, err := http.NewRequest("POST", u.String(), bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, fmt.Errorf("docmirror: failed to create server-parse request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	c.setAuthHeader(req)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("docmirror: server-parse request failed: %w", err)
	}
	defer resp.Body.Close()

	return c.decodeResponse(resp)
}

// Health checks the DocMirror API health.
func (c *Client) Health() (*HealthResponse, error) {
	req, err := http.NewRequest("GET", c.baseURL+"/health", nil)
	if err != nil {
		return nil, fmt.Errorf("docmirror: failed to create health request: %w", err)
	}
	c.setAuthHeader(req)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("docmirror: health check failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("docmirror: health check returned HTTP %d: %s", resp.StatusCode, string(body))
	}

	var health HealthResponse
	if err := json.NewDecoder(resp.Body).Decode(&health); err != nil {
		return nil, fmt.Errorf("docmirror: failed to decode health response: %w", err)
	}
	return &health, nil
}

// ── Internal Helpers ──

func (c *Client) addQueryParams(u *url.URL, opts *ParseOptions) {
	if opts == nil {
		return
	}
	q := u.Query()
	if opts.Mode != "" {
		q.Set("mode", opts.Mode)
	}
	if opts.Edition != "" {
		q.Set("edition", opts.Edition)
	}
	if opts.Pages != "" {
		q.Set("pages", opts.Pages)
	}
	if opts.MaxPages > 0 {
		q.Set("max_pages", fmt.Sprintf("%d", opts.MaxPages))
	}
	if opts.Workers != "" {
		q.Set("workers", opts.Workers)
	}
	if opts.IncludeText {
		q.Set("include_text", "true")
	}
	if opts.IncludeGeometry {
		q.Set("include_geometry", "true")
	}
	if opts.Format != "" {
		q.Set("format", opts.Format)
	}
	if opts.DocTypeHint != "" {
		q.Set("doc_type_hint", opts.DocTypeHint)
	}
	u.RawQuery = q.Encode()
}

func (c *Client) setAuthHeader(req *http.Request) {
	if c.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.apiKey)
	}
}

func (c *Client) decodeResponse(resp *http.Response) (*ParseResponse, error) {
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("docmirror: failed to read response: %w", err)
	}

	var result ParseResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("docmirror: failed to decode response: %w", err)
	}

	if !c.isSuccess(resp.StatusCode) {
		errMsg := result.Error.Detail
		if errMsg == "" {
			errMsg = result.Message
		}
		return &result, fmt.Errorf("docmirror: API error (HTTP %d): %s", resp.StatusCode, errMsg)
	}

	return &result, nil
}

func (c *Client) isSuccess(code int) bool {
	return code >= 200 && code < 300
}
