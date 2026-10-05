# Windows 二进制核验记录（2026-10-06）

分支 `codex/windows-binary`，独立工作树 `sayrift-windows-binary`，基于 `main` 的 `0b9cfe3`。
本记录验证 0.2.0 构建方法；父集成分支负责 0.2.1 版本号、最终重建与上传。没有发布远端，
没有读取密钥，没有调用付费 API，没有操作前台应用、注册表或用户安装目录。

本次实际结果：安装器 **84,625,982 字节**，SHA-256
`c2d01f4554a62ce783d049333091e0b2a968646f996cb3f0699b08227877ab7e`。
175 个默认测试通过，9 个修改/新增 Python 文件的 Ruff lint/format 检查通过。
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

## libsndfile 的来源证据与尚未解决的实际阻塞

实际 DLL SHA-256：`22518c16f9d13eda5ae5adf999c4740d7d16cc2d6b178b36dd4ac2f759a38559`。
它与 [上游 1ac5f941 的 DLL](https://github.com/bastibe/libsndfile-binaries/tree/1ac5f9412cedaac97667bf5f2c7d4d4fea91999e)
逐字节一致，也与 SoundFile 0.14.0 引用的 submodule `a3e6f976…` 一致。
对应构建仓库归档已保留。该 workflow 在 Windows 2019 使用 vcpkg，libsndfile 动态链接、
依赖静态链接，CRT 动态链接；工作流只执行 `vcpkg update`，没有固定 vcpkg baseline。

实际 DLL 可见 `libsndfile 1.2.2`、`FLAC 1.4.3`、`Opus 1.5.2`、`Vorbis 1.3.7`、
`LAME 3.100` 字符串和 mpg123 代码/路径。已下载这些已识别版本的源码、Ogg 1.3.5 源码，
并附完整相应许可与 SoundFile 上游 native-license notes。额外下载 vcpkg 2024.12.16
源码/port 补丁、mpg123 1.32.9 源码作为该构建日期附近的候选材料。

**剩余阻塞：尚未证明该 DLL 使用的确切 mpg123/Ogg 版本、vcpkg baseline 与补丁组合。**
不能把候选归档标成已验证的完整对应源码。发布负责人需取得原构建的 baseline/依赖锁定证据，
或用已固定源码、补丁和工具链重新构建 libsndfile 及其静态依赖，替换 wheel DLL 后重新验证。
此处没有将“版本看起来接近”当作 LGPL 对应源码义务完成的依据。

Qt/PySide 完整版本源码、libsndfile 及编解码器来源材料和 Certifi 2026.7.22 的 MPL 源码
都应与最终安装器同页提供。父任务需上传这些资产并在发行说明明确列出源码入口；本任务未上传。
本机没有进行 Qt/音频库从源码重建，也没有测试所有显卡、真实麦克风或 Windows 安装/卸载界面。

许可依据：[Qt 官方 LGPL 义务](https://www.qt.io/development/open-source-lgpl-obligations)、
[Qt for Python Windows 构建说明](https://doc.qt.io/qtforpython-6/building_from_source/windows.html)、
[上游音频构建工作流](https://github.com/bastibe/libsndfile-binaries/blob/1ac5f9412cedaac97667bf5f2c7d4d4fea91999e/.github/workflows/build-libs.yml)。
