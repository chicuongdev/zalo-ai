"""Generates notebooks/kaggle_llm_benchmark.ipynb (edit the cells here, then re-run this file)."""
import json
from pathlib import Path

CELLS = [
    ("md", """# DataMate — benchmark LLM parser trên Kaggle (zero-shot + few-shot, chưa fine-tune)

**Mục tiêu:** đo xem model open-source nào chuyển câu hỏi → QueryPlan tốt nhất trên **dev** (5 shop không dùng làm few-shot),
và PA end-to-end khi ghép với thư viện ngữ nghĩa + parser luật.

**Chuẩn bị (một lần):**
1. Máy local: `python scripts/make_kaggle_bundle.py` → `dist/datamate_code.zip`.
2. Kaggle → Datasets → New: tải `dist/datamate_code.zip` tên **datamate-code**, tải `train.zip` tên **datamate-train**.
   **Visibility: Private** (dữ liệu cuộc thi không được công khai).
3. Notebook: *Add Input* hai dataset trên; *Settings* → Accelerator **GPU T4 x2**, **Internet on**.
4. (Tuỳ) *Add-ons → Secrets*: `HF_TOKEN` nếu repo model cần đăng nhập.

Chạy lần lượt từng cell (chỉ dùng vLLM trên GPU). Mỗi model chạy ở một phiên (Restart session giữa các model để giải phóng VRAM)."""),
    ("code", """# ==== cấu hình: chọn model cho lần chạy này ====
import os
CANDIDATES = {
    # name: (hf repo, extra args cho eval script)        — T4 không có bf16 => dtype half
    # T4 = 15GB/GPU: prompt ~2.5k token nên 4096 là đủ; giới hạn số câu song song để tiết kiệm bộ nhớ trạng thái
    "qwen3.5-9b":    ("Qwen/Qwen3.5-9B",     "--dtype half --tp 2 --text-only --max-model-len 4096 --max-num-seqs 16 --enforce-eager"),
    "qwen3-14b-awq": ("Qwen/Qwen3-14B-AWQ",  "--dtype half --tp 2 --quant awq --max-model-len 4096 --max-num-seqs 32"),
    "qwen3-8b":      ("Qwen/Qwen3-8B",       "--dtype half --tp 2 --max-model-len 4096 --max-num-seqs 32"),
    "qwen3.5-4b":    ("Qwen/Qwen3.5-4B",     "--dtype half --tp 1 --text-only --max-model-len 4096 --max-num-seqs 16 --enforce-eager"),
}
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'   # giảm phân mảnh bộ nhớ GPU
RUN = "qwen3.5-9b"          # đổi ở đây
SPLIT = "dev,holdout"       # dev (513 câu) + holdout (512) chạy chung một lần nạp model; few-shot pool = fit
LIMIT = 0                   # 0 = tất cả; đặt 50 để chạy thử nhanh (50 câu mỗi split)
SHOTS = 6
"""),
    ("code", """import os, shutil, subprocess, sys, zipfile, glob
from pathlib import Path

REPO = Path('/kaggle/working/repo')
RESULTS = Path('/kaggle/working/results')     # ngoài REPO: chạy lại cell này không mất kết quả / cache
CACHE = Path('/kaggle/working/cdm_cache')
RESULTS.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
code = sorted(glob.glob('/kaggle/input/**/datamate_code.zip', recursive=True))
pkg_dirs = sorted(glob.glob('/kaggle/input/**/datamate/__init__.py', recursive=True))
os.chdir('/kaggle/working')
if REPO.exists():
    shutil.rmtree(REPO)
if code:
    zipfile.ZipFile(code[0]).extractall(REPO)
elif pkg_dirs:   # Kaggle auto-extracts uploaded zips
    shutil.copytree(Path(pkg_dirs[0]).parents[1], REPO)
else:
    raise SystemExit('datamate-code dataset not attached')

# train data: questions.jsonl + answers.jsonl + calendar.csv + data/<biz>/
qfile = sorted(glob.glob('/kaggle/input/**/train/questions.jsonl', recursive=True))
if qfile:
    train_dir = Path(qfile[0]).parent
else:
    z = sorted(glob.glob('/kaggle/input/**/train.zip', recursive=True))
    zipfile.ZipFile(z[0]).extractall('/kaggle/working/train_data')
    train_dir = Path('/kaggle/working/train_data/train')
(REPO / 'data').mkdir(exist_ok=True)
if not (REPO / 'data/train').exists():
    os.symlink(train_dir, REPO / 'data/train')
os.chdir(REPO)
print('repo', REPO, '| train', train_dir, '| shops', len(list((REPO / 'data/train/data').iterdir())))
# so sánh với dòng make_kaggle_bundle.py in ra trên máy local: khác nhau => Kaggle còn dùng bản code cũ
info = REPO / 'BUILD_INFO.txt'
print(info.read_text() if info.exists() else 'BUILD_INFO.txt not found => bundle cũ (trước khi có dấu phiên bản)')
"""),
    ("code", """# ==== cài thư viện ====
# Qwen3.5 cần vLLM/transformers mới (trang model ghi vLLM nightly). vLLM kéo theo bản torch riêng, có thể khác
# CUDA với torchaudio/torchvision cài sẵn của Kaggle => gỡ torchaudio (không dùng; transformers sẽ import nó nếu có).
!pip install -q python-calamine rapidfuzz duckdb
!pip install -q -U vllm --extra-index-url https://wheels.vllm.ai/nightly 2>&1 | tail -2
!pip install -q -U "transformers>=4.57" 2>&1 | tail -2
!pip uninstall -y -q torchaudio
!nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv
"""),
    ("code", """# ==== kiểm tra torch thấy GPU (chạy trong tiến trình mới, giống lúc chạy eval) ====
check = r'''
import torch, importlib.metadata as md
print("torch", torch.__version__, "| CUDA build", torch.version.cuda, "| GPU visible:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("devices", torch.cuda.device_count(), torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))
for p in ("vllm", "transformers", "torchvision"):
    try: print(p, md.version(p))
    except Exception as e: print(p, "missing")
import transformers.processing_utils   # the import that failed when torchaudio mismatched
print("transformers import OK")
'''
r = subprocess.run([sys.executable, '-c', check], capture_output=True, text=True)
print(r.stdout[-3000:], r.stderr[-3000:])
if 'GPU visible: False' in r.stdout:
    print('>>> torch không thấy GPU: driver Kaggle có thể quá cũ so với CUDA của torch mà vLLM kéo về. '
          'Gửi lại output cell này (driver_version + CUDA build) để chọn bản vLLM phù hợp.')
"""),
    ("code", """# ==== kiểm tra code + dữ liệu (không cần GPU) ====
!python -m pytest -q 2>&1 | tail -2
# dựng Pha A cho shop của split (cache ở work/cdm) và chạy đường ống với plan vàng: phải ra PA llm = 1.0
!python -X utf8 scripts/eval_llm_parser.py --model none --backend gold --split {SPLIT} --cache {CACHE} --out {RESULTS}/gold_check 2>&1 | grep -v Warning | tail -12
"""),
    ("code", """# ==== tải model về /tmp (đĩa /kaggle/working chỉ ~20GB) ====
from huggingface_hub import snapshot_download
try:
    from kaggle_secrets import UserSecretsClient
    os.environ['HF_TOKEN'] = UserSecretsClient().get_secret('HF_TOKEN')
except Exception:
    pass
repo_id, extra = CANDIDATES[RUN]
local = snapshot_download(repo_id, local_dir=f'/tmp/models/{RUN}',
                          allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model', '*.jinja', '*.py', 'tokenizer*'])
print(local); print(subprocess.run(['du', '-sh', local], capture_output=True, text=True).stdout)
"""),
    ("code", """# ==== benchmark với vLLM (GPU) ====
OUT = f'{RESULTS}/llm_{RUN}_{SPLIT.replace(",", "+")}'
cmd = (f'python -X utf8 scripts/eval_llm_parser.py --model {local} --backend vllm {extra} '
       f'--split {SPLIT} --shots {SHOTS} --limit {LIMIT} --cache {CACHE} --out {OUT}')
LOG = f'{RESULTS}/{RUN}_vllm.log'
print(cmd)
# log đầy đủ vào file; màn hình chỉ hiện các mốc tiến độ (Phase A, nạp model, thời gian sinh, kết quả)
!{cmd} 2>&1 | tee {LOG} | grep --line-buffered -E "questions, |model load|Error:"
# báo cáo: mỗi split + tổng, số câu đúng / tổng cho từng cách kết hợp
!cat {OUT}/report.txt 2>/dev/null || echo "no report => xem lỗi bên dưới"
# nguyên nhân lỗi (nếu có): vLLM in root cause ở giữa log, không phải ở cuối
!grep -n -i -E "out of memory|exception|raise |Traceback" {LOG} | head -20
print('full log:', LOG, '(tải ở panel Output nếu cần)')
"""),
    ("code", """# ==== phân tích lỗi: câu LLM không trả lời đúng ====
import json, collections
rows = [json.loads(l) for l in open(f'{OUT}/rows.jsonl', encoding='utf-8')]
for split in dict.fromkeys(r['split'] for r in rows):
    part = [r for r in rows if r['split'] == split]
    ok = sum(r['llm_score'] == 'correct' for r in part)
    print(f'{split}: LLM đúng {ok}/{len(part)} câu, parser luật đúng {sum(r["rule_score"] == "correct" for r in part)}/{len(part)}')
bad = [r for r in rows if r['llm_score'] != 'correct']
print('\\nLLM không đúng:', len(bad), dict(collections.Counter(r['llm_score'] for r in bad)))
print('theo intent đúng:', collections.Counter((r['gold_plan'] or {}).get('intent') for r in bad).most_common(15))
both = sum(r['rule_score'] == 'correct' for r in bad)
print(f'trong đó parser luật đúng {both} câu (=> agree/llm_else_rule có thể cứu)')
for r in bad[:25]:
    print(f"\\n- [{r['split']} {r['business_id']}] {r['question']}")
    print('  gold:', json.dumps(r['gold_plan'], ensure_ascii=False)[:220])
    print('  llm :', json.dumps(r['plan'], ensure_ascii=False)[:220])
    print('  =>', str(r['llm'])[:150], '| ref:', str(r['ref'].get('answer'))[:80], '| rule:', r['rule_score'])
"""),
    ("code", """# ==== tổng hợp: mọi report đã chạy (thư mục /kaggle/working/results, tải ở panel Output) ====
for f in sorted(RESULTS.glob('*/report.txt')):
    print('===', f.parent.name)
    print(f.read_text(encoding='utf-8'), '\\n')
"""),
]


def main():
    nb = {"cells": [], "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                     "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    for i, (kind, src) in enumerate(CELLS):
        lines = src.strip("\n").split("\n")
        source = [l + "\n" for l in lines[:-1]] + [lines[-1]]
        cell = {"cell_type": "markdown" if kind == "md" else "code", "id": f"c{i:02d}", "metadata": {}, "source": source}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        nb["cells"].append(cell)
    out = Path(__file__).with_name("kaggle_llm_benchmark.ipynb")
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
