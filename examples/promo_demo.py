import asyncio
import shutil
import sys
import threading
import time
from pathlib import Path

# Terminal Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_typewriter(text: str, delay: float = 0.03):
    """Prints text with a hacker-like typing effect."""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()


def print_header(title: str):
    term_width = shutil.get_terminal_size().columns
    print(f"\n{CYAN}{'=' * term_width}{RESET}")
    print(f"{CYAN}{BOLD}{title.center(term_width)}{RESET}")
    print(f"{CYAN}{'=' * term_width}{RESET}\n")


def _document_properties(mirror: dict) -> dict:
    views = mirror.get("semantics", {}).get("views", {})
    if isinstance(views, dict):
        for view in views.values():
            if isinstance(view, dict):
                props = view.get("properties") or view.get("metadata") or {}
                if isinstance(props, dict):
                    return props
    return {}


async def run_cinematic_demo():
    print_header("DocMirror - Universal Parsing Engine Initialization")

    # 1. Booting sequence
    print_typewriter(f"{MAGENTA}[SYSTEM]{RESET} Booting L0 Dispatcher...", 0.02)
    time.sleep(0.3)
    print_typewriter(f"{MAGENTA}[SYSTEM]{RESET} Loading Layout YOLO Weights (ONNX)...", 0.02)
    time.sleep(0.4)
    print_typewriter(f"{MAGENTA}[SYSTEM]{RESET} Registering Domain Plugins -> [BankStatement] [Invoice]", 0.02)
    time.sleep(0.5)
    print(f"{GREEN}[ OK ] Engine Ready.{RESET}\n")
    time.sleep(1)

    # 2. Target File
    target_file = Path("tests/fixtures/1.jpg")
    print_header("Target Acquisition")
    print_typewriter(f"File   : {YELLOW}{target_file.name}{RESET}")
    if target_file.exists():
        print_typewriter(f"Size   : {YELLOW}{target_file.stat().st_size / 1024:.1f} KB{RESET}")
    print_typewriter(f"Status : {CYAN}Ingesting into Pipeline...{RESET}")
    print("")
    time.sleep(1)

    # 3. Execution (The actual real parsing using the docmirror package)
    print_header("Exec: [docmirror.perceive_document]")

    # Create an active spinner while the vNext topology is built.
    from docmirror import perceive_document

    loading = True

    def spinner():
        spinner_chars = "|/-\\"
        i = 0
        while loading:
            sys.stdout.write(
                f"\r{CYAN}[Engine]{RESET} Extracting Evidence Plane & vNext Topology... {spinner_chars[i % 4]}"
            )
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

    t = threading.Thread(target=spinner)
    t.start()

    try:
        # Actually parse the file synchronously wrapped in asyncio!
        t_start = time.time()
        result = await perceive_document(str(target_file))
        elapsed = time.time() - t_start
    except Exception as e:
        loading = False
        t.join()
        print(f"\n{RED}[FATAL] Engine crash: {e}{RESET}")
        return

    loading = False
    t.join()
    sys.stdout.write(f"\r{GREEN}[Engine]{RESET} Parsing Complete in {elapsed:.2f}s!{' ' * 20}\n\n")
    time.sleep(0.5)

    # 4. Reveal Results — use canonical vNext mirror output
    from docmirror.models.sealed import seal_parse_result
    from docmirror.output.mirror_projector import project_mirror

    mirror = project_mirror(seal_parse_result(result))

    print_header("ParseResult -> [Document & Identity]")
    time.sleep(0.5)
    doc = mirror["document"]
    candidates = doc.get("document_type_candidates", [])
    document_type = candidates[0]["type"] if candidates else "unknown"
    confidence = candidates[0].get("confidence", 0.0) if candidates else 0.0
    print_typewriter(f" {BOLD}Document Type{RESET}:  {CYAN}{document_type}{RESET}")
    print_typewriter(f" {BOLD}Confidence   {RESET}:  {GREEN}{(confidence * 100):.1f}%{RESET}")
    print_typewriter(f" {BOLD}Properties   {RESET}:", 0.01)

    for k, v in _document_properties(mirror).items():
        print_typewriter(f"    - {k}: {YELLOW}{v}{RESET}", 0.01)
        time.sleep(0.1)

    print("")
    time.sleep(1)

    # 5. Quality Check
    print_header("Quality & Validation Check")
    quality = mirror["quality"]
    overall = quality.get("overall", {})
    print_typewriter(f" Trust Score    :  {MAGENTA}{overall.get('score', 0.0):.3f}{RESET}")
    if overall.get("status") == "pass":
        print_typewriter(f" Validation     :  {GREEN}PASSED{RESET}")
    else:
        print_typewriter(f" Validation     :  {RED}FAILED{RESET}")
        for issue in quality.get("events", []):
            print(f"    -> {RED}{issue}{RESET}")

    print("")
    time.sleep(1)

    # 6. Extracted Data Structure Highlight
    print_header("Data Topology Overview")
    pages = mirror.get("pages", [])
    tables = [b for b in mirror.get("blocks", []) if b.get("type") == "table"]
    texts = [b for b in mirror.get("blocks", []) if b.get("type") in {"paragraph", "heading"}]

    print_typewriter(f" 📄 Parsed {CYAN}{len(pages)}{RESET} Pages")
    print_typewriter(f" 📊 Parsed {CYAN}{len(tables)}{RESET} Tables")
    print_typewriter(f" 📝 Parsed {CYAN}{len(texts)}{RESET} Text Blocks")

    if tables:
        print_typewriter(f"\n {BOLD}Sample Table Header{RESET}:", 0.01)
        print(f" {YELLOW}{tables[0].get('content', {}).get('headers', [])}{RESET}")
        total_rows = sum(len(t.get("content", {}).get("rows", [])) for t in tables)
        print_typewriter(f" Total Rows: {CYAN}{total_rows}{RESET}")

    print("\n")
    print_typewriter(f"{GREEN}=========================================={RESET}", 0.01)
    print_typewriter(f"{GREEN}    [DEMO COMPLETED SUCCESSFULLY]{RESET}", 0.03)
    print_typewriter(f"{GREEN}=========================================={RESET}", 0.01)
    print("\n")


if __name__ == "__main__":
    try:
        asyncio.run(run_cinematic_demo())
    except KeyboardInterrupt:
        print(f"\n{RED}Abort sequence initiated.{RESET}\n")
