# 架构设计

> 本文保留早期架构设计。Windows 核心与 Glass 界面已经实现，Android 也已加入；文中标注未来里程碑的模块不一定实际采用。当前功能见 README，实际模块以源码为准。

## 1. 技术选型

| 关注点 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.12 + uv | 本机已有；迭代和评测脚本最快；Win32 API 用 `ctypes` 直接调 |
| UI | PySide6（Qt 6） | 托盘、无焦点浮层、设置/历史窗口放在同一个事件循环里；LGPL |
| 录音 | `sounddevice`（PortAudio/WASAPI）+ `numpy` | 16 kHz 单声道 int16，回调里算音量 |
| 编码 | `soundfile`（libsndfile 1.2.2） | 内存里直接编码 OGG/Opus，已验证 Windows wheel 支持 |
| HTTP | `httpx` | 同步 + 流式；显式传代理；keep-alive |
| 热键 / 粘贴 / 剪贴板 / 前台窗口 | `ctypes` 调 user32 / kernel32 | 不引入 pywin32；需要的 API 很少 |
| UI Automation（M3，读选中文字） | `comtypes` + UIAutomationCore | 不走剪贴板就能读选区 |
| 存储 | TOML 配置 + SQLite 历史（标准库） | 可以手改；零依赖 |

**依赖只在用到的那个里程碑才加**（`uv add`），不要提前把整张表装进去。

## 2. 进程与线程模型

```
┌──────────────── 一个进程 ────────────────────────────────────────────────┐
│ Qt 主线程：托盘 / 浮层 / 设置窗口 / 状态机（唯一能碰 Qt 控件的线程）      │
│    ▲ Qt signal（跨线程 queued）                                           │
│    │                                                                      │
│ 热键线程：WH_KEYBOARD_LL 钩子 + GetMessage 循环（回调里只做判断和转发） │
│ 音频线程：PortAudio 回调 → 帧队列 + RMS 音量                              │
│ 工作线程池：pipeline（ASR → 润色），网络 I/O                              │
└──────────────────────────────────────────────────────────────────────────┘
```

- **钩子回调必须微秒级返回**。它持有 GIL；如果别的线程长时间占着 GIL（大循环、同步编码大文件），
  会造成**全系统键盘卡顿**，超过 `LowLevelHooksTimeout` 后 Windows 还会静默摘掉钩子。
  numpy 或 soundfile 调用会释放 GIL，可以放心用，但不要写逐采样点的纯 Python 循环。
- 工作线程通过 signal 回主线程；主线程不做阻塞 I/O。

## 3. 状态机

```
IDLE ──热键按下──▶ RECORDING ──松开 / 再按一次 / 到最长时长──▶ PROCESSING ──▶ INSERTING ──▶ IDLE
  ▲                  │ Esc / 太短(<300ms) / 静音                  │ Esc          │
  └──────────────────┴──────────────────── CANCELLED / ERROR ◀────┴──────────────┘
```

- 每次会话在**按下热键那一刻**抓取：前台窗口句柄、进程名、窗口标题、模式（听写 / 指令 / 翻译）。
- PROCESSING 期间再按热键：M1 先忽略并闪一下浮层；以后再考虑排队。
- 整个会话有唯一 id，用来关联日志、历史记录、耗时。

## 4. 各模块职责（目标目录结构）

```
src/local_typeless/
  cli.py            # 入口：无子命令启动 app；file / polish 是开发命令
  config.py         # TOML 配置（%APPDATA%/local-typeless/config.toml）
  openrouter.py     # OpenRouter 客户端：STT + 流式 chat，代理、预热、keep-alive、重试、超时
  models.py         # 各模型的请求预设 + provider 路由（延迟优先 / 隐私）
  pipeline.py       # 流水线：音频 → ASR → 整理或翻译 → 文本（无 UI、同步）
  prompts/          # dictation.md / translate.md（M3：command.md）+ 构造 messages
  app.py            # 控制器：状态机 + 各组件编排
  hotkeys.py        # 热键状态机（纯逻辑）；keys.py：键码与键名
  audio.py          # 录音（WASAPI）、边录边编码 Opus、静音检测；FileAudio
  sounds.py         # 提示音
  win/              # _api.py（ctypes 声明）、keyboard_hook.py、inject.py（剪贴板 + SendInput）、
                    # clipboard.py、foreground.py（进程名/标题/是否提权）、(M3) uia.py（选区）
  ui/               # (M2) tray.py、overlay.py、settings.py、history.py
  store.py          # (M4) SQLite 历史与用量统计
```

## 5. 关键流程与 Windows 细节

### 5.1 热键（`win/hotkey.py`）
- 用 `SetWindowsHookExW(WH_KEYBOARD_LL)` 在专用线程里挂钩，才能拿到**按下和松开**（按住说话需要），也能识别**只按修饰键**的组合（比如按住右 Alt）。
- 自己的 `SendInput` 事件带 `LLKHF_INJECTED` 标志，钩子里要忽略，防止自触发。自己维护按键状态，过滤自动重复。
- 吞掉 Alt 或 Win 时，先注入一个未分配的虚拟键 **0xE8** 做遮罩（Handy #917、AutoHotkey 同理），否则会激活菜单栏或弹出开始菜单。
  VS Code 里 Alt 类热键会把焦点移到菜单，这一点要专门测（OpenLess #648）。
- 被我们用掉的按键要吞掉（回调返回 1），不能漏给前台程序。但单独按修饰键、没有构成热键时，必须原样放行。
- 钩子健康检查：**睡眠唤醒、锁屏解锁后重新安装钩子，并重新读取修饰键的真实状态**（Handy #1620）。
- 默认热键见 `docs/product-spec.md`，全部可在配置里改。备选方案：按住 CapsLock，点按放行（CapsWriter 的做法，见 references §3.1）。

### 5.2 录音（`audio/recorder.py`）
- 在热键**按下时**打开 `InputStream(16000, mono, int16, blocksize=800)`（50 ms 一块），不启用任何自动增益。要实测按下到拿到第一帧的时间。
  OpenWhispr 就吃过亏：修好之前一直丢开头 1–2 s（#845）。
  如果开流太慢，退路是用完后麦克风再保持打开约 30 s，这样连续听写时是热的。
  不采用一直常开：Windows 会一直显示“麦克风使用中”。
- 回调里只做 `queue.put(frame)` 和算 RMS；RMS 以约 30 fps 推给浮层画波形。
- **边录边编码**：用一个消费线程把帧写进 `soundfile.SoundFile(BytesIO, 'w', 16000, 1, format='OGG', subtype='OPUS')`。
  实测（本机）：
  - 一次性编码 60 s 的 Opus 要 **608 ms**，10 s 要 95 ms；
  - 增量写入每 50 ms 一块只要 0.5 ms，停止时 `close()` 只要 0.4 ms。

  所以绝不能等录完再编码。
- 开头的静音可以在编码前裁掉：先缓冲，等检测到第一块有声音的帧，再从它之前 200 ms 开始写。结尾的静音不裁，影响很小。
- 录音结束后，如果全程 RMS 都低于阈值，判定为静音：直接取消，不调 API，避免 Whisper 类模型对着静音“幻觉”出文字。
- 录音时长 < 300 ms 视为误触。最长时长做成可配置项，默认 6 分钟。上游单次处理超时 60 s，长录音要切片（见 §6）。

### 5.3 插入文字（`win/inject.py`）
默认路径：
1. 备份剪贴板（**全部格式**）；`OpenClipboard` 被占用时重试。
2. 写入 `CF_UNICODETEXT`，同时写入 `ExcludeClipboardContentFromMonitorProcessing`、`CanIncludeInClipboardHistory=0`、
   `CanUploadToCloudClipboard=0` 三种注册格式，不让听写内容进入 Win+V 剪贴板历史和云剪贴板。
3. 等用户松开全部物理修饰键：用 `GetAsyncKeyState` 每 10 ms 查一次，最多 500 ms。
4. **一次 `SendInput` 调用发出 Ctrl+V 的 4 个事件**。一次调用不会被其他输入插进来；分开发很可能就是 CapsWriter
   “中文输入法下只上屏一个 v”的原因。仍被按住的修饰键，就在同一次调用里用区分左右的虚拟键码补发 key-up。
5. 恢复剪贴板：只有当剪贴板序号还是我们写入时的那个，才恢复。
   - 不要用固定的短定时器恢复（Outlook 会贴出上一次的内容，OpenWhispr #118）。
   - 连续快速听写时，要恢复的是用户最初的内容。
   - **目标方案**是 Handy 的延迟渲染：放一个占位，等目标程序读取（`WM_RENDERFORMAT`）时才给出数据，并以此确认粘贴成功。
     M1 先做“序号检查 + 500 ms”，延迟渲染放到 M2 或 M5。

按目标程序覆盖（按 exe 名 / 窗口类名）：
- 经典 Edit 控件：直接发 `WM_PASTE` 消息，不经过键盘，输入法不会干扰。
- Windows Terminal、mintty：发 Ctrl+Shift+V。
- 老式控制台：发 `WM_SYSCOMMAND` 的粘贴命令 0xFFF1。

具体做法见 references §3.2。

其他：
- 粘贴前确认焦点还在按下热键时的那个窗口。变了就先切回去，或者退化为“已复制，请手动粘贴”。
- **提权窗口**（以管理员运行的程序）会被 UIPI 拦掉 `SendInput`，而且**返回值里看不出来**。先检测目标进程是否提权，
  是的话退化为“结果留在剪贴板 + 浮层提示手动粘贴”。
- 可选的“逐字输入”模式（`SendInput` + `KEYEVENTF_UNICODE`）：给不吃 Ctrl+V 的程序用。
  它在部分程序里会乱码（CapsWriter 在 Win11 记事本、千牛里出过问题）；会不会被 TSF 输入法截获说法不一，未验证。
  所以不做默认路径，只给一个“这些程序强制用某种方式”的名单。
- 超过约 200 字的长文本在 Windows 11 上有静默粘贴失败的报告（OpenWhispr #829，原因不明），手动测试要覆盖长文本。
- 提供“重新粘贴上一次结果”热键和托盘菜单项，作为万一贴丢时的兜底。

### 5.4 读取选中文字（M3，`win/uia.py` + 剪贴板兜底）
- 优先走 UI Automation：焦点元素的 `TextPattern.GetSelection()`，不碰剪贴板。
- 兜底流程：
  1. 备份剪贴板，再写入一个随机标记串；
  2. 发 **Ctrl+Insert**（不用 Ctrl+C，避免在控制台里触发中断）；
  3. 每 20 ms 查一次序号，最多约 1.2 s；
  4. 读取内容，然后恢复剪贴板。

  判定为“没有选中文字”的情况：内容还是标记串，或者是“一整行 + 换行”——VS Code、JetBrains、Notepad++ 在没有选区时会复制整行。
- **读不到选区时绝不执行替换**，而是退化为问答（结果卡片）。FreeFlow #237 就是在读不到选区时把内容覆盖掉了。

### 5.5 上下文（`win/foreground.py`）
- 按下热键时读取 `GetForegroundWindow` → 进程 exe 名（`QueryFullProcessImageNameW`）+ 窗口标题，开销很小。
- 进程名 → 应用类别（聊天 / 邮件 / 代码 / 终端 / 文档 / 浏览器）：内置一张表，用户可覆盖。
  浏览器再用窗口标题里的关键词细分（Gmail、Outlook、Slack、飞书……）。
  类别和用户为这个类别写的风格说明会放进 prompt 的 `<context>`。
- 以后可选：用 UIA 读光标前的文字，处理续写时的大小写和标点衔接。

### 5.6 浮层（`ui/overlay.py`）
- 无边框、半透明、置顶、**不抢焦点**。Qt 标志：`FramelessWindowHint | WindowStaysOnTopHint | Tool | WindowDoesNotAcceptFocus`，
  属性：`WA_TranslucentBackground | WA_ShowWithoutActivating | WA_TransparentForMouseEvents`。
  再用 `SetWindowLongPtrW` 补上 `WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW`。
- 永远不要调用 `activateWindow()` / `raise_()`。要有测试：显示浮层前后 `GetForegroundWindow()` 不变。
- 位置：前台窗口所在显示器的底部居中，任务栏上方。状态：录音（波形）/ 处理中 / 完成（一闪）/ 错误（红字 2 s）/ 已取消。

## 6. 延迟预算（目标：松开热键到文字上屏 p50 ≤ 1.5 s，10 s 左右的语音）

端到端实测（`tools/e2e_dictation.py`，9 s 中文样例，2026-09-23，5 次运行）：**停止后 1.56–2.41 s 上屏**，其中 ASR 1.0–1.7 s，润色 0.5–1.2 s。

| 阶段 | 当前实测 | 手段 |
|---|---|---|
| 开麦（按下热键时） | WASAPI 约 0.11–0.12 s；进程内首次偶尔约 0.5 s | 启动时后台预热一次；开麦完成后才放“开始”提示音（Typeless 同样要求听到提示音再说） |
| 停止录音 + Opus 编码 | 关流约 40 ms，编码收尾 < 1 ms | 录音过程中边录边编（一次性编码 60 s 要 608 ms） |
| 建连 | 0（已预热）/ 冷连接 ~0.7 s | **按下热键时 `warm_up()`**，keep-alive 120 s |
| ASR（gpt-transcribe） | ~0.9–1.2 s | 上传 Opus，不传 WAV |
| 润色（deepseek-v4.1-flash） | ~0.5–0.7 s（p90 偶发 4 s） | reasoning 关闭；`sort=latency`；**对冲请求**（TTFT > 1.5 s 时并行发备用模型） |
| 粘贴 | ~50–100 ms | |

后续优化（按收益排序，每一项都要先测量）：
1. 对冲请求，砍掉润色的长尾。
2. 长录音**边说边转**：录音过程中在静音处切出已完成的片段，并行送 ASR，松开时只剩最后一段要转，延迟不再随时长增长。这也顺带绕开了 60 s 的上游超时。
3. 短而干净的句子跳过润色，直接用 ASR 结果（gpt-transcribe 自带标点）。需要先评测误伤率。

## 7. 隐私与安全
- API key 只从环境变量 `OPENROUTER_API_KEY` 读，**永不写盘、永不进日志**。日志里的请求体要去掉音频 base64。
- 默认 `provider.data_collection = "deny"`，可选 `zdr = true`。
- 音频默认不落盘。历史记录只存在本地 SQLite，可在设置里关闭。
- 听写内容不进入 Windows 剪贴板历史（见 §5.3）。

## 8. 配置与数据位置
- `%APPDATA%\local-typeless\config.toml`：用户配置（`LOCAL_TYPELESS_CONFIG` 可覆盖路径）
- `%APPDATA%\local-typeless\history.sqlite`：历史 / 用量（M4）
- `%APPDATA%\local-typeless\logs\`：滚动日志（M1）

## 9. 运行与自启（M5）
- 开发：`uv run local-typeless`
- 日常：在 `[project.gui-scripts]` 里加一个无控制台入口，`uv` 会在 `.venv\Scripts\` 生成对应的 exe；在 `shell:startup` 放它的快捷方式实现开机自启。
- 以后如有需要再做 PyInstaller / Nuitka 打包。注意：单文件打包再加上钩子和 `SendInput` 容易被杀毒软件误报（Handy #1891），
  所以打成文件夹、不用 UPX、最好签名。
