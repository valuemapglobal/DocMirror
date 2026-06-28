---
name: Projection Template Contribution
about: Add a new LLM framework projection template for DocMirror DMIR output
title: 'feat(projection): add <framework> projection template'
labels: ['projection', 'enhancement', 'community']
---

## Framework

<!-- Name the LLM framework this template targets -->

**Framework**: [e.g., LangChain, LlamaIndex, Haystack, Spring AI, Semantic Kernel, Vercel AI SDK]
**Package**: [e.g., langchain-core]
**Document type used**: [e.g., langchain_core.documents.Document]

## Template File

<!-- Link to the YAML template file you're adding -->

`docmirror/output/projection/templates/<framework>.yaml`

## Template Mapping

<!-- Describe the key DMIR-to-Document field mappings -->

| DMIR Field | Framework Field | Transform | Notes |
|------------|----------------|-----------|-------|
| `$.document.full_text` | `page_content` | `safe_text` | |
| `$.meta.page_count` | `metadata.page_count` | | |
| ... | ... | ... | ... |

## Test Coverage

- [ ] A test case is added to `tests/unit/test_output_dmir.py` in `TestProjectionEngine`
- [ ] The test verifies the template is loadable
- [ ] The test verifies a projection produces the expected structure

## Validation

- [ ] Template YAML is valid (no syntax errors)
- [ ] Template only uses existing DMIR fields (no custom ParseResult access)
- [ ] Template does not import any framework package at runtime
- [ ] Template follows the canonical DMIR schema (v1.0)

## Dependencies

<!-- List any optional extras that need to be added to pyproject.toml -->

N/A (projection templates are declarative YAML, no Python dependencies)

## Checklist

- [ ] I have tested the template with a real DocMirror parse result
- [ ] The projected output matches the framework's Document schema
- [ ] I have read the [Projection Template Guide](../../docs/design/GA1.0/ec/README.md)
- [ ] This template fits within ~60 lines of YAML

## Related Issues

Closes #
