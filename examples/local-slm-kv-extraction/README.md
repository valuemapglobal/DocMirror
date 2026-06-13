# CPU-Only Semantic K-V Extraction with DocMirror & Qwen2.5 0.5B

This example demonstrates DocMirror's pure **unix-philosophy** capability: using the parser strictly for deterministic structural segmentation (yielding clean Section blocks), and delegating complex semantic understanding (converting messy layouts into Key-Value pairs) to a tiny, fast, locally-run Small Language Model (SLM) on pure CPU.

## The Architecture
- **Parser (`SectionDrivenStrategy`)**: Detects document sections, outputting perfectly isolated `text` blocks for each section (e.g. `1.1 Identity Info`).
- **Semantic Extractor (LLM)**: A 400MB `Qwen2.5-0.5B-Instruct` model inference engine running on CPU via `llama-cpp-python`. It takes the section text and accurately restructures it into a JSON key-value dictionary, overcoming any layout obfuscation (like merged columns) without regex or heuristics.

## Requirements
To run this example, you need `llama-cpp-python`.

```bash
# This will compile llama.cpp natively for your CPU architecture.
# It requires a standard C/C++ compiler on your system (Xcode on Mac, GCC on Linux).
pip install -r requirements.txt
```

## Running the Example
```bash
python extract_kv_slm.py
```

The script will:
1. Auto-download the `qwen2.5-0.5b-instruct-q8_0.gguf` model (~400MB) from Hugging Face Hub.
2. Load an anonymized mock-up of a structurally complex text block extracted by DocMirror.
3. Process the text entirely on your CPU, returning a pristine JSON dictionary containing the target fields.
