# Architecture

## System Overview

```mermaid
graph TD
    A[Input Document] --> B[Dispatcher]
    B --> C[Format Adapter]
    C --> D[Core Extraction]
    D --> E[BaseResult]
    E --> F[Middleware Pipeline]
    F --> G[Builder]
    G --> H[PerceptionResult]

    subgraph Adapters
        C1[PDF] -.-> C
        C2[Image] -.-> C
        C3[Word] -.-> C
        C4[Excel] -.-> C
        C5[PPT] -.-> C
        C6[Email] -.-> C
    end

    subgraph Core
        D1[Layout Analysis] -.-> D
        D2[OCR Engine] -.-> D
        D3[Table Extraction] -.-> D
        D4[Formula Recognition] -.-> D
    end

    subgraph Middlewares
        F1[Scene Detection] -.-> F
        F2[Entity Extraction] -.-> F
        F3[Institution Detection] -.-> F
        F4[Validation + Trust] -.-> F
    end
```

## Layer Architecture

| Layer | Module | Responsibility |
|-------|--------|---------------|
| **Dispatch** | `framework.dispatcher` | Route files to appropriate adapter, manage caching |
| **Adapt** | `adapters.*` | Convert format → `BaseResult` |
| **Extract** | `core.extraction` | Low-level parsing (text, tables, layout, OCR) |
| **Enhance** | `middlewares.*` | Business logic pipeline (detection, extraction, validation) |
| **Build** | `models.construction.builder` | Assemble final `PerceptionResult` |
| **Output** | `models.entities.perception_result` | Structured 4-layer output model |

## Data Flow

1. **Dispatcher** (`[Dispatcher]`) detects file type, checks Redis cache, and routes to adapter.
2. **Adapter** converts raw physical elements → immutable `BaseResult`.
3. **Orchestrator** (`[Orchestrator]`) spins up middleware pipeline on `EnhancedResult`.
4. **Middlewares** (`[Middleware]`) execute in sequence: Scene → Entity → Institution → Validation.
5. **Builder** assembles final 4-layer `PerceptionResult`.
6. **Dispatcher** caches final dict securely to Redis.

## PerceptionResult Model

The output model has 4 layers:

| Layer | Field | Contents |
|-------|-------|----------|
| **Meta/Status** | `status`, `success`, `error`, `scene` | Parse envelope status, catch-all errors, and document classifier |
| **Identity** | `identity` | Domain-resolved attributes (e.g. `account_number`, `institution`) via Plugins |
| **Content** | `blocks` | Flattened standard structures (table blocks, plain text, headers, KV pairs) |
| **Trust/Provenance** | `trust`, `diagnostics` | Fidelity scoring (`validation_score`), execution timeline, and sub-engine tracebacks |

## Plugin System

Domain plugins extend DocMirror with business-specific logic:

```python
from docmirror.plugins import DomainPlugin

class InvoicePlugin(DomainPlugin):
    domain_name = "invoice"
    display_name = "Invoice"
    scene_keywords = ("invoice", "bill", "receipt")
    # ... implement build_domain_data()
```

See [Creating Plugins](../plugins/creating-plugins.md) for details.
