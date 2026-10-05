# 开源同类项目调研（2026-09-23）

> 方法：克隆了 17 个仓库，读源码，用 `gh` 查 issue。star 数和最近推送时间来自 GitHub API。**只读了代码，没有编译运行任何一个。**
> 用途：给 M1–M3 的实现找现成做法和已知坑。**只参考，不照搬**。许可证多为 AGPL/GPL，不要复制代码。

## 1. 总览

| 项目 | ★ / 最近推送 | 技术栈 · 平台 · 许可 | ASR | LLM 整理 | Windows 插入方式 | Windows 热键 |
|---|---|---|---|---|---|---|
| [Handy](https://github.com/cjpais/Handy) | 32.1k / 09-19 | Rust/Tauri · Win/mac/Linux · MIT | 仅本地（whisper.cpp、Parakeet、SenseVoice…）+ Silero VAD | 可选，支持 OpenRouter 等 OpenAI 兼容接口 | 剪贴板 + Ctrl+V；可选的 “reliable paste”（见 §3.2），默认关 | 自研 `handy-keys` 低级钩子；按住 / 切换 / 两者兼有 |
| [OpenWhispr](https://github.com/OpenWhispr/openwhispr) | 8.5k / 09-23 | Electron + C 小程序 · 三平台 · MIT | 本地 + 多家云端 | 有 | C 小程序发 Ctrl+V（终端里发 Ctrl+Shift+V）；500 ms 后且剪贴板没被改动才恢复 | 按住说话用 C 写的低级钩子 |
| [VoiceInk](https://github.com/Beingpax/VoiceInk) | 6.5k / 09-22 | Swift · 仅 macOS · GPL-3 | 本地 + 约 12 家云端，**含 OpenRouter 转写接口** | 有（含 OpenRouter） | — | — |
| [CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline) | 6.9k / 09-14 | **Python** · Windows · MIT | 本地中文模型（Qwen3-ASR、SenseVoice、Paraformer） | 有，按“角色”分文件 | 默认 `keyboard.write` 逐字；也可剪贴板 + pynput Ctrl+V，100 ms 后恢复 | pynput 钩子；按住 CapsLock，点按 < 0.3 s 放行为普通 CapsLock |
| [Whispering](https://github.com/EpicenterHQ/epicenter/tree/main/apps/whispering) | 4.8k（monorepo） / 09-18 | Svelte + Tauri · AGPL-3 | 多家云端 + 本地 | “Polish” + 用户自定义配方 | enigo 发 Ctrl+V，固定等待 | Tauri 全局快捷键 |
| [OpenLess](https://github.com/Open-Less/openless) | 3.6k / 09-18 | Rust/Tauri · AGPL-3 | 国内云（火山、讯飞、百炼、阶跃）+ OpenAI 兼容 | 有，中文 prompt | **自带 Windows TSF 输入法**直接上屏；或 Unicode 逐字流式；剪贴板兜底 | 按住 / 切换 |
| [FreeFlow](https://github.com/zachlatta/freeflow) | 2.7k / 09-07 | Swift · macOS · MIT | Groq whisper-large-v3 | 有（Groq gpt-oss-20b） | — | — |
| [amical](https://github.com/amicalhq/amical) | 1.5k / 09-22 | Electron + C# 助手 · mac/Win · MIT | 本地 + 自家云 | 有（含 OpenRouter） | C# 一次调用发完整个 Ctrl+V；保存全部剪贴板格式 | C# 低级钩子 |
| [VoiceTypr](https://github.com/ideaplexa/voicetypr) | 0.7k / 09-22 | Rust/Tauri · AGPL-3 | 本地 + 多家云端 | 有（含 OpenRouter） | 一次调用发 4 个事件的 Ctrl+V；500 ms 后恢复 | 自研低级钩子 |
| [Tambourine](https://github.com/kstonekuan/tambourine-voice) | 0.4k / 07-17 | Tauri + **Python（Pipecat）服务** · AGPL-3 | WebRTC 流式送 12 种 STT | 有（含 OpenRouter） | Ctrl+V，50 ms 间隔，100 ms 后恢复 | Tauri 全局快捷键 |
| [ququ](https://github.com/yan5xu/ququ) | 2.3k / 2025-10（停更） | Electron + Python FunASR | 本地 FunASR | 有，中文 prompt | PowerShell `SendKeys("^v")` | Electron 快捷键 |
| [whisper-writer](https://github.com/savbell/whisper-writer) | 1.1k / 2024-08（停更） | Python/PyQt5 · GPL-3 | faster-whisper / OpenAI | 无 | pynput 逐字输入 | pynput |

另外值得一看：
- [SayIt](https://github.com/crosswk/SayIt)（0.4k，国人）：读过的项目里 Windows 插入代码最细致的一个。
- 自称“开源 Typeless”的项目：OpenLess、[opentypeless](https://github.com/tover0314-w/opentypeless)、[light-whisper](https://github.com/sypsyp97/light-whisper)、[Whisper-Input-Next](https://github.com/Mor-Li/Whisper-Input-Next)。
- [vocotype-cli](https://github.com/233stone/vocotype-cli)（Python）。
- [FluidVoice](https://github.com/altic-dev/FluidVoice)（11.7k，仅 macOS）。

## 2. 最值得读的 3 个项目

1. **Handy**，Windows 插入、热键和浮层的工程细节最好：
   - [paste_tx/windows.rs](https://github.com/cjpais/Handy/blob/HEAD/src-tauri/src/paste_tx/windows.rs) 和 [paste_tx/mod.rs](https://github.com/cjpais/Handy/blob/HEAD/src-tauri/src/paste_tx/mod.rs)
   - [clipboard.rs](https://github.com/cjpais/Handy/blob/HEAD/src-tauri/src/clipboard.rs)、[input.rs](https://github.com/cjpais/Handy/blob/HEAD/src-tauri/src/input.rs)
   - [handy-keys 的 windows/listener.rs](https://github.com/handy-computer/handy-keys/blob/HEAD/src/platform/windows/listener.rs)
   - [overlay.rs](https://github.com/cjpais/Handy/blob/HEAD/src-tauri/src/overlay.rs)
   - prompt 和 LLM 调用：[settings.rs](https://github.com/cjpais/Handy/blob/HEAD/src-tauri/src/settings.rs)、[actions.rs](https://github.com/cjpais/Handy/blob/HEAD/src-tauri/src/actions.rs)、[llm_client.rs](https://github.com/cjpais/Handy/blob/HEAD/src-tauri/src/llm_client.rs)
2. **OpenWhispr**，Windows 粘贴、读选区、prompt：
   - [windows-fast-paste.c](https://github.com/OpenWhispr/openwhispr/blob/HEAD/resources/windows-fast-paste.c)、[windows-key-listener.c](https://github.com/OpenWhispr/openwhispr/blob/HEAD/resources/windows-key-listener.c)
   - [clipboard.js](https://github.com/OpenWhispr/openwhispr/blob/HEAD/src/helpers/clipboard.js)、[selectionManager.js](https://github.com/OpenWhispr/openwhispr/blob/HEAD/src/helpers/selectionManager.js)、[selectionEditing.js](https://github.com/OpenWhispr/openwhispr/blob/HEAD/src/helpers/selectionEditing.js)
   - [prompts.json](https://github.com/OpenWhispr/openwhispr/blob/HEAD/src/locales/en/prompts.json)
3. **CapsWriter-Offline**，唯一的 Python + Windows + 中文参考：
   - [shortcut_manager.py](https://github.com/HaujetZhao/CapsWriter-Offline/blob/HEAD/core/client/shortcut/shortcut_manager.py)、[text_output.py](https://github.com/HaujetZhao/CapsWriter-Offline/blob/HEAD/core/client/output/text_output.py)、[LLM/default.py](https://github.com/HaujetZhao/CapsWriter-Offline/blob/HEAD/LLM/default.py)、`core/client/hotword/`
   - **写粘贴代码之前先读 issue** [#79](https://github.com/HaujetZhao/CapsWriter-Offline/issues/79)、[#426](https://github.com/HaujetZhao/CapsWriter-Offline/issues/426)、[#371](https://github.com/HaujetZhao/CapsWriter-Offline/issues/371)、[#443](https://github.com/HaujetZhao/CapsWriter-Offline/issues/443)。

prompt 方面再看：
- VoiceInk [AIPrompts.swift](https://github.com/Beingpax/VoiceInk/blob/HEAD/VoiceInk/Core/Enhancement/AIPrompts.swift)
- OpenLess [style_packs.rs](https://github.com/Open-Less/openless/blob/HEAD/openless-all/app/crates/openless-core/src/style_packs.rs)
- FreeFlow [PostProcessingService.swift](https://github.com/zachlatta/freeflow/blob/HEAD/Sources/PostProcessingService.swift)
- amical [formatter-prompt.ts](https://github.com/amicalhq/amical/blob/HEAD/apps/desktop/src/pipeline/providers/formatting/formatter-prompt.ts)

Windows 插入的更多细节：
- SayIt [inject/mod.rs](https://github.com/crosswk/SayIt/blob/HEAD/client/src-tauri/src/inject/mod.rs)
- amical [AccessibilityService.cs](https://github.com/amicalhq/amical/blob/HEAD/packages/native-helpers/windows-helper/src/Services/AccessibilityService.cs)

## 3. 落到我们实现上的教训（按模块）

### 3.1 热键（M1，`win/hotkey.py`）
- 低级钩子放在独立线程，自带消息循环，回调里只往队列里放事件。回调超过约 1 s，Windows 会静默摘掉钩子（[文档](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelkeyboardproc)）；Python 有 GIL，这个风险是真实存在的。
- 做健康检查；**睡眠唤醒、锁屏解锁后重新安装钩子，并重新读取修饰键的真实状态**（Handy [#1620](https://github.com/cjpais/Handy/issues/1620)）。如果 Python 实在压不住，退路是一个极小的 C 助手进程（OpenWhispr 的做法）。
- 用 `LLKHF_INJECTED` 标记区分自己注入的按键；自己维护按键状态，过滤自动重复。
- 吞掉 Win 或 Alt 组合时，**先发一个未分配的虚拟键 0xE8 做遮罩**，否则会弹开始菜单或激活菜单栏（Handy [#917](https://github.com/cjpais/Handy/issues/917)）。在 VS Code 里，基于 Alt 的热键还会把焦点移到菜单（OpenLess [#648](https://github.com/Open-Less/openless/issues/648)）。**这正是我们默认用右 Alt 要重点测的地方。**
- 备选默认热键：**按住 CapsLock，点按不到 0.3 s 时放行成普通 CapsLock**（CapsWriter）。在中文用户里久经验证，也避开了 Alt/Win 的坑。

### 3.2 插入文字（M1，`win/inject.py`）
- **等物理修饰键全部松开**（每 10 ms 轮询一次，最多 500 ms，opentypeless 的做法），然后**用一次 `SendInput` 调用发出 Ctrl+V 的全部 4 个事件**。
  - 一次调用的事件不会被别的输入插进来（[SendInput 文档](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)）。
  - 分几次调用发，很可能就是 CapsWriter “中文输入法下只上屏一个 v” 的原因（#79、#426）。这一点是推断，未验证。
  - 补发修饰键的 key-up 时，用区分左右的虚拟键码（`VK_LCONTROL` / `VK_RMENU` 等），见 amical。
  - 热键修饰键没松开就发 Ctrl+V，会变成 Ctrl+Alt+V（Handy [#2051](https://github.com/cjpais/Handy/issues/2051)）。
- **按目标程序选择插入方式**：
  - 经典 Edit 控件：直接给控件发 `WM_PASTE` 消息，不经过键盘，输入法完全不会干扰（SayIt）。
  - Windows Terminal、mintty：发 Ctrl+Shift+V（OpenWhispr）。
  - 老式控制台（conhost）：发 `WM_SYSCOMMAND` 的粘贴命令 0xFFF1，全屏的终端程序里也能用（SayIt）。
  - 按 exe 名覆盖；注意微信 4.x 的进程名是 `Weixin.exe`。
- **剪贴板**：
  - 备份全部格式，不只是文本。
  - 写入那 3 个“不进剪贴板历史”的格式（[文档](https://learn.microsoft.com/en-us/windows/win32/dataxchg/clipboard-formats)）。
  - `OpenClipboard` 被别的程序占用时要重试。剪贴板历史本身就会占着剪贴板（OpenLess [#1024](https://github.com/Open-Less/openless/issues/1024)）；国产安全软件也可能拦截写入（SayIt 会提示是哪个软件）。
  - 只有当剪贴板序号（`GetClipboardSequenceNumber`）还是我们写入时的那个，才恢复。
  - 连续快速听写时，要恢复的是**用户最初的内容**，而不是上一次听写的结果（OpenLess [#167](https://github.com/Open-Less/openless/issues/167)）。
  - **不要用固定的 100 ms 定时器恢复**，Outlook 会贴出上一次的结果（OpenWhispr [#118](https://github.com/OpenWhispr/openwhispr/issues/118)）。
  - 最佳方案是 Handy 的 “reliable paste”（延迟渲染）：往剪贴板放一个占位，等目标程序真的来读（`WM_RENDERFORMAT`）时才给出文本。“被读取”就是粘贴成功的证据；最后一次读取 200 ms 后（最多 8 s）恢复。可以在 M2 或 M5 用 ctypes 实现。
- 在热键按下时记住前台窗口和焦点控件；粘贴前如果焦点变了，先切回去，或者退化为“已复制，请手动粘贴”（OpenWhispr [#859](https://github.com/OpenWhispr/openwhispr/issues/859)）。
- **提权窗口**：`SendInput` 被 UIPI 拦截时，返回值里看不出来。要先检查目标进程是否提权（Handy [#434](https://github.com/cjpais/Handy/issues/434)、[#677](https://github.com/cjpais/Handy/issues/677)）。
- 发出了 Ctrl+V 不等于真的插入成功（OpenLess [#20](https://github.com/Open-Less/openless/issues/20)）。能用 UI Automation 读回输入框内容做确认的地方就确认一下。
- OpenWhispr [#829](https://github.com/OpenWhispr/openwhispr/issues/829)：Windows 11 上超过约 200 字的文本会静默粘贴失败，原因不明。**M1 的手动测试里要有长文本。**
- 逐字流式输入（`KEYEVENTF_UNICODE`）：
  - 做法是每 12 ms 发约 16 个字符；emoji 要拆成两个 UTF-16 单元（vocotype-cli 这里写错了）；最后要和目标文本核对。
  - OpenLess 声称这种输入不会被 TSF 输入法截获（**未验证**）。
  - CapsWriter 的逐字模式在 Win11 记事本和千牛里出现乱码（#371、#443），所以要维护一份“这些程序强制用粘贴”的名单。
  - **我们默认仍然用粘贴**，逐字输入只是可选项。

### 3.3 读取选中文字（M3，`win/uia.py`）
- 优先用 UI Automation 读选区。
- 兜底流程：
  1. 往剪贴板写一个随机标记串；
  2. 发 **Ctrl+Insert**（不用 Ctrl+C，避免在控制台里触发中断，amical 的做法）；
  3. 每 20 ms 查一次，最多约 1.2 s；
  4. 恢复剪贴板（OpenWhispr）。
- 什么都没选时，VS Code、JetBrains、Notepad++ 会复制**整行**。复制结果是“一整行 + 换行”这种形态时，要当作没有选中（OpenWhispr）。
- 改写选区时，prompt 用 JSON 传入 `{spokenInstruction, selectedText}`，并要求输出以一个结束标记收尾，用来发现被截断的回复（OpenWhispr [selectionEditing.js](https://github.com/OpenWhispr/openwhispr/blob/HEAD/src/helpers/selectionEditing.js)）。
- macOS 上的 FreeFlow 在 Electron/Chromium 应用里读不到选区，编辑模式会覆盖掉选中内容（[#237](https://github.com/zachlatta/freeflow/issues/237)）。**读不到选区时绝不能执行替换。**

### 3.4 上下文（M1 起步，M3 增强）
- 低成本的上下文：exe 名、窗口标题、浏览器地址栏的 URL（Tambourine 通过 UIA 读取）、光标前后 300–500 个字符（amical）。
- 这些内容要转义、限长，并告诉模型“不要照抄上下文”。OpenLess 会转义转写文本里的标签，并把长度限制在 16k 字符。
- 更重的做法：FreeFlow 在说话期间截图，交给视觉模型总结“用户在做什么”。放在 P3。

### 3.5 录音（M1，`audio/`）
- `sounddevice`，不启用自动增益。OpenWhispr 用的 Chromium AGC 会把 Windows 麦克风音量调低（[#476](https://github.com/OpenWhispr/openwhispr/issues/476)）。
- **按下即开麦，并配一个预录缓冲**。OpenWhispr 修好之前一直丢开头 1–2 s（[#845](https://github.com/OpenWhispr/openwhispr/issues/845)）。
  折中方案：用完后麦克风再保持打开约 30 s，这样连续听写时不用重新打开。
- 静音时别把音频送去识别。Whisper 会把 prompt（词典）原样吐出来（OpenWhispr [#851](https://github.com/OpenWhispr/openwhispr/issues/851)），也会编造“感谢观看”之类的内容（[#462](https://github.com/OpenWhispr/openwhispr/issues/462)）。
- 格式：OpenWhispr 转成 WAV，是因为 Azure 的 MAI-Transcribe 经 OpenRouter 时**拒收 WebM**。我们实测 **OGG/Opus 可以被 gpt-transcribe 和 mai-transcribe-2 接受**（docs/models.md）。以后换备用模型时要先验证格式。AssemblyAI 只收 WAV，gpt-audio-mini 只收 wav/mp3。

### 3.6 Prompt（已部分吸收进 `prompts/dictation.md`）
各家的共性（我们都已具备）：
- 自我定位为“文本过滤器 / 格式整理器，不是助手”，例如 “THE SPEAKER IS NEVER TALKING TO YOU”（OpenWhispr）、“千万不要以为用户在和你对话”（CapsWriter）；
- 转写文本放在标签里；问句和命令都按内容处理，并配上示例；
- 自我修正只保留最后的意图；
- 只输出文本；静音时输出空；
- 保持原语言；有术语表；temperature 0；关闭 reasoning。

吸收进来的：
- 句尾语气词（好啊、吧、呢）保留，只删真正的语气填充（ququ）；
- 被写成中文谐音的英文术语要还原，如 克劳德 → Claude（OpenLess）；
- 版本号原样保留（OpenLess）；
- 代码层面的输出兜底：`pipeline.guard()` 把占位符变成空，把“远长于原文”的输出退回原始转写。

以后可以考虑：
- **长度约束**：±20%（OpenLess），或者“短句保持短”（VoiceTypr）。
- **结构化输出**：用 JSON schema 只返回一个 `transcription` 字段，并去掉 `<think>`（Handy）。
- **三明治提示**：转写文本之后再重复一句“只输出整理后的文本”（OpenWhispr）。
- **开发者语法**：口述的 “dash dash fix” 转成 `--fix`（FreeFlow）；“编程点 MD” 转成 “编程.md”（CapsWriter）。
- **词典映射**：支持 “ant row pick = Anthropic” 这种写法（Tambourine）。
- **按拼音相似度匹配热词**：≥ 0.85 直接替换，0.6–0.85 作为候选交给 LLM（CapsWriter）。
- **短句去掉句末标点**（CapsWriter）。聊天场景里我们交给 prompt 处理。
- 不要学 Tambourine 的 “Begin with a concise checklist”，它和“只输出文本”相矛盾。
- VoiceInk 出现过整理时把中文变成英文的“语言漂移”（[#876](https://github.com/Beingpax/VoiceInk/issues/876)）。我们有“不要翻译”的规则，评测里也覆盖了中文用例。

### 3.7 词典自动学习（P3）
OpenWhispr 在粘贴后用 UIA 监视输入框（[windows-text-monitor.c](https://github.com/OpenWhispr/openwhispr/blob/HEAD/resources/windows-text-monitor.c)），从用户的修改里学习新词。Typeless 也有同样的功能。

### 3.8 打包（M5）
PyInstaller 单文件打包，再加上钩子和 `SendInput`，很容易被杀毒软件误报（Handy [#1891](https://github.com/cjpais/Handy/issues/1891)、CapsWriter #146）。应对：打成文件夹、不用 UPX、给 exe 签名。另外 CapsWriter [#153](https://github.com/HaujetZhao/CapsWriter-Offline/issues/153) 报告过重度使用后微信强制重新登录（原因未确认），需要留意。

## 4. 未验证的点
- OpenWhispr #829（长文本粘贴失败）和 CapsWriter #153（微信重新登录）的根因。
- “一次 `SendInput` 发完 Ctrl+V 能修好输入法下只出一个 v 的问题”：只是根据 VoiceTypr 的注释和 SendInput 文档推断的。
- OpenLess 说 Unicode 逐字输入不会被 TSF 截获。
- Whispering 自身的 star 数（它现在属于 Epicenter monorepo）。
