# 模型选型（2026-09-23 实测）

> 结论先行：**ASR = `openai/gpt-transcribe`，润色 = `deepseek/deepseek-v4.1-flash`（关闭 reasoning）**。
> 按示例用量（每周 ≤ 8000 字 ≈ 每月 ≤ 150 分钟语音）估算 **约 $0.7/月**，即使用量翻 4 倍也在 $3/月以内。
> 在这个量级上成本几乎不构成约束，**选型标准是：准确率 > 延迟 > 价格**。

以下为历史实验数据，不是当前价格、性能或月费用保证。首次公开快照不分发当时的合成语音及内部实验日志；ASR 表格不能直接精确复现。请用自己的授权录音重新评测：

```bash
uv run tools/bench_asr.py --samples-dir evals/asr            # ASR 对比（独立脚本，不依赖包）
uv run python tools/bench_polish.py --repeat 3               # 润色对比（使用 app 自己的 prompt 和请求参数）
```

## 1. OpenRouter 的音频能力（2026-09 现状）

- **专用转写接口** `POST /api/v1/audio/transcriptions`（2026-07-22 上线）。JSON 请求体：
  `{"model", "input_audio": {"data": <base64>, "format": "ogg|mp3|wav|flac|m4a|webm|aac"}, "language"?, "temperature"?, "response_format"?: "json"|"verbose_json", "provider"?}`。
  上限 25 MB，上游处理超时 60 s。返回 `{"text", "usage": {"seconds", "cost"}}`。
- STT 模型**不出现在默认的 `/api/v1/models` 列表里**，要用 `GET /api/v1/models?output_modalities=transcription` 查（当前 22 个）。
- 多模态聊天模型也能吃音频（`/chat/completions` 里的 `input_audio` content part），但更慢，见下表。
- **供应商专属参数**放在 `provider.options.<provider-slug>` 下。已验证：`gpt-transcribe` 的 `keywords` / `languages` / `prompt`
  放在 `provider.options.openai` 下**生效**，放在顶层**被静默忽略**。
  2026-09-24 补充实测（10 条合成 clip，内部实验 12，原始日志未公开）：
  `mai-transcribe-2` 的热词要写成 `provider.options.azure.phraseList.phrases`（列表），其他写法不生效；
  `gpt-4o-mini-transcribe` 只认 `provider.options.openai.prompt`（词表拼成字符串）；
  Fish / Voxtral / Qwen3-ASR-Flash / Deepgram 经 OpenRouter 试过的所有热词写法都不生效。
- 隐私路由：`provider.data_collection = "deny"` 和 `provider.zdr = true` 对 STT 与 chat 请求都被接受，且不增加延迟（已实测）。

## 2. ASR 对比

测试集：`evals/asr/`，8 条 edge-tts 合成语音（5–9 s；中文、中英混杂、口语化自我修正、英文），16 kHz 单声道 Opus 24 kbps。
**注意：合成语音比真人录音干净得多，CER 普遍偏低；最终要用用户自己的录音复测（见 AGENTS.md 的“评测”一节）。**

| 模型 | 类型 | p50 延迟 | 最大 | 平均 CER | 约 $/分钟 | 备注 |
|---|---|---|---|---|---|---|
| **openai/gpt-transcribe** | STT | **0.95 s** | 1.17 s | **0.4%** | 0.0045 | 中英混排空格规范；**唯一验证可用的关键词提示** |
| microsoft/mai-transcribe-2 | STT | 0.82 s | 0.88 s | 0.6% | 0.0017 | 快且便宜；英文术语全小写、偶尔整句加引号 → **备用** |
| fish-audio/transcribe-1 | STT | 0.53 s | 0.58 s | 0.6% | 0.006 | 最快 |
| x-ai/grok-stt-1.0 | STT | 0.79 s | 1.13 s | 1.5% | 0.0017 | "PR" → "P2" |
| openai/gpt-4o-mini-transcribe | STT | 1.23 s | 1.94 s | 1.0% | ~0.0018 | 中文里用半角逗号 |
| qwen/qwen3-asr-flash-2026-02-10 | STT | 1.88 s | 2.01 s | 1.0% | 0.0021 | 中文标点/列表格式最好；pytest → Ptest |
| mistralai/voxtral-mini-transcribe | STT | 1.05 s | 2.06 s | 1.3% | 0.003 | 中文常缺标点 |
| openai/whisper-large-v3 | STT | 0.77 s | 5.91 s | 1.3% | ~0.0005 | "API key" → "API-T" |
| openai/whisper-large-v3-turbo | STT | 3.05 s | 31.8 s | 0.6% | 0.0002 | 延迟极不稳定 |
| qwen/qwen3-asr-1.7b | STT | 58 s | 59 s | 0.6% | 0.00045 | 不可用（排队） |
| nvidia/nemotron-3.5-asr-streaming | STT | 19.7 s | 23 s | 8.9% | 0.0002 | 不可用 |
| google/gemini-3.1-flash-lite | chat+audio | 1.75 s | 2.24 s | 0.6% | — | |
| google/gemini-3.8-flash | chat+audio | 2.52 s | 3.08 s | 0.4% | — | reasoning 必开 |
| xiaomi/mimo-v2.6-flash | chat+audio | 2.89 s | 6.45 s | 0.4% | — | |
| qwen/qwen3.8-omni-flash | chat+audio | 5.02 s | 7.34 s | 0.4% | — | |
| assemblyai/universal-3-5-pro | STT | — | — | — | 0.0038 | 只收 WAV，未测 |
| meta/muse-voice-transcribe-1.0 | STT | — | — | — | 0.003 | 需在 OpenRouter 设置里做 18+ 确认，未测 |
| openai/gpt-audio-mini | chat+audio | — | — | — | — | 只收 wav/mp3，未测 |

共性问题：所有模型都把 "Claude Code" 听成 "Cloud Code"。
对 `gpt-transcribe` 传 `provider.options.openai.keywords = ["Claude Code", ...]` 后即可修正。
对 Qwen（试过 `context` / `prompt` / `corpus`）、MAI（`keywords` / `phrase_list` / `prompt`）、Fish（`prompt`）都没有找到生效的参数名。
**个人词典因此以 gpt-transcribe 为主通道**，润色 LLM 作为第二道保险：没有词典时它也能根据上下文把 "cloud code" 改成 "Claude Code"。

### 上传格式（经本地代理，gpt-transcribe / MAI 各 16 次的 p50）

| 格式 | gpt-transcribe | mai-transcribe-2 | 8 s 语音体积 |
|---|---|---|---|
| OGG/Opus 24 kbps | 0.97 s | 0.63 s | ~25 KB |
| MP3 32 kbps | 0.93 s | 0.58 s | ~35 KB |
| FLAC | 1.04 s | 0.80 s | ~150 KB |
| WAV 16 kHz | 1.80 s | 1.31 s | ~280 KB |

→ **上传 OGG/Opus**（`soundfile` 0.14 / libsndfile 1.2.2 在 Windows 上原生支持 OGG-Opus 和 MP3 编码，已验证）。
不要上传 WAV：多出 0.7–0.9 s。

## 3. 润色（文本）模型对比

用例：`evals/polish/cases.jsonl`（现在 24 条），每条带自动检查（must / must_not / 长度比 / 行数），
覆盖：自我修正、列表化、问句不回答、“帮我写…”不执行、提示注入、大小写/术语、词典纠错、英文邮件格式、
聊天短句、口语冗余、数字规范、口述换行、有意义的“那个”不删、纯语气词输出空、繁转简、称呼 AI 不回答、长段落不丢信息。

第二轮（19 条 × 3 次，并发 6，`provider.sort=latency` + `data_collection=deny`）：

| 模型 | 通过 | TTFT p50 | 总时长 p50 | p90 | $/千次 | 主要问题 |
|---|---|---|---|---|---|---|
| **deepseek/deepseek-v4.1-flash** | **57/57** | 1.19 s | **1.29 s** | 3.80 s | 0.07 | 偶发长尾（4–5 s） |
| qwen/qwen3.8-flash | 55/57 | 1.78 s | 2.27 s | 2.85 s | 0.06 | 输出 "（空）"；多插一个"的" |
| openai/gpt-5.6-luna | 52/57 | 1.56 s | 1.89 s | 2.51 s | 0.07 | 过度改写（删掉"那个文件"、重排语序） |
| google/gemini-3.1-flash-lite | 48/57 | 1.44 s | 1.53 s | 1.91 s | 0.35 | **长段落丢内容**、数字两侧加空格 |
| inception/mercury-2.5 | 47/57 | 1.25 s | 1.26 s | 1.56 s | 0.05 | 长段落截断、Mac → macOS |
| moonshotai/kimi-k2.6 | 46/57 | 1.56 s | 1.96 s | 3.51 s | 0.27 | 9 次请求报错；输出 "（空）" |

第一轮（16 条 × 1 次，旧版 prompt）里被淘汰的：`openai/gpt-6-luna`（15/16，但在提示注入用例里**自己补了一句英文拒答**）、
`gemini-3.5-flash-lite` 14/16、`mimo-v2.6-flash` 14/16（延迟 15 s）、`nemotron-3.5-lightning` 13/16（英文邮件原样返回）、
`claude-haiku-4.5` 12/16、`seed-2.0-mini` 12/16、`gpt-5.4-nano` 11/16（英文邮件原样返回、繁体不转）、
`qwen3.7-flash` / `mistral-small-2603`（并发下被上游 429 限流）。

第三轮（用例扩到 22 条，新增：耳语提问“橙汁多少钱”、笔记里的购物清单转列表、“7 am 改成 3 pm”；
prompt 增加了“笔记类应用把并列项转成列表”的规则和示例；客户端加了网络错误重试）：
**deepseek-v4.1-flash 66/66**，TTFT p50 1.31 s，总时长 p50 1.47 s，p90 2.18 s（4 路并发）。

第四轮（24 条，新增“保留句尾语气词”和“中文谐音还原英文术语，如 克劳德 → Claude”，均来自开源项目的经验，见 references §3.6）：
- deepseek-v4.1-flash **71/72**，唯一失败是“笔记里的购物清单转列表”（3 次里 1 次没转）。这是风格上的边缘用例，允许不稳定。
- 备用 qwen3.8-flash **24/24**。

说明：
- 上表延迟是在并发下测的；**CLI 顺序单次调用时 DeepSeek 润色只要 0.46–0.67 s**。
- 并发时，本地代理偶尔会让连接以 `SSL: UNEXPECTED_EOF_WHILE_READING` 断掉。
  客户端对这类网络错误会在“还没收到任何输出”的前提下自动重试一次（`openrouter.NetworkError`）。
- 网络基线：经本地代理（127.0.0.1:7890）到 OpenRouter，热连接 RTT ≈ 215 ms，**冷连接 ≈ 920 ms**，
  所以 app 必须在按下热键时预热连接（`OpenRouterClient.warm_up()`），并把 keep-alive 设长（已设 120 s）。

## 4. 端到端延迟（松开热键 → 拿到文本）

实测（CLI，8 s 中文语音）：ASR 1.1 s + 润色 0.5 s ≈ **1.6 s**。目标：p50 ≤ 1.5 s（不含粘贴）。后续可做的优化见 `docs/architecture.md` 的“延迟预算”。

## 5. 成本估算

| 项 | 单价 | 月用量假设 | 月成本 |
|---|---|---|---|
| gpt-transcribe | $0.000075/s（$0.0045/min） | 150 min | $0.68 |
| deepseek-v4.1-flash 润色 | ≈ $0.00007/次（~1.5k 输入 token，含 system prompt） | 600 次 | $0.04 |
| 指令 / 翻译 | 同量级 | 少量 | < $0.05 |
| **合计** | | | **≈ $0.7–0.8**（OpenRouter 充值另收 5.5% 手续费） |

对比 Typeless Pro 的 $12/月。

## 6. 默认配置与备选（2026-10-08 按源码核对）

| 用途 | 默认 | 备用（主模型报错时） | 请求参数 |
|---|---|---|---|
| ASR | `openai/gpt-transcribe` | `microsoft/mai-transcribe-2` | `provider.options.openai.{keywords, languages}`；`data_collection=deny` |
| 听写润色 | `deepseek/deepseek-v4.1-flash` | `openai/gpt-6-luna` | `reasoning.enabled=false`，`provider.sort=latency` |
| 语音指令 / 提问 | `deepseek/deepseek-v4.1-flash` | `openai/gpt-6-luna` | 独立 Ask 提示词与结构化动作输出 |
| 翻译 | `deepseek/deepseek-v4.1-flash` | `openai/gpt-6-luna` | 复用润色模型配置，使用翻译提示词 |

请求预设在 `src/local_typeless/models.py` 的 `CHAT_PRESETS` 里。换模型之前先跑一遍 `tools/bench_polish.py`。

2026-10-08 未换模型，仅调整听写提示词。33 条用例各 3 次，主模型 92/99 → 99/99，备用 89/99 → 97/99；原有用例无新增失败。历史样本范围、计分规则复核、费用与限制见 [本次评测记录](prompt-quality-2026-10-08.md)。已有用户配置若显式填写旧备用模型，会继续覆盖这些默认值。

## 7. 待办 / 未决

- 用**真人录音**（用户自己的声音、带口音、带背景噪音、更长的 30–120 s 段落）重跑 ASR 对比。合成语音区分度不够。
- **候选：把默认 ASR 换成 `mai-transcribe-2` + phraseList 热词 + 现有 LLM 词典**。2026-09-24 的合成语音实验（实验 12）里，它在术语识别上达到 95%，
  高于 `gpt-transcribe` + keywords 的 88–93%，费用约 1/3；轻噪声下仍是 95%。延迟：并发探测时 p50 0.56 s 对 1.02 s，
  但顺序热连接复测只快约 0.15 s（ASR p50 0.91 s 对 1.06 s；ASR+LLM 1.54 s 对 1.64 s），以顺序数字为准。
  前提仍是本节第一条：先用真人录音跑 `tools/bench_asr.py` 复核 CER、标点和英文大小写，再改 `models.py` 的默认值。
- DeepSeek 的长尾延迟：可以考虑对冲请求（TTFT 超过约 1.5 s 时并行打一发备用模型，谁先回来用谁），或者用 `provider.order` 固定 p90 更好的供应商。
- 短句能不能跳过润色（gpt-transcribe 自带标点）直接上屏以省 0.5 s，需要评测。
- 长录音（> 2 分钟）：上游 60 s 处理超时，需要在静音处切片、并行转写。
- 模型会更新很快：本文件的数字只代表 2026-09-23 这一天。

## 备用整理模型换成 gpt-6-luna（2026-09-27）

**原因**：原备用模型 `qwen/qwen3.8-flash` 在 2026-09-26 至 27 连续两天被上游限流（`temporarily rate-limited upstream`），单并发也有 23/27 个请求返回 429。默认模型一出错就没有可用的兜底。用户要求换成 Luna。

**实测**（当前 prompt，含 2026-09-26 新加的两条词典规则，用例 27 条）：

| | 整理 bench_polish ×3 | Ask bench_ask | 首字 p50 | 价格（输入 / 输出，每百万 token） |
|---|---|---|---|---|
| deepseek-v4.1-flash（默认） | 80/81 | 28/28 | 1.12 s | $0.035 / $0.29 |
| **gpt-6-luna（新备用）** | 74/81 | 27/28 | 1.42 s | $0.10 / $0.50 |
| qwen3.8-flash（原备用） | 无法测（429） | — | — | $0.15 / $0.47 |

- gpt-6-luna 的失败集中在"太保守"：
  - 不把口语的标识符写成代码形式，`zh_dictionary_not_exhaustive` 3 次全失败；
  - 笔记里的购物清单不转列表，3 次全失败（默认模型也会偶发）；
  - `zh_request_stays_request` 1 次没把 "test dependency overrides" 连成标识符。
- 第一轮淘汰它的原因是它在提示注入用例里自己补了一句英文拒答。这次 `zh_injection` 3/3 原样输出，没有复现。
- Ask 唯一的失败是弯引号（`didn’t`），内容正确。
- **不适合当默认模型**：比 DeepSeek 贵约 2–3 倍，整理质量也低一档。**作为备用可以**：只在默认模型出错或超时时才用，而且比 qwen 便宜。
- 注意：之前说"Luna 成本减半"指的是**生成仓库词库**（实验 24），不是日常整理。
