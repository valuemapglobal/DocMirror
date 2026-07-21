/**
 * DocMirror TypeScript SDK
 *
 * Typed client for the DocMirror Universal Document Parsing API.
 *
 * @example
 * ```typescript
 * import { DocMirrorClient } from "@docmirror/sdk";
 *
 * const client = new DocMirrorClient({
 *   baseUrl: "http://localhost:8000",
 *   apiKey: "sk-...",
 * });
 *
 * const result = await client.parseDocument("statement.pdf");
 * console.log(result.data?.document?.pages?.[0]?.tables);
 * ```
 *
 * @module @docmirror/sdk
 */

export { DocMirrorClient, DocMirrorApiError } from "./client.js";
export type { DocMirrorClientConfig } from "./client.js";
export type {
  // Response
  ParseResponse,
  ParseResultData,
  ApiError,
  // Document
  DocumentSection,
  PageSection,
  TextBlock,
  TableBlock,
  DataRow,
  CellValue,
  KeyValuePair,
  // Quality
  QualitySection,
  // Evidence
  EvidenceSection,
  EvidenceEntry,
  // Health
  HealthResponse,
  // Options
  ParseOptions,
  // Community Bundle 3.0
  CommunityBundle,
  CommunitySchema,
  CommunityDataset,
  CommunityColumn,
  CommunityCompleteness,
  CommunityRecord,
} from "./types.js";
