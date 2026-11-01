"""LLM backends: vLLM (fast, used in the final Docker image) and plain transformers (fallback for GPUs/kernels
vLLM cannot run, e.g. some Kaggle T4 setups). Both take chat messages and return text, greedy and deterministic.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    model: str                                  # HF repo id or local path
    backend: str = "vllm"                       # "vllm" | "hf"
    dtype: str = "auto"                         # T4/P100 have no bf16: use "half"
    quantization: str | None = None             # vllm: "awq", "gptq", "fp8", "bitsandbytes"; hf: "4bit" | "8bit"
    tensor_parallel: int = 1
    max_model_len: int = 8192
    max_new_tokens: int = 384
    gpu_memory_utilization: float = 0.90
    enable_thinking: bool = False               # Qwen3 / Qwen3.5 chat templates
    seed: int = 0
    guided_json: bool = True                    # vllm structured output when available
    extra: dict = field(default_factory=dict)   # passed to vllm.LLM(...)


class LLM:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        t0 = time.time()
        if cfg.backend == "vllm":
            self._init_vllm()
        elif cfg.backend == "hf":
            self._init_hf()
        else:
            raise ValueError(cfg.backend)
        self.load_seconds = time.time() - t0

    # ------------------------------------------------------------------ chat template
    def _prompt(self, messages: list[dict]) -> str:
        kw = {"tokenize": False, "add_generation_prompt": True}
        try:
            return self.tok.apply_chat_template(messages, enable_thinking=self.cfg.enable_thinking, **kw)
        except TypeError:
            return self.tok.apply_chat_template(messages, **kw)

    # ------------------------------------------------------------------ vLLM
    def _init_vllm(self):
        from vllm import LLM as VLLM
        c = self.cfg
        kw = dict(model=c.model, dtype=c.dtype, tensor_parallel_size=c.tensor_parallel, max_model_len=c.max_model_len,
                  gpu_memory_utilization=c.gpu_memory_utilization, seed=c.seed, trust_remote_code=True, **c.extra)
        if c.quantization:
            kw["quantization"] = c.quantization
        self.engine = VLLM(**kw)
        self.tok = self.engine.get_tokenizer()

    def _sampling(self, schema: dict | None):
        from vllm import SamplingParams
        kw = dict(temperature=0.0, max_tokens=self.cfg.max_new_tokens, seed=self.cfg.seed)
        if schema is not None and self.cfg.guided_json:
            # the structured-output API was renamed across vLLM versions
            try:
                from vllm.sampling_params import StructuredOutputsParams
                return SamplingParams(structured_outputs=StructuredOutputsParams(json=schema), **kw)
            except (ImportError, TypeError):
                pass
            try:
                from vllm.sampling_params import GuidedDecodingParams
                return SamplingParams(guided_decoding=GuidedDecodingParams(json=schema), **kw)
            except (ImportError, TypeError):
                pass
        return SamplingParams(**kw)

    # ------------------------------------------------------------------ transformers
    def _init_hf(self):
        import torch
        from transformers import AutoTokenizer
        c = self.cfg
        self.tok = AutoTokenizer.from_pretrained(c.model, trust_remote_code=True)
        self.tok.padding_side = "left"
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        kw = {"device_map": "auto", "trust_remote_code": True}
        if c.quantization in ("4bit", "8bit"):
            from transformers import BitsAndBytesConfig
            kw["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=c.quantization == "4bit", load_in_8bit=c.quantization == "8bit",
                bnb_4bit_compute_dtype=torch.float16, bnb_4bit_quant_type="nf4")
        else:
            kw["torch_dtype"] = {"half": torch.float16, "bfloat16": torch.bfloat16}.get(c.dtype, "auto")
        try:
            from transformers import AutoModelForCausalLM
            self.model = AutoModelForCausalLM.from_pretrained(c.model, **kw)
        except (ValueError, KeyError):
            # multimodal checkpoints (e.g. Qwen3.5) register under image-text-to-text
            from transformers import AutoModelForImageTextToText
            self.model = AutoModelForImageTextToText.from_pretrained(c.model, **kw)
        self.model.eval()

    def _hf_generate(self, prompts: list[str], batch_size: int) -> list[str]:
        import torch
        out = []
        for i in range(0, len(prompts), batch_size):
            enc = self.tok(prompts[i:i + batch_size], return_tensors="pt", padding=True).to(self.model.device)
            with torch.no_grad():
                gen = self.model.generate(**enc, max_new_tokens=self.cfg.max_new_tokens, do_sample=False,
                                          pad_token_id=self.tok.pad_token_id)
            for row in gen[:, enc["input_ids"].shape[1]:]:
                out.append(self.tok.decode(row, skip_special_tokens=True))
        return out

    # ------------------------------------------------------------------ public
    def chat(self, conversations: list[list[dict]], schema: dict | None = None, batch_size: int = 8) -> list[str]:
        prompts = [self._prompt(m) for m in conversations]
        if self.cfg.backend == "vllm":
            try:
                outs = self.engine.generate(prompts, self._sampling(schema), use_tqdm=True)
            except Exception as e:  # noqa: BLE001 - schema features differ across vLLM versions
                if schema is None:
                    raise
                print(f"guided JSON failed ({type(e).__name__}: {str(e)[:200]}); retrying unguided", flush=True)
                outs = self.engine.generate(prompts, self._sampling(None), use_tqdm=True)
            return [o.outputs[0].text for o in outs]
        return self._hf_generate(prompts, batch_size)


def extract_json(text: str):
    """First balanced JSON object in the text (thinking blocks and code fences are skipped)."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    start = text.find("{")
    while start >= 0:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None
