# Windows 二进制核验记录（2026-10-06）

分支 `codex/windows-binary`，独立工作树 `sayrift-windows-binary`，基于 `main` 的 `0b9cfe3`。
本记录验证 0.2.0 构建方法；父集成分支负责 0.2.1 版本号、最终重建与上传。没有发布远端，
没有读取密钥，没有调用付费 API，没有操作前台应用、注册表或用户安装目录。

本次实际结果：安装器 **84,559,686 字节**，SHA-256
`ca18fb7ba9550b560d696c035bc12a4e665dd2ca547110e7e4e9049a8e6af2a3`。
178 个默认测试通过，修改/新增 Python 文件的 Ruff lint/format 检查通过。
真实冻结 EXE 的解包、临时安装、升级、Qt 和 libsndfile 修改版本运行验证均通过。
应用 85 个 PE、内层安装器 55 个 PE 均为 x64；外层 CArchive 不含 Qt/PySide/Shiboken。
已去掉临时机器路径的完整证据见 [Windows PE 清单](windows-native-inventory.json)。

## 制品与复核命令

```powershell
uv sync --locked
uv run python tools/prepare_windows_sources.py
uv run python tools/collect_windows_source_notices.py
uv run python tools/build_installer.py
uv run python tools/verify_windows_bundle.py dist/sayrift-Setup-0.2.0.exe
```

源码下载是显式发布准备步骤，普通构建和 CI 不下载 1 GB 的 Qt 源码。所有源码在忽略的
`dist/sources/`，准确 URL、文件字节数和 SHA-256 见 `tools/windows-sources.json`；下载工具验证摘要，
保留现有正确归档，并将 manifest 复制到输出目录。不要把成功下载直接当作准确对应关系的证明。

构建输出为 `dist/sayrift-Setup-0.2.0.exe`、`dist/sayrift/` 和 `dist/SayriftSetup/`。
验证工具输出 `dist/windows-verification.json`：安装器摘要、应用和安装器每个 PE 文件的相对路径、
SHA-256、架构、直接导入表，以及原始和修改库后的运行结果。完整构建日志在 `build/windows-build.log`。

## 库替换与安装路径

外层 EXE 是只用标准库的自解包程序。默认仍启动原来的 Qt 安装界面；`--silent` 保持原语义。
`--extract-to` 把独立的 Qt 安装器解包到用户选定的新目录，不执行安装。其 `licenses/` 在安装前
可直接访问，欢迎页也有明确的 Qt/PySide6/Shiboken LGPLv3 告知和许可按钮。

应用和内层安装器都是 onedir，共享库与插件是外部文件。没有固定库哈希检查，没有签名锁定，
没有额外 EULA 限制库修改或为修改调试而逆向工程。具体路径见 [替换说明](windows-library-replacement.md)，
也随两份程序放在 `licenses/LIBRARY-REPLACEMENT.md`。负载根目录只包含安装器允许的
`sayrift.exe`、`_internal`、`licenses`。

验证工具用外层 EXE 实际解包，然后调用生产 `install.replace_payload` 在临时 `Sayrift` 目录
安装和升级，检查无关文件保留。它在该临时目录把 QtCore 的版本字符串从 6.11.2 改为 6.11.9，
把 libsndfile 的版本字符串从 1.2.2 改为 1.2.9，再运行真实冻结 EXE 的诊断入口，断言修改后的
版本确实返回。诊断同时完成离屏 Qt 栅格绘制、1600 帧合成静音的 OGG/Opus 编解码。
新的冻结探针还确认 Ogg 子格式只有 Opus，FLAC/MP3 不出现在可用格式中，PCM 往返成功；
Python ssl + certifi 在无网络下创建默认 TLS 上下文，OpenSSL 3.0.13 加载 121 个 CA。
这是修改二进制的实际运行证据，不是宣称已经从源代码重建 Qt 或完整交互验收。

## 实际原生依赖

应用使用 Qt 6.11.2 的 Core、Gui、Widgets、Network、Svg，PySide6 Essentials 和 Shiboken 6.11.2。
插件含平台、样式、图像、SVG、网络信息和 TLS 后端。完整 Qt 6.11.2 源码及 PySide/Shiboken
6.11.2 源码已下载；也保留 qtbase/qtsvg/qtimageformats 小归档，供提取组件版权、许可与
`qt_attribution.json`。所有 attribution 引用的 LicenseFile 也包含在聚合告知中。
版本来源为锁文件、wheel 元数据及运行时 qVersion；没有对库做产品修改。

已从应用和内层安装器排除：

- ASIO、32 位、ARM64 和 macOS PortAudio 变体；保留 `libportaudio64bit.dll`。
  冻结入口清除 `SD_ENABLE_ASIO`，避免环境变量选择被排除的 DLL。应用依赖 WASAPI。
- `opengl32sw.dll`；应用使用栅格 Widgets，未使用 Quick/OpenGL Widgets。
- Qt 可选的 `qopensslbackend.dll` 及 `libcrypto-3-x64.dll` / `libssl-3-x64.dll`。
  初次构建发现这两个 DLL 来自构建机上无关 Poppler 目录的 PATH，不能默默继承其版本。
  Qt 保留 Windows Schannel 和证书后端；Python HTTPS 仍使用自身 OpenSSL。
- 从 System32 收集的 UCRT/API-set DLL；目标 Windows 11 自带这些系统组件。

其他 PE 包括 CPython 3.12.2、其 OpenSSL 3.0.13、libffi、SQLite、NumPy 2.5.3 的 OpenBLAS
以及 Microsoft C/C++ 运行库。Python、wheel 的完整许可随包复制，额外保留 OpenSSL 3.0.13
许可和 PortAudio 上游许可。NumPy 的告知包含其原生库说明，不能只标 BSD。
`python-inventory.json` 是保守的构建环境清单，包含开发依赖，不能当作实际装载模块的 SBOM。
PE 导入表也无法单独识别静态链接代码。

## libsndfile：阻塞已由固定源码重建消除

之前 wheel DLL 的未知 mpg123/Ogg/vcpkg 来源不再影响当前制品：安装包强制替换为本仓库
`tools/build_windows_audio.py` 构建的 DLL，不存在回退 wheel 副本的路径。
详细命令及可见功能变化见 [音频库构建](windows-audio-build.md)。

- libsndfile 1.2.2 + Ogg 1.3.5 + Opus 1.5.2；三个库的固定原始源码已在 source kit 内。
- LLVM-MinGW 20260922 UCRT x64（Clang 23.1.2）；工具链 ZIP 的上游 SHA-256
  `e3ad77d117a4bea19a7a3b333341824d79a5a371004a10e25b8504e7b3047666`。
- CMake 3.31.6 / Ninja 1.11.1.4；可执行文件摘要和完整规范化命令见构建报告。
- 外部 FLAC/Vorbis/MPEG 编解码器禁用；内置 PCM 等格式保留。源代码改动显著标注 Sayrift 与日期。
  精确替换规则、实际 unified diff 和原始源归档都随 kit 提供。
- 两次干净编译得到了相同的 DLL 摘要：
  `e4ba1dacb86dc6bfe9a47119d616c795e049c06bf906d16402f45def56aa4f7e`（1,379,840 字节）。
  这证明本机重复构建一致，不承诺不同机器上无条件逐字节一致。
- DLL 导入表只有 Kernel32 和 Windows UCRT API-set；无 Vorbis/FLAC/LAME/mpg123、libgcc 或
  winpthread DLL 依赖。源码/链接配置同时确认没有静态链接这些被排除的外部编解码器。
- 本地 DLL 和整个 source kit 内容检查没有 `littletiger`（UTF-8/UTF-16）或开发目录泄漏。

`dist/sayrift-windows-audio-source.zip` 包含原始源码、recipe、manifest、补丁、编译结果、许可和
构建报告。编译器本身不重新分发，脚本从已固定 URL 下载并验证摘要。源码 kit 的正常重建
只需要 Python/uv 和 Windows 11，无需 MSVC，也不依赖本机旧的 32 位 MinGW。

**此音频来源阻塞已解决。** 父任务还需用集成版本 0.2.1 重建、重新运行冻结制品检查，
并将 Qt/PySide 全部源码、当前 `tools/windows-sources.json` 中资产、Certifi MPL 源码和音频
source kit 与最终安装包同页发布。旧候选 mpg123/vcpkg/FLAC/Vorbis/LAME 归档不再属于交付清单，
不要按 `dist/sources/*` 通配符上传旧缓存。本任务没有远端发布。

许可依据：[Qt 官方 LGPL 义务](https://www.qt.io/development/open-source-lgpl-obligations)、
[Qt for Python Windows 构建说明](https://doc.qt.io/qtforpython-6/building_from_source/windows.html)、
[libsndfile 1.2.2 上游](https://github.com/libsndfile/libsndfile/tree/1.2.2)、
[LLVM-MinGW 工具链发布](https://github.com/mstorsjo/llvm-mingw/releases/tag/20260922)。

音频 source kit：5,846,482 字节，SHA-256
`54fe15e43a049c8bc5f306ea241b753c29346e5c8f96d49884acb8d95ae253f4`。
精确的已规范化重建记录见 [音频构建报告](windows-audio-build-report.json)。

最终 source kit 的 recipe/补丁摘要已与 Git 暂存的 LF 字节逐一比对，复制到集成工作树后可直接验证。
