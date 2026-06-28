/**
 * DocMirror TypeScript SDK — Client
 *
 * Typed HTTP client for the DocMirror Universal Document Parsing API.
 * Supports Node.js 18+ (native fetch) and modern browsers.
 *
 * @module @docmirror/sdk
 */

import {
  type ParseOptions,
  type ParseResponse,
  type HealthResponse,
} from "./types.js";

// ── Defaults ──

const DEFAULT_BASE_URL = "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 120_000;

// ── Client Configuration ──

export interface DocMirrorClientConfig {
  /** API base URL (default: http://localhost:8000) */
  baseUrl?: string;
  /** API key for Bearer auth */
  apiKey?: string;
  /** Request timeout in milliseconds (default: 120000) */
  timeoutMs?: number;
  /** Custom fetch implementation (for environments without global fetch) */
  fetch?: typeof globalThis.fetch;
}

// ── Client ──

/**
 * Typed client for the DocMirror API.
 *
 * @example
 * ```typescript
 * import { DocMirrorClient } from "@docmirror/sdk";
 *
 * const client = new DocMirrorClient({ apiKey: "sk-..." });
 * const result = await client.parseDocument("statement.pdf");
 * console.log(result.data?.document?.pages);
 * ```
 */
export class DocMirrorClient {
  private readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly timeoutMs: number;
  private readonly fetchFn: typeof globalThis.fetch;

  constructor(config: DocMirrorClientConfig = {}) {
    this.baseUrl = (config.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.apiKey = config.apiKey;
    this.timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.fetchFn = config.fetch ?? globalThis.fetch;
  }

  // ── Public API ──

  /**
   * Parse a single document file.
   *
   * @param filePath  Path to the document (Node.js) or File/Blob (browser)
   * @param options   Optional parse parameters
   * @returns         Typed DMIR response
   */
  async parseDocument(
    filePath: string | File | Blob,
    options?: ParseOptions,
  ): Promise<ParseResponse> {
    const formData = await this._buildFileFormData(filePath, options);
    return this._request("POST", "/v1/parse", formData);
  }

  /**
   * Parse multiple documents in batch.
   *
   * @param filePaths  Array of paths (Node.js) or File/Blob objects (browser)
   * @param options    Optional parse parameters
   * @returns          Array of DMIR responses
   */
  async parseDocumentBatch(
    filePaths: (string | File | Blob)[],
    options?: ParseOptions,
  ): Promise<ParseResponse[]> {
    const formData = await this._buildBatchFormData(filePaths, options);
    return this._request("POST", "/v1/parse/batch", formData);
  }

  /**
   * Parse a file already present on the server filesystem.
   *
   * @param serverPath  Absolute path to the file on the server
   * @param options     Optional parse parameters
   * @returns           Typed DMIR response
   */
  async parseFileOnServer(
    serverPath: string,
    options?: ParseOptions,
  ): Promise<ParseResponse> {
    const body = JSON.stringify({ path: serverPath });
    const url = this._buildUrl("/v1/parse/file", options);
    return this._requestRaw("POST", url, body, {
      "Content-Type": "application/json",
    });
  }

  /**
   * Check API health.
   */
  async health(): Promise<HealthResponse> {
    return this._request("GET", "/health");
  }

  // ── Internal Helpers ──

  private _buildUrl(
    path: string,
    options?: ParseOptions,
  ): string {
    const url = new URL(`${this.baseUrl}${path}`);
    if (options) {
      if (options.mode) url.searchParams.set("mode", options.mode);
      if (options.edition) url.searchParams.set("edition", options.edition);
      if (options.pages) url.searchParams.set("pages", options.pages);
      if (options.max_pages !== undefined) url.searchParams.set("max_pages", String(options.max_pages));
      if (options.workers !== undefined) url.searchParams.set("workers", String(options.workers));
      if (options.include_text !== undefined) url.searchParams.set("include_text", String(options.include_text));
      if (options.include_geometry !== undefined) url.searchParams.set("include_geometry", String(options.include_geometry));
      if (options.format) url.searchParams.set("format", options.format);
      if (options.doc_type_hint) url.searchParams.set("doc_type_hint", options.doc_type_hint);
    }
    return url.toString();
  }

  private async _buildFileFormData(
    file: string | File | Blob,
    options?: ParseOptions,
  ): Promise<FormData> {
    const fd = new FormData();
    const blob = await this._resolveFile(file);
    const fileName = typeof file === "string"
      ? file.split("/").pop() ?? "document"
      : file instanceof File ? file.name : "document.bin";
    fd.append("file", blob, fileName);
    if (options?.mode) fd.append("mode", options.mode);
    return fd;
  }

  private async _buildBatchFormData(
    files: (string | File | Blob)[],
    options?: ParseOptions,
  ): Promise<FormData> {
    const fd = new FormData();
    for (const file of files) {
      const blob = await this._resolveFile(file);
      const fileName = typeof file === "string"
        ? file.split("/").pop() ?? "document"
        : file instanceof File ? file.name : "document.bin";
      fd.append("files", blob, fileName);
    }
    if (options?.mode) fd.append("mode", options.mode);
    return fd;
  }

  private async _resolveFile(file: string | File | Blob): Promise<Blob> {
    if (file instanceof Blob) return file;
    // Node.js: read file and convert to Blob
    if (typeof process !== "undefined" && process.versions?.node) {
      const { readFile } = await import("node:fs/promises");
      const buffer = await readFile(file);
      return new Blob([buffer]);
    }
    throw new Error(
      "File path resolution is only supported in Node.js. " +
      "In browser environments, pass a File or Blob object directly.",
    );
  }

  private _buildHeaders(contentType?: string): Record<string, string> {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (contentType) {
      headers["Content-Type"] = contentType;
    }
    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }
    return headers;
  }

  private async _request<T>(
    method: string,
    path: string,
    body?: FormData | string,
  ): Promise<T> {
    const isFormData = body instanceof FormData;
    const url = isFormData
      ? `${this.baseUrl}${path}`
      : this._buildUrl(path);
    const headers = this._buildHeaders(
      isFormData ? undefined : "application/json",
    );

    return this._requestRaw(method, url, body, headers);
  }

  private async _requestRaw<T>(
    method: string,
    url: string,
    body?: BodyInit | null,
    headers?: Record<string, string>,
  ): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await this.fetchFn(url, {
        method,
        headers,
        body: body ?? null,
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorBody = await response.text();
        let parsed: ParseResponse | null = null;
        try {
          parsed = JSON.parse(errorBody) as ParseResponse;
        } catch {
          // ignore parse failure
        }
        throw new DocMirrorApiError(
          response.status,
          parsed?.error?.detail ?? parsed?.message ?? errorBody,
          parsed ?? undefined,
        );
      }

      const json = (await response.json()) as T;
      return json;
    } catch (error) {
      if (error instanceof DocMirrorApiError) throw error;
      if ((error as Error).name === "AbortError") {
        throw new DocMirrorApiError(
          0,
          `Request timed out after ${this.timeoutMs}ms`,
        );
      }
      throw new DocMirrorApiError(0, (error as Error).message);
    } finally {
      clearTimeout(timer);
    }
  }
}

// ── Error Type ──

/**
 * Typed error for DocMirror API failures.
 * Includes the HTTP status code and optionally the parsed response body.
 */
export class DocMirrorApiError extends Error {
  /** HTTP status code (0 for network errors) */
  public readonly statusCode: number;
  /** Parsed API response, if available */
  public readonly response?: ParseResponse;

  constructor(statusCode: number, message: string, response?: ParseResponse) {
    super(message);
    this.name = "DocMirrorApiError";
    this.statusCode = statusCode;
    this.response = response;
  }
}
