import os
import sys
import time

try:
    from llama_cpp import Llama
except ImportError:
    print("Please install requirements first: pip install -r requirements.txt")
    sys.exit(1)

from huggingface_hub import hf_hub_download

# ==============================================================================
# DocMirror + SLM POC (CPU-only Semantic KV Extraction)
# 
# Demonstrates taking a parsed `text` block from DocMirror's SectionDrivenStrategy
# and reconstructing a structured JSON dict using a tiny local LLM (0.5B parameters).
# ==============================================================================

def main():
    print("🚀 [Step 1] Initializing Proof of Concept for Local SLM...")
    repo_id = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    filename = "qwen2.5-0.5b-instruct-q8_0.gguf"
    
    print(f"📥 [Step 2] Downloading/Verifying tiny model (400MB): {filename}")
    # Set mirror if huggingface.co is blocked in your region
    # os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    model_path = hf_hub_download(repo_id=repo_id, filename=filename)
    
    print(f"🧠 [Step 3] Loading {filename} into CPU memory...")
    # Initialize llama-cpp-python engine. Runs strictly on CPU.
    llm = Llama(
        model_path=model_path,
        n_ctx=2048,
        n_threads=os.cpu_count(),
        verbose=False  # Set to True to see hardware acceleration capabilities
    )
    
    # Simulating a complex, multi-column layout parsed linearly by DocMirror
    # (ANONYMIZED & FAKE DATA FOR DEMONSTRATION)
    mock_docmirror_text = """姓名
张伟
性别
男
出生日期
1985.08.12
婚姻状况
未婚
手机号码
138****0001
单位电话
010-88****22
住宅电话
--
通讯地址
北京市朝阳区建国路XXX号
电子邮箱
zhangwei@mock.example.com"""

    prompt = f"""<|im_start|>system
你是一个专门提取财务报表和征信报告关键信息的AI助手。
任务：将我提供的杂乱文本转换为标准的JSON格式键值对 (Key-Value Pair)。
绝对只输出合法的 JSON 字典对象，不要输出任何额外的解释、说明或 Markdown 代码块符号。<|im_end|>
<|im_start|>user
提取以下文本中的个人身份信息，严格输出纯 JSON 格式。如果有"--"或空数据，请输出空字符串。
文本内容：
{mock_docmirror_text}<|im_end|>
<|im_start|>assistant
{{"""

    print("\n⚡ [Step 4] Running CPU Inference on raw text...")
    start_time = time.time()
    
    # Execute inference
    response = llm(
        prompt,
        max_tokens=512,
        stop=["<|im_end|>"],
        temperature=0.1,
        top_p=0.9
    )
    
    end_time = time.time()
    
    # Add back the opening bracket omitted in the prompt trick
    output_json = "{" + response['choices'][0]['text'].strip()
    
    # Cleanup possible closing markdown block if the model outputted one
    if output_json.endswith("```"):
        output_json = output_json[:-3].strip()
        
    print("\n" + "="*50 + "\n[💡 提取结果 (Extracted JSON)]:\n")
    print(output_json)
    
    tokens = response['usage']['completion_tokens']
    elapsed = end_time - start_time
    print("\n" + "="*50 + "\n[🚀 性能分析 (Performance)]:")
    print(f"Time Taken  : {elapsed:.2f} seconds")
    print(f"Token Speed : {tokens / elapsed:.2f} tokens/sec")
    print(f"RAM Usage   : ~500 MB (Model size 398MB)")
    print("="*50)

if __name__ == "__main__":
    main()
