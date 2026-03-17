import asyncio
import time
import sys
import shutil
from pathlib import Path

# Terminal Colors
CYAN = '\033[96m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
MAGENTA = '\033[95m'
BOLD = '\033[1m'
RESET = '\033[0m'

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
    print_typewriter(f"Size   : {YELLOW}{target_file.stat().st_size / 1024:.1f} KB{RESET}")
    print_typewriter(f"Status : {CYAN}Ingesting into Pipeline...{RESET}")
    print("")
    time.sleep(1)

    # 3. Execution (The actual real parsing using the docmirror package)
    print_header("Exec: [docmirror.perceive_document]")
    
    # Create an active spinning loader while it extracts text
    from docmirror import perceive_document
    import threading

    loading = True
    def spinner():
        spinner_chars = "|/-\\"
        i = 0
        while loading:
            sys.stdout.write(f"\r{CYAN}[Engine]{RESET} Extracting Core Topology & Applying Middlewares... {spinner_chars[i % 4]}")
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

    # 4. Reveal Results
    print_header("PerceptionResult -> [Meta & Identity]")
    time.sleep(0.5)
    print_typewriter(f" {BOLD}Scene / Domain{RESET}:  {CYAN}{result.scene}{RESET}")
    print_typewriter(f" {BOLD}Confidence    {RESET}:  {GREEN}{(result.confidence * 100):.1f}%{RESET}")
    print_typewriter(f" {BOLD}Found Entities{RESET}:", 0.01)
    
    for k, v in result.content.entities.items():
        print_typewriter(f"    - {k}: {YELLOW}{v}{RESET}", 0.01)
        time.sleep(0.1)
        
    print("")
    time.sleep(1)

    # 5. Forgery Detection (Trust Layer)
    print_header("Trust & Validation Check")
    val = result.provenance.validation
    if val:
        print_typewriter(f" L2 Audit Score :  {MAGENTA}{val.l2_score}{RESET}")
        is_forged = val.is_forged
        if is_forged:
            print_typewriter(f" Metadata Tamper:  {RED}DETECTED{RESET}")
            for r in val.forgery_reasons:
                print(f"    -> {RED}{r}{RESET}")
        else:
            print_typewriter(f" Image Fidelity :  {GREEN}VERIFIED (No ELA Tampering){RESET}")
    else:
        print_typewriter(f" Validation     :  {YELLOW}SKIPPED (No validation middleware hit){RESET}")
        
    print("")
    time.sleep(1)

    # 6. Extracted Data Structure Highlight
    print_header("Data Topology Overview")
    tables = [b for b in result.content.blocks if b.type == "table"]
    texts = [b for b in result.content.blocks if b.type == "text"]
    
    print_typewriter(f" 📊 Parsed {CYAN}{len(tables)}{RESET} Tables")
    print_typewriter(f" 📝 Parsed {CYAN}{len(texts)}{RESET} Text Blocks")
    
    if tables and tables[0].table:
        print_typewriter(f"\n {BOLD}Sample Table Header{RESET}:", 0.01)
        print(f" {YELLOW}{tables[0].table.headers}{RESET}")
        
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
