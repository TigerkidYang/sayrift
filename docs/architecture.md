# Sayrift 架构（v0.2.1）

2026-10-06 按发布源码核对。Windows 安装包和 Android APK 已正式发布；本文描述实际实现，替代早期里程碑规划。验证结果见 [构建核验](binary-release.md)，平台与升级限制见 [兼容性](compatibility.md)。

## 1. 技术选型

| 范围 | 实际实现 |
| --- | --- |
| Windows | Python 3.12、uv、PySide6；Win32 调用统一在 `win/`，使用 ctypes。 |
| Windows 音频 / 网络 | sounddevice / PortAudio / WASAPI、numpy、soundfile / libsndfile；httpx 流式 chat 与同步 STT。发布音频 DLL 从固定 libsndfile / Ogg / Opus 源码构建。 |
| Android | Kotlin、Compose、无障碍服务、麦克风前台服务；MediaRecorder 编码 OGG/Opus，OkHttp 调模型。 |
| 存储 | Windows：TOML 与 SQLite；Android：偏好设置与 SQLite，key 用 Keystore 加密。 |
| 共用部分 | Android 构建时复制 `src/local_typeless/prompts/*.md`；Python / Kotlin 分别实现流水线与输出兜底。 |

没有采用早期规划中的 `comtypes` / `win/uia.py`。分级热词库实验未纳入此版本。

## 2. 进程与线程模型

Windows Qt 主线程负责控件。`ui/qt.py` 启动独立 controller 线程运行 `App.run()`，控制器拥有会话状态；键盘钩子线程处理按键状态并排队事件。PortAudio 回调提供音频帧与音量，编码线程增量写入 Opus；pipeline 工作线程处理网络，结果回控制器，再通过 Qt 信号更新界面。主线程不执行模型请求，钩子回调必须立即返回。

Android 会话状态与界面在主线程处理，网络在后台 executor。每次会话持有请求取消对象，预热单独执行。取消或服务失效会取消底层 OkHttp Call，并阻止失效结果插入及后续模型调用，详见 [取消流程](android-cancellation.md)。

## 3. 状态机与模式

主状态为 `IDLE → RECORDING / LISTENING → PROCESSING → IDLE`，取消、静音、错误也返回空闲。默认录音上限 9 分钟，Windows 可配置，最后 60 秒倒计时。

- 听写：ASR → 忠实整理 → 插入。转写是数据；过长输出退回原转写，空占位输出归零。
- 翻译：输出有序目标列表的第一个语言，关闭听写长度兜底。
- Ask：可用选区加语音指令 → 替换 / 插入 / 答案动作。解析失败显示卡片，读不到选区不执行替换。

Windows 用会话 ID 排除取消后的旧结果。Android 另核对输入框标识 / 输入会话，换输入框后用卡片取回结果。取消不能撤销供应商已产生的费用，本地用量也可能不完整。

## 4. 模块职责

| 位置 | 职责 |
| --- | --- |
| `app.py`、`hotkeys.py` | Windows 控制器与可测试的热键状态机。 |
| `audio.py`、`pipeline.py`、`openrouter.py`、`prompts/` | 录音、无 UI 流水线、HTTP / 超时 / 降级、三种模式提示词。 |
| `win/` | 键盘钩子、前台窗口、剪贴板粘贴、选区读取、自启、安装与快捷方式。 |
| `ui/`、`store.py` | Glass 主窗口、浮条、卡片、托盘、引导、历史 / 用量与保留期。 |
| `android/core/` | Kotlin 流水线、提示词、模型请求和取消，JVM 测试使用模拟服务器。 |
| `android/app/` | 无障碍输入、浮层、麦克风服务、录音、偏好设置 / Keystore、历史与 Compose 页面。 |
| `packaging/`、`tools/` | 安装器入口、构建与制品核验；Android release 需要显式签名凭据。 |

Windows 模块位于 `src/local_typeless/`，保留内部旧名以兼容升级。

## 5. 输入与录音的关键流程

### 5.1 热键

Windows 低级键盘钩子运行在专用线程，过滤注入事件。吞掉 Alt / Win 时注入遮罩键 0xE8，避免菜单被激活。听写默认右 Alt（点按或按住），翻译右 Alt + 右 Shift，Ask 右 Alt + 空格，Esc 取消。见 [行为规格](product-spec.md)。

### 5.2 录音

Windows 使用 WASAPI，后台预热降低首次开麦延迟；16 kHz 单声道、24 kbps OGG/Opus，边录边编码，过短 / 静音不送识别。Android 使用麦克风前台服务与 MediaRecorder 输出 OGG/Opus；正常停止 / 取消删除临时缓存，崩溃可能留下文件。

### 5.3 插入与剪贴板

Windows `win/inject.py` 备份剪贴板，写入结果及排除剪贴板历史 / 云同步的标记，等待物理修饰键释放，一次 SendInput 发送完整组合。经典 Edit 用 WM_PASTE，终端用 Ctrl+Shift+V，旧控制台用系统粘贴命令。

实际恢复方案为默认 0.8 秒计时器加序号检查，未被其他程序修改时恢复；连续粘贴保留最初快照。未实现延迟渲染确认。目标窗口切换时尝试恢复原窗口；无法恢复或权限阻止时报告失败并提供卡片，部分失败路径留下结果在剪贴板。返回成功不保证所有应用接受文本。

Android 13+ 优先使用无障碍 InputConnection，与当前键盘并存；旧系统或无连接时尝试无障碍文本动作。失败显示卡片供主动复制，不再自动剪贴板粘贴。密码框隐藏把手。

### 5.4 读取选区

Windows `win/selection.py` 使用剪贴板往返：备份、随机探针、Ctrl+Insert、等待序号变化并读取、恢复。无新内容或特定编辑器复制整行时判定无选区。UI Automation 是未实现的改进方向。

Android 通过可用输入连接 / 无障碍节点读取选区，目标应用必须允许读取。Ask 真机选区与特殊应用仍需按 [手动清单](manual-tests.md)记录结果。

### 5.5 上下文

Windows 捕获开始说话时的窗口、进程名与标题；Android 记录目标应用与输入框。每次变化的上下文、词典、转写和选区放 user 消息，稳定设置留 system 消息。个人词典注入支持提示的 ASR 和整理模型。

### 5.6 界面

Windows Voice bar 置顶、不激活窗口，按钮可点击，整个浮条不是鼠标穿透窗口。主窗口、浮条、卡片、托盘与引导使用 Glass 风格。Android 边缘把手与卡片由无障碍服务管理，录音通知可停止会话。

## 6. 网络与延迟

开始录音时预热连接。ASR 超时随音频大小增长；Windows 文本请求使用首字超时（整理默认 6 秒、Ask 8 秒），Android 使用完整调用时限。失败或超时顺序切备用模型，没有实现并行对冲或边录边 ASR。

早期 Windows E2E 曾测得停止后约 1.6–2.4 秒上屏，这是特定样例、网络和模型的历史测量，不是 v0.2.1 新测量或性能保证。见 [models.md](models.md)。

## 7. 隐私与历史

录音、文本、词典、应用上下文与 Ask 选区可发给 OpenRouter / 模型供应商。默认 `data_collection=deny`，Windows 可另启用 ZDR；路由过滤不等于零留存保证。

Windows 默认保存本地文字及录音以便重试，可关闭音频或历史；Android 只保存文字历史。历史 SQLite 未加密；访问时执行保留期，独立数字用量不随历史删除。清理不保证物理安全擦除。见 [Windows 保留期](history-retention.md)、[Android 存储](android-history-privacy.md)。

Windows key 从 `OPENROUTER_API_KEY` 读取，不写配置；Android key 在 App 填写，经 Keystore 加密。默认日志不记录用户文本，API 异常不保留响应正文。

## 8. 数据位置与升级身份

Windows 默认 `%APPDATA%\local-typeless`；`SAYRIFT_CONFIG` 优先于旧 `LOCAL_TYPELESS_CONFIG`，历史位于配置旁。Android 包名仍为 `app.localtypeless.android`，内部存储标识保持兼容。

正式 Android APK 使用发布证书，不能覆盖旧个人 debug 签名安装。需要保留旧数据时不要直接卸载绕过限制。见 [compatibility.md](compatibility.md)。

## 9. 启动与分发

公开源码：`uv sync --locked`，然后 `uv run sayrift`；无控制台入口 `uv run sayrift-gui`。主窗口关闭隐藏到托盘，开机自启使用 Windows 注册设置与 `--minimized`。

Windows PyInstaller 文件夹负载由图形安装器按用户安装，不用 UPX；`uv run python tools/build_installer.py` 构建。v0.2.1 EXE 未代码签名。Android release 经 R8 / 资源压缩与显式签名。安装包、APK、许可告知及对应依赖源码在 [正式 Release](https://github.com/TigerkidYang/sayrift/releases/tag/v0.2.1)提供。库替换见 [Windows 文档](windows-library-replacement.md)。
