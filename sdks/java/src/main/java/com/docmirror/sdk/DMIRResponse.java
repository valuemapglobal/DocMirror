package com.docmirror.sdk;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

/**
 * Top-level DocMirror API response — DMIR (DocMirror Intermediate Representation).
 * Auto-generated from OpenAPI spec. Fields match dmir_version "1.0".
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class DMIRResponse {

    @JsonProperty("dmir_version")
    private String dmirVersion;

    @JsonProperty("document")
    private DocumentSection document;

    @JsonProperty("quality")
    private QualitySection quality;

    @JsonProperty("evidence")
    private EvidenceSection evidence;

    @JsonProperty("meta")
    private MetaSection meta;

    // ── Getters ──

    public String getDmirVersion() { return dmirVersion; }
    public DocumentSection getDocument() { return document; }
    public QualitySection getQuality() { return quality; }
    public EvidenceSection getEvidence() { return evidence; }
    public MetaSection getMeta() { return meta; }

    // ── Nested Types ──

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class DocumentSection {
        @JsonProperty("type")
        private String type;

        @JsonProperty("properties")
        private Map<String, String> properties;

        @JsonProperty("pages")
        private List<PageSection> pages;

        @JsonProperty("full_text")
        private String fullText;

        public String getType() { return type; }
        public Map<String, String> getProperties() { return properties; }
        public List<PageSection> getPages() { return pages; }
        public String getFullText() { return fullText; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class PageSection {
        @JsonProperty("page_number")
        private int pageNumber;

        @JsonProperty("width_pt")
        private double widthPt;

        @JsonProperty("height_pt")
        private double heightPt;

        @JsonProperty("texts")
        private List<TextBlock> texts;

        @JsonProperty("tables")
        private List<TableBlock> tables;

        @JsonProperty("key_values")
        private List<KeyValuePair> keyValues;

        public int getPageNumber() { return pageNumber; }
        public double getWidthPt() { return widthPt; }
        public double getHeightPt() { return heightPt; }
        public List<TextBlock> getTexts() { return texts; }
        public List<TableBlock> getTables() { return tables; }
        public List<KeyValuePair> getKeyValues() { return keyValues; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class TextBlock {
        @JsonProperty("content")
        private String content;

        @JsonProperty("level")
        private String level;

        @JsonProperty("reading_order")
        private int readingOrder;

        public String getContent() { return content; }
        public String getLevel() { return level; }
        public int getReadingOrder() { return readingOrder; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class TableBlock {
        @JsonProperty("table_id")
        private String tableId;

        @JsonProperty("headers")
        private List<String> headers;

        @JsonProperty("data_rows")
        private List<DataRow> dataRows;

        @JsonProperty("method")
        private String method;

        public String getTableId() { return tableId; }
        public List<String> getHeaders() { return headers; }
        public List<DataRow> getDataRows() { return dataRows; }
        public String getMethod() { return method; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class DataRow {
        @JsonProperty("cells")
        private List<CellValue> cells;

        @JsonProperty("row_type")
        private String rowType;

        public List<CellValue> getCells() { return cells; }
        public String getRowType() { return rowType; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class CellValue {
        @JsonProperty("text")
        private String text;

        @JsonProperty("data_type")
        private String dataType;

        public String getText() { return text; }
        public String getDataType() { return dataType; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class KeyValuePair {
        @JsonProperty("key")
        private String key;

        @JsonProperty("value")
        private String value;

        @JsonProperty("group_id")
        private String groupId;

        public String getKey() { return key; }
        public String getValue() { return value; }
        public String getGroupId() { return groupId; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class QualitySection {
        @JsonProperty("confidence")
        private double confidence;

        @JsonProperty("trust_score")
        private double trustScore;

        @JsonProperty("validation_passed")
        private boolean validationPassed;

        @JsonProperty("warnings")
        private List<String> warnings;

        public double getConfidence() { return confidence; }
        public double getTrustScore() { return trustScore; }
        public boolean isValidationPassed() { return validationPassed; }
        public List<String> getWarnings() { return warnings; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class EvidenceSection {
        @JsonProperty("ledger")
        private Map<String, EvidenceEntry> ledger;

        public Map<String, EvidenceEntry> getLedger() { return ledger; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class EvidenceEntry {
        @JsonProperty("type")
        private String type;

        @JsonProperty("confidence")
        private double confidence;

        @JsonProperty("method")
        private String method;

        public String getType() { return type; }
        public double getConfidence() { return confidence; }
        public String getMethod() { return method; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class MetaSection {
        @JsonProperty("parser")
        private String parser;

        @JsonProperty("version")
        private String version;

        @JsonProperty("elapsed_ms")
        private double elapsedMs;

        @JsonProperty("page_count")
        private int pageCount;

        @JsonProperty("table_count")
        private int tableCount;

        @JsonProperty("row_count")
        private int rowCount;

        @JsonProperty("dmir_version")
        private String dmirVersion;

        public String getParser() { return parser; }
        public String getVersion() { return version; }
        public double getElapsedMs() { return elapsedMs; }
        public int getPageCount() { return pageCount; }
        public int getTableCount() { return tableCount; }
        public int getRowCount() { return rowCount; }
        public String getDmirVersion() { return dmirVersion; }
    }
}
