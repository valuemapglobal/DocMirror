package com.docmirror.sdk;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

/** Self-contained Community Bundle 3.0 structured API response. */
@JsonIgnoreProperties(ignoreUnknown = true)
public class CommunityBundle {
    private Schema schema;
    private Map<String, Object> document;
    private List<Map<String, Object>> sections;
    private List<Dataset> datasets;
    private Map<String, String> files;
    private List<Map<String, Object>> warnings;

    public Schema getSchema() { return schema; }
    public Map<String, Object> getDocument() { return document; }
    public List<Map<String, Object>> getSections() { return sections; }
    public List<Dataset> getDatasets() { return datasets; }
    public Map<String, String> getFiles() { return files; }
    public List<Map<String, Object>> getWarnings() { return warnings; }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Schema {
        private String name;
        private String version;
        private String edition;
        private String domain;
        @JsonProperty("support_level") private String supportLevel;

        public String getName() { return name; }
        public String getVersion() { return version; }
        public String getEdition() { return edition; }
        public String getDomain() { return domain; }
        public String getSupportLevel() { return supportLevel; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Dataset {
        private String id;
        private String name;
        private String label;
        private String type;
        @JsonProperty("section_id") private String sectionId;
        private String csv;
        @JsonProperty("row_count") private int rowCount;
        private String grain;
        @JsonProperty("primary_key") private String primaryKey;
        @JsonProperty("schema_version") private String schemaVersion;
        private String status;
        private List<Column> columns;
        private Completeness completeness;
        private List<Record> rows;

        public String getId() { return id; }
        public String getName() { return name; }
        public String getLabel() { return label; }
        public String getType() { return type; }
        public String getSectionId() { return sectionId; }
        public String getCsv() { return csv; }
        public int getRowCount() { return rowCount; }
        public String getGrain() { return grain; }
        public String getPrimaryKey() { return primaryKey; }
        public String getSchemaVersion() { return schemaVersion; }
        public String getStatus() { return status; }
        public List<Column> getColumns() { return columns; }
        public Completeness getCompleteness() { return completeness; }
        public List<Record> getRows() { return rows; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Column {
        private String key;
        private String label;
        private String type;
        private String unit;
        private boolean nullable;
        @JsonProperty("raw_available") private boolean rawAvailable;
        @JsonProperty("evidence_available") private boolean evidenceAvailable;

        public String getKey() { return key; }
        public String getLabel() { return label; }
        public String getType() { return type; }
        public String getUnit() { return unit; }
        public boolean isNullable() { return nullable; }
        public boolean isRawAvailable() { return rawAvailable; }
        public boolean isEvidenceAvailable() { return evidenceAvailable; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Completeness {
        @JsonProperty("expected_row_count") private int expectedRowCount;
        @JsonProperty("emitted_row_count") private int emittedRowCount;
        @JsonProperty("omitted_row_count") private int omittedRowCount;
        private boolean verified;
        private String basis;

        public int getExpectedRowCount() { return expectedRowCount; }
        public int getEmittedRowCount() { return emittedRowCount; }
        public int getOmittedRowCount() { return omittedRowCount; }
        public boolean isVerified() { return verified; }
        public String getBasis() { return basis; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Record {
        @JsonProperty("record_id") private String recordId;
        private Map<String, Object> normalized;
        @JsonProperty("canonical_raw") private Map<String, Object> canonicalRaw;
        private Map<String, Object> raw;
        private Map<String, Object> source;
        private Object confidence;
        private Map<String, Object> review;

        public String getRecordId() { return recordId; }
        public Map<String, Object> getNormalized() { return normalized; }
        public Map<String, Object> getCanonicalRaw() { return canonicalRaw; }
        public Map<String, Object> getRaw() { return raw; }
        public Map<String, Object> getSource() { return source; }
        public Object getConfidence() { return confidence; }
        public Map<String, Object> getReview() { return review; }
    }
}
