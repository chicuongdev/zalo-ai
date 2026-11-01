# 08 — Hợp đồng giữa các module & cấu trúc repo

## 1. Kiểu dữ liệu trao đổi (Python dataclass / pydantic)

```python
# --- Pha A ---
RawSheet(file: str, sheet: str | None, cells: list[list[Any]])
LogicalTable(name: str, sources: list[str], header: list[str], header_prefix: list[str] | None,
             rows: list[list[Any]], sheet_period: list[tuple[int, int] | None])
ColumnProfile(name, parser: str, parse_rate: float, n_distinct: int, samples: list, stats: dict)
TypedTable(logical: LogicalTable, columns: dict[str, ColumnProfile], data: pd.DataFrame)
MappingSpec(tables: list[TableMapping], enum_maps: dict[str, dict[str, str]],
            unit_conversions: list[tuple[str, str, float]], readme_facts: dict, decisions: list[Decision])
TableMapping(source: str, cdm_table: str, columns: dict[str, str | None], split: str | None)
Manifest(business_id, industry_guess, data_start, data_end, has_customer_codes,
         capabilities: dict[str, bool], enums: dict[str, list[str]],
         validation: dict[str, float], confidence: dict[str, float])
ShopStore(business_id, db: duckdb.DuckDBPyConnection, manifest: Manifest, entities: EntityIndex, cfg: RuleConfig)

# --- Pha B ---
Question(id, business_id, question, as_of_date: date)
NormalizedQ(raw, fixed, noaccent, hints: RegexHints)
QueryPlan(intent: str, outputs: list[OutputSpec], entities: list[Mention], answer_type: str,
          requires: list[str], unsupported_attribute: str | None)
ResolvedPlan(plan: QueryPlan, entity_ids: dict[str, EntityLink], periods: dict[str, ResolvedPeriod])
Answerability(status: Literal["answerable", "unanswerable", "uncertain"], rule: str | None, reason: str | None)
ExecResult(path: Literal["semantic", "fallback"], value: Any, code: str | None, output: str | None, error: str | None)
Decision(p_correct: float, signals: dict[str, float], action: Literal["answer", "abstain"])
FinalAnswer(id, type, answer=None, reason=None)
```

Mọi kiểu đều **serialize được ra JSON** để ghi log và để dựng lại một câu khi debug (`scripts/replay.py <qid>`).

## 2. Giao diện chính

```python
# datamate/ingest/__init__.py
def build_shop(biz_dir: Path, llm: LLMClient, cfg: RuleConfig, work: Path) -> ShopStore

# datamate/semantic/registry.py
INTENT_REGISTRY: dict[str, IntentSpec]     # name -> (fn, slots schema, answer types, requires, rule refs)

# datamate/qa/pipeline.py
async def answer(q: Question, store: ShopStore, ctx: RunContext) -> tuple[FinalAnswer, dict]   # (đáp án, log)

# datamate/llm.py
class LLMClient:  # bọc vLLM OpenAI API
    async def json(self, prompt, schema, *, thinking=False, seed=0) -> dict
    async def text(self, prompt, *, seed=0, max_tokens=...) -> str
```

## 3. Cấu trúc repo

```
zaloai/
├── subject/                      # đề bài
├── plan/                         # kế hoạch & thiết kế
├── data/                         # train/ (gitignore)
├── datamate/
│   ├── main.py                   # entrypoint: Orchestrator (P0–P4)
│   ├── config.py                 # cấu hình chạy (đường dẫn, concurrency, ngưỡng, model)
│   ├── llm.py                    # LLMClient
│   ├── rules/
│   │   ├── rulebook_train.md     # bản train đóng gói để diff
│   │   ├── config.py             # RuleConfig
│   │   └── analyzer.py           # [R]
│   ├── calendar.py               # [C]
│   ├── ingest/
│   │   ├── readers.py            # A1
│   │   ├── detect.py             # A2
│   │   ├── parsers.py            # A3
│   │   ├── synonyms.py           # từ điển cột/giá trị (xây từ train)
│   │   ├── mapper.py             # A4
│   │   ├── builder.py            # A5
│   │   ├── validate.py           # A6
│   │   └── cdm.py                # định nghĩa bảng CDM (DDL)
│   ├── semantic/
│   │   ├── primitives.py         # valid_orders, revenue, rank, debt_at, stock_at…
│   │   ├── intents/              # mỗi nhóm intent một file: revenue.py, items.py, debt.py, stock.py, purchase.py, pharmacy.py…
│   │   └── registry.py
│   ├── qa/
│   │   ├── normalize.py          # B1 (+ bảng teencode/Telex)
│   │   ├── parser.py             # B2 (+ prompts/, schema QueryPlan)
│   │   ├── entities.py           # B3
│   │   ├── periods.py            # B4
│   │   ├── answerability.py      # B5
│   │   ├── executor.py           # B6
│   │   ├── fallback.py           # B7 (+ sandbox runner)
│   │   ├── decide.py             # B8
│   │   ├── formatter.py          # B9
│   │   └── pipeline.py
│   ├── scoring.py                # luật chấm chính thức (evaluator + round-trip formatter)
│   └── io.py                     # Writer submission + logs
├── scripts/
│   ├── eda.py
│   ├── evaluate.py               # chấm submission vs answers
│   ├── label_plans.py            # sinh & kiểm chứng QueryPlan cho train (xem 09)
│   ├── replay.py                 # chạy lại một câu từ log
│   └── bench_models.py
├── training/                     # SFT parser / codegen (LoRA)
├── tests/                        # unit test parser giá trị, period, primitives, scoring…
├── Dockerfile  predict.sh  requirements.txt  README.md
```

## 4. Cấu hình (một file, ghi vào log mỗi lần chạy)

```yaml
model: {name: Qwen3-14B-FP8, replicas: 2, max_model_len: 16384}
concurrency: {ingest_procs: 8, questions: 32}
parser: {few_shot: 8, retry_with_thinking: true}
fallback: {enabled: true, timeout_s: 30, repairs: 2, self_consistency: 2}
decision: {threshold: 0.5, calibrator: models/calib.json}
time: {budget_s: 21600, safety_margin_s: 900}
```
