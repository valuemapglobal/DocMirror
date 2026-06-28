package com.docmirror.sdk;

import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.*;

import java.io.File;
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Client for the DocMirror Universal Document Parsing API.
 * Auto-generated from OpenAPI spec at docs/openapi/openapi.json.
 * Regenerate with: openapi-generator-cli generate -i openapi.json -g java
 */
public class DocMirrorClient {

    private final String baseUrl;
    private final OkHttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final String apiKey;

    /**
     * Create a new DocMirror API client.
     *
     * @param baseUrl the API base URL (e.g. "https://api.docmirror.dev")
     */
    public DocMirrorClient(String baseUrl) {
        this(baseUrl, null, null);
    }

    /**
     * Create a new DocMirror API client with API key.
     *
     * @param baseUrl the API base URL
     * @param apiKey  the API key for authentication
     */
    public DocMirrorClient(String baseUrl, String apiKey) {
        this(baseUrl, apiKey, null);
    }

    /**
     * Create a new DocMirror API client with full configuration.
     *
     * @param baseUrl    the API base URL
     * @param apiKey     the API key (nullable)
     * @param httpClient custom OkHttpClient (nullable)
     */
    public DocMirrorClient(String baseUrl, String apiKey, OkHttpClient httpClient) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.apiKey = apiKey;
        this.httpClient = httpClient != null ? httpClient : new OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(120, TimeUnit.SECONDS)
                .writeTimeout(120, TimeUnit.SECONDS)
                .build();
        this.objectMapper = new ObjectMapper();
    }

    /**
     * Parse a document and return the DMIR response.
     *
     * @param filePath path to the document file
     * @return parsed DMIR response
     * @throws IOException if the request fails
     */
    public DMIRResponse parseDocument(String filePath) throws IOException {
        return parseDocument(filePath, null);
    }

    /**
     * Parse a document with explicit parse mode.
     *
     * @param filePath path to the document file
     * @param mode     parse mode: "auto", "fast", "balanced", or "accurate"
     * @return parsed DMIR response
     * @throws IOException if the request fails
     */
    public DMIRResponse parseDocument(String filePath, String mode) throws IOException {
        File file = new File(filePath);
        if (!file.exists()) {
            throw new IOException("File not found: " + filePath);
        }

        RequestBody requestBody = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("file", file.getName(),
                        RequestBody.create(file, MediaType.parse("application/octet-stream")))
                .addFormDataPart("mode", mode != null ? mode : "auto")
                .build();

        Request request = new Request.Builder()
                .url(baseUrl + "/v1/parse")
                .header("Authorization", apiKey != null ? "Bearer " + apiKey : "")
                .post(requestBody)
                .build();

        try (Response response = httpClient.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("DocMirror API error: HTTP " + response.code()
                        + " - " + (response.body() != null ? response.body().string() : "unknown"));
            }
            String json = response.body() != null ? response.body().string() : "{}";
            return objectMapper.readValue(json, DMIRResponse.class);
        }
    }


    /**
     * Parse a document from a raw byte array (e.g. from an API response).
     *
     * @param data     raw document bytes
     * @param fileName original filename with extension
     * @return parsed DMIR response
     * @throws IOException if the request fails
     */
    public DMIRResponse parseDocument(byte[] data, String fileName) throws IOException {
        return parseDocument(data, fileName, null);
    }

    /**
     * Parse a document from raw bytes with explicit parse mode.
     *
     * @param data     raw document bytes
     * @param fileName original filename with extension
     * @param mode     parse mode: "auto", "fast", "balanced", or "accurate"
     * @return parsed DMIR response
     * @throws IOException if the request fails
     */
    public DMIRResponse parseDocument(byte[] data, String fileName, String mode) throws IOException {
        RequestBody requestBody = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("file", fileName,
                        RequestBody.create(data, MediaType.parse("application/octet-stream")))
                .addFormDataPart("mode", mode != null ? mode : "auto")
                .build();

        Request request = new Request.Builder()
                .url(baseUrl + "/v1/parse")
                .header("Authorization", apiKey != null ? "Bearer " + apiKey : "")
                .post(requestBody)
                .build();

        try (Response response = httpClient.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("DocMirror API error: HTTP " + response.code()
                        + " - " + (response.body() != null ? response.body().string() : "unknown"));
            }
            String json = response.body() != null ? response.body().string() : "{}";
            return objectMapper.readValue(json, DMIRResponse.class);
        }
    }

    /**
     * Parse multiple documents in batch.
     *
     * @param filePaths array of file paths to upload and parse
     * @return parsed DMIR response (batch summary)
     * @throws IOException if the request fails
     */
    public DMIRResponse parseDocumentBatch(String[] filePaths) throws IOException {
        return parseDocumentBatch(filePaths, null);
    }

    /**
     * Parse multiple documents in batch with explicit parse mode.
     *
     * @param filePaths array of file paths to upload and parse
     * @param mode      parse mode: "auto", "fast", "balanced", or "accurate"
     * @return parsed DMIR response (batch summary)
     * @throws IOException if the request fails
     */
    public DMIRResponse parseDocumentBatch(String[] filePaths, String mode) throws IOException {
        MultipartBody.Builder builder = new MultipartBody.Builder()
                .setType(MultipartBody.FORM);

        for (String fp : filePaths) {
            File file = new File(fp);
            if (!file.exists()) {
                throw new IOException("File not found: " + fp);
            }
            builder.addFormDataPart("files", file.getName(),
                    RequestBody.create(file, MediaType.parse("application/octet-stream")));
        }

        builder.addFormDataPart("mode", mode != null ? mode : "auto");

        Request request = new Request.Builder()
                .url(baseUrl + "/v1/parse/batch")
                .header("Authorization", apiKey != null ? "Bearer " + apiKey : "")
                .post(builder.build())
                .build();

        try (Response response = httpClient.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("DocMirror batch API error: HTTP " + response.code()
                        + " - " + (response.body() != null ? response.body().string() : "unknown"));
            }
            String json = response.body() != null ? response.body().string() : "{}";
            return objectMapper.readValue(json, DMIRResponse.class);
        }
    }

    /**
     * Parse a file already present on the DocMirror server filesystem.
     *
     * @param serverPath absolute path to the file on the server
     * @return parsed DMIR response
     * @throws IOException if the request fails
     */
    public DMIRResponse parseFileOnServer(String serverPath) throws IOException {
        return parseFileOnServer(serverPath, null);
    }

    /**
     * Parse a file on the server with explicit parse mode.
     *
     * @param serverPath absolute path to the file on the server
     * @param mode       parse mode: "auto", "fast", "balanced", or "accurate"
     * @return parsed DMIR response
     * @throws IOException if the request fails
     */
    public DMIRResponse parseFileOnServer(String serverPath, String mode) throws IOException {
        String jsonBody = objectMapper.writeValueAsString(
                java.util.Map.of("path", serverPath, "mode", mode != null ? mode : "auto"));

        Request request = new Request.Builder()
                .url(baseUrl + "/v1/parse/file")
                .header("Authorization", apiKey != null ? "Bearer " + apiKey : "")
                .header("Content-Type", "application/json")
                .post(RequestBody.create(jsonBody, MediaType.parse("application/json")))
                .build();

        try (Response response = httpClient.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("DocMirror server-parse error: HTTP " + response.code()
                        + " - " + (response.body() != null ? response.body().string() : "unknown"));
            }
            String json = response.body() != null ? response.body().string() : "{}";
            return objectMapper.readValue(json, DMIRResponse.class);
        }
    }

    /**
     * Check API health.
     *
     * @return health response
     * @throws IOException if the request fails
     */
    public HealthResponse health() throws IOException {
        Request request = new Request.Builder()
                .url(baseUrl + "/health")
                .get()
                .build();

        try (Response response = httpClient.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("DocMirror health check failed: HTTP " + response.code());
            }
            String json = response.body() != null ? response.body().string() : "{}";
            return objectMapper.readValue(json, HealthResponse.class);
        }
    }
}
