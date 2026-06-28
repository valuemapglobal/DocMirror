package com.docmirror.sdk;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Health check response from the DocMirror API.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class HealthResponse {

    @JsonProperty("status")
    private String status;

    @JsonProperty("version")
    private String version;

    @JsonProperty("timestamp")
    private String timestamp;

    public String getStatus() { return status; }
    public String getVersion() { return version; }
    public String getTimestamp() { return timestamp; }

    public boolean isHealthy() {
        return "ok".equalsIgnoreCase(status) || "healthy".equalsIgnoreCase(status);
    }
}
