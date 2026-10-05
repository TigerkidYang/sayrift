# Sayrift 第三方软件与素材告知

核验日期：2026-10-06。Sayrift 自有代码采用 [MIT](LICENSE)，第三方作品保留各自许可证。

0.2.1 提供 Windows 安装包和 Android APK。安装器、应用目录与 APK 内包含适用的许可和告知；
发布页同时提供配套告知及 Windows 依赖源码下载。最终制品的检查范围见
[二进制发布记录](docs/binary-release.md)、[Windows 核验](docs/windows-binary-evidence.md)和
[Android 运行时告知](android/runtime-notices.md)。本文件保留初次源码审查的来源说明，
其中“旧分发包”“审计基线”的观察不代表 0.2.1 仍包含那些已排除的组件。

`licenses/` 下的许可适用于对应第三方作品，不是 Sayrift 整体的许可证。此处记录材料与验证证据，
不作对任意未来构建的合规保证。更新依赖、打包方式或原生库后应重新核验实际制品。

## 1. Windows 依赖清单

版本依据是本次核验的锁文件与已安装发行包；以后更换依赖或解释器后，需要对实际发布包重新核对。
下表的 wheel 文件路径相对于 Python 环境的 `site-packages/`，供构建时提取，不要求终端用户安装 Python。

| 组件 | 已核验版本 | 许可证据与应保留材料 |
|---|---|---|
| PySide6_Essentials | 6.11.2 | 元数据：`LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`；详见 §3 的缺失文本和源码问题。[官方源码](https://code.qt.io/cgit/pyside/pyside-setup.git/) |
| shiboken6 | 6.11.2 | 元数据同上；随 PySide6 使用的绑定运行库也在核验范围内。[官方源码包](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/) |
| Qt 运行库 | 6.11.2 | 由 `QtCore.qVersion()` 核实；旧分发目录含 Qt6Core、Qt6Gui、Qt6Network、Qt6Svg、Qt6Widgets、插件与 `opengl32sw.dll`。Qt 及其中的第三方代码要分别核对。[Qt 许可说明](https://doc.qt.io/qt-6/licensing.html) |
| httpx | 0.28.1 | BSD-3-Clause；`httpx-0.28.1.dist-info/licenses/LICENSE.md`。[版本源码](https://github.com/encode/httpx/tree/0.28.1) |
| numpy | 2.5.3 | 本机元数据列出 `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`；保留 `numpy-2.5.3.dist-info/licenses/` 整个目录，并核对 wheel 自带原生库告知，不能只写一个 BSD 标签。[上游](https://github.com/numpy/numpy) |
| sounddevice | 0.5.6 | MIT；`sounddevice-0.5.6.dist-info/licenses/LICENSE`；PortAudio/ASIO 二进制另见 §4。[上游](https://github.com/spatialaudio/python-sounddevice/) |
| soundfile | 0.14.0 | BSD-3-Clause；`soundfile-0.14.0.dist-info/LICENSE`，版权人为 Bastian Bechtold；不覆盖原生 libsndfile。[上游说明](https://python-soundfile.readthedocs.io/) |
| libsndfile | 1.2.2 | 由 `soundfile.__libsndfile_version__` 核实；`_soundfile_data/libsndfile_x64.dll` 和 `_soundfile_data/COPYING`；上游采用 LGPL，详见 §4。[1.2.2 源码](https://github.com/libsndfile/libsndfile/releases/tag/1.2.2) |

以下传递依赖的版本与许可取自本机对应 wheel 元数据；构建时应提取各发行包的完整许可与告知，
不能仅把此表当作许可全文：

| 组件 | 版本 | 元数据中的许可 | wheel 内许可文件 |
|---|---|---|---|
| anyio | 4.15.1 | MIT | `anyio-4.15.1.dist-info/licenses/LICENSE` |
| certifi | 2026.7.22 | MPL-2.0 | `certifi-2026.7.22.dist-info/licenses/LICENSE` |
| cffi | 2.1.1 | MIT-0 | `cffi-2.1.1.dist-info/licenses/LICENSE` |
| httpcore | 1.0.9 | BSD-3-Clause | `httpcore-1.0.9.dist-info/licenses/LICENSE.md` |
| idna | 3.20 | BSD-3-Clause | `idna-3.20.dist-info/licenses/LICENSE.md` |
| h11 | 0.16.0 | MIT | `h11-0.16.0.dist-info/licenses/LICENSE.txt` |
| typing_extensions | 4.16.0 | PSF-2.0 | `typing_extensions-4.16.0.dist-info/licenses/LICENSE` |

这些是已核验的条目，不是完整 SBOM。还需对最终包里的 CPython、原生库、平台运行库、
资源文件和其他被打包的模块做清单核对。`certifi` 的 MPL 材料还应说明相应源码的获取方式；
不要把证书包仅当作无需告知的数据文件。

开发/构建工具：PyInstaller **6.22.3**。它不是通常运行时安装的 Python 依赖，但其 bootloader
参与生成 EXE。[PyInstaller 官方例外说明](https://pyinstaller.org/en/stable/license.html)
允许按应用及其依赖适用的许可分发生成包；**不能因为使用 PyInstaller 就推定 Sayrift 必须采用 GPL**。
如修改并分发 PyInstaller 自身，其条款另行适用。

## 2. Lucide 与 Feather 图标

`src/local_typeless/ui/icons.py` 内嵌 SVG 路径，不会由 wheel 的许可提取覆盖。
审计基线的文件开头仅写了 Lucide/ISC，但所用图形也包含 Feather 派生形状：例如 `volume` 的几何与
[Feather volume-2](https://github.com/feathericons/feather/blob/main/icons/volume-2.svg) 对应。
“风格类似”这句注释不能代替复制/改编图形的来源和版权告知。

随本仓库保留：

- [Lucide 的完整复合许可](licenses/Lucide-ISC-Feather-MIT.txt)：上游修订
  `e715345d62667c800e7f54c94b1b023692e900a3` 的原始 `LICENSE`，包含 Lucide ISC 以及上游列明的
  Feather 派生图标 MIT 文本、版权人和适用图标列表。
- [Feather 的独立 MIT 许可](licenses/Feather-MIT.txt)：保留 Cole Bemis 的完整版权与许可告知，
  包括直接采用 Feather 图形时需要保留的文本；来源修订见 [licenses/README.md](licenses/README.md)。

这是对已知来源补齐告知；未从现有代码重建每个图标最初导入时的版本，不能声称完成了逐图形溯源。
发行源码与二进制都应带上这些文本。官方解释见 [Lucide license](https://lucide.dev/license)。
这些文本不为 Sayrift 自制光球标识授予新的许可，也不代表 Lucide、Feather 或其作者认可 Sayrift。

## 3. Qt / PySide6 / Shiboken

**实测缺口：**本机 `pyside6_essentials-6.11.2.dist-info/METADATA` 与
`shiboken6-6.11.2.dist-info/METADATA` 声明 LGPL-3.0-only / GPL-2.0-only / GPL-3.0-only 三选一，
但两个 `dist-info/licenses/` 目录都只有 `LicenseRef-Qt-Commercial.txt`。
这是本次已安装 wheel 的观测结果，不是对所有平台 wheel 的断言；商业条款文件本身也不证明拥有商业授权。
**单纯遍历 wheel 的 License-File，无法补齐这两个包的开源许可文本。**

本仓库从 Qt 官方 `qtbase` 的 `v6.11.2` 标签原样补充
[LGPLv3](licenses/Qt-LGPL-3.0-only.txt) 与 [GPLv3](licenses/Qt-GPL-3.0-only.txt)。
LGPLv3 纳入 GPLv3 的条款，因而两份文本一起提供；这不为 Sayrift 自有代码选择 GPL。
这些通用文本也不能替代每个组件自己的版权、例外及第三方材料。

0.2.1 的核验按以下项目进行，实际构建与库替换证据见 [Windows 核验记录](docs/windows-binary-evidence.md)：

1. 明确所依赖的许可路径；若使用 LGPL，提供显著使用告知、完整许可文本，并保留相关版权/告知。
2. 记录**实际 DLL、插件及绑定的对应源码**：准确版本、构建来源、所用修改及必要构建材料，
   按适用条款提供接收者可获得源码的方式。仅有项目主页、wheel 或本文件的参考链接，不证明已履行该义务。
3. 验证用户能按 LGPLv3 §4 适用路径替换/重新组合库并运行修改后的程序，保留条款要求的修改与调试权利。
   安装后的 `--onedir` 应用和使用 Qt 的 `--onefile` 安装程序是两个待验证的分发对象；
   “动态链接”“公开了 Python 代码”或“安装程序会解压”都不能单独证明满足要求。
4. 核对实际打包的 Qt 模块及第三方组件，不把整个 PySide wheel 统一当作一个 LGPL 文件。

对应版本源码的官方参考入口：

- [PySide/Shiboken 6.11.2 源码归档](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/)。
- [Qt 6.11.2 源码归档](https://download.qt.io/archive/qt/6.11/6.11.2/single/)。
- [Qt 官方 LGPL 义务说明](https://www.qt.io/development/open-source-lgpl-obligations)。
- [Qt 第三方许可索引](https://doc.qt.io/qt-6/licenses-used-in-qt.html)。

0.2.1 已保存固定哈希的 Qt/PySide 完整版本源码，并验证应用和图形安装器实际加载修改后的库。
替换和重建方法见 [Windows 库替换](docs/windows-library-replacement.md)，准确源文件 URL 与摘要见 `tools/windows-sources.json`。

## 4. soundfile、原生音频库及其他二进制

`soundfile` 的 Python 包是 BSD-3-Clause，原生 **libsndfile 1.2.2 是单独的 LGPL 组件**。
本仓库提供其上游 1.2.2 的 [COPYING 全文](licenses/libsndfile-LGPL-2.1.txt)；
wheel 的 `_soundfile_data/COPYING` 也应保留。[上游 FAQ §21](https://libsndfile.github.io/libsndfile/FAQ.html#q21)
说明 LGPL 2.1 及可选 LGPLv3 的使用方式。不能只保留 Python BSD 文本而忽略 DLL。
DLL 的源码交付/获取安排、修改记录及适用的库替换要求需按其实际许可核对；只附许可文本不等于完成。

对本机旧 Windows 分发包的观察，以及超出一般 wheel 元数据提取范围的待办如下：

- `_sounddevice_data/portaudio-binaries/` 含普通及 `*-asio.dll` 变体，甚至非当前 Windows 架构的二进制。
  上游随包 README 分别列明 PortAudio 与 Steinberg ASIO；不能用 sounddevice 的 MIT 标签概括全部。
  [PortAudio 官方许可](https://portaudio.com/license.html) 可作为 PortAudio 告知来源，
  ASIO 变体需单独确认 SDK 版本和分发条款，或在构建中排除确实不需要的变体。
- `_soundfile_data/libsndfile_x64.dll`：仍需识别其中实际编入的编码器/解码器及其版本、许可和源码需求。
  DLL 导入表只有系统库并不能证明没有静态编入其他音频库。
- `PySide6/opengl32sw.dll`、Qt 插件、字体/图像支持代码以及其他原生依赖：需依据实际制品和相应构建材料
  确定第三方清单。没有在 wheel 中看到独立许可证文件，不表示它们不存在或无需告知。
- CPython 与 Microsoft 运行库：解释器和 DLL 往往不以普通 wheel 出现，应单独记录实际版本与分发材料。

构建时自动复制已安装 wheel 的许可证是必要的材料收集步骤，**不是对所有字体、编解码器、静态链接库、
系统运行库及手写内嵌素材的完整许可审核**。最后应直接检查应用目录和安装包的实际内容。

## 5. Android 声明与告知来源

以下依据 `android/build.gradle.kts`、`android/app/build.gradle.kts`、`android/core/build.gradle.kts`，
并核对 Google Maven 的 [Compose BOM 2024.12.01 原始 POM](https://dl.google.com/dl/android/maven2/androidx/compose/compose-bom/2024.12.01/compose-bom-2024.12.01.pom)。
以下表格是直接声明/版本约束；最终解析的 60 个运行时制品及哈希另见 `android/notices/manifest.json`。

| 组件 | 声明/约束版本 | 类型与许可来源 |
|---|---|---|
| Kotlin Android/JVM、Compose、serialization 插件 | 2.0.21 | 构建工具；[Kotlin 对应版本 Apache-2.0 文本](https://github.com/JetBrains/kotlin/blob/v2.0.21/license/LICENSE.txt)。APK 中 Kotlin 标准库的最终版本需看解析报告。 |
| Android Gradle Plugin | 8.7.3 | 构建工具；[Android 构建工具源码](https://android.googlesource.com/platform/tools/base/)。 |
| Gradle wrapper | 8.10.2 | 构建工具；脚本已含 Apache-2.0 头；[Gradle 许可](https://github.com/gradle/gradle/blob/v8.10.2/LICENSE)。 |
| Compose BOM | 2024.12.01 | 版本约束平台，本身不等于打进 APK 的运行时代码。 |
| Compose UI、Foundation、Material icons extended | BOM 约束 1.7.6 | AndroidX；[UI 1.7.6 POM](https://dl.google.com/dl/android/maven2/androidx/compose/ui/ui/1.7.6/ui-1.7.6.pom)；Apache-2.0，仍应保留实际 AAR/JAR 的通知。 |
| Compose Material3 | BOM 约束 1.3.1 | AndroidX；[Material3 POM](https://dl.google.com/dl/android/maven2/androidx/compose/material3/material3/1.3.1/material3-1.3.1.pom)；Apache-2.0。 |
| activity-compose | 1.9.3 | AndroidX；[版本 POM](https://dl.google.com/dl/android/maven2/androidx/activity/activity-compose/1.9.3/activity-compose-1.9.3.pom)。 |
| core-ktx | 1.15.0 | AndroidX；[版本 POM](https://dl.google.com/dl/android/maven2/androidx/core/core-ktx/1.15.0/core-ktx-1.15.0.pom)。 |
| kotlinx-coroutines-android | 1.9.0 | [对应版本 Apache-2.0 许可](https://github.com/Kotlin/kotlinx.coroutines/blob/1.9.0/LICENSE.txt)。 |
| kotlinx-serialization-json | 1.7.3 | [对应版本 Apache-2.0 许可](https://github.com/Kotlin/kotlinx.serialization/blob/v1.7.3/LICENSE.txt)。 |
| OkHttp | 4.12.0 | [版本 POM](https://repo.maven.apache.org/maven2/com/squareup/okhttp3/okhttp/4.12.0/okhttp-4.12.0.pom)；Apache-2.0；Okio 等传递依赖另行收集。 |
| kotlin-test / MockWebServer | Kotlin 2.0.21 / 4.12.0 | 测试依赖，不应据此声称它们被包含在正式 APK 中。 |

通用 [Apache-2.0 全文](licenses/Apache-2.0.txt) 已保留；它不替代各库原有的版权、NOTICE、
源码中的特别条款及各自的第三方告知。发布构建需导出 `releaseRuntimeClasspath` 的解析结果，
检查实际 AAR/JAR/APK 的许可证和 NOTICE，再生成随 APK 可获得的告知。

审计基线的 `android/app/build.gradle.kts` 排除了 `/META-INF/{AL2.0,LGPL2.1}`。
这条打包规则并不自动证明违规，也不证明义务消失；若资源被排除，应确认其适用文本在另一可获得位置完整提供。
整合分支已将此规则改为合并保留根目录和 META-INF 中的许可 / NOTICE 资源，并通过 AGP 配置检查；
0.2.1 另将完整告知打入 `assets/third_party/`，最终签名 APK 的 153 个告知文件与配套 ZIP 已逐字节核对。

## 6. 图像、声音与评测数据来源

- 应用光球图标有仓库内生成路径：`tools/make_icon.py` 与 `src/local_typeless/ui/icons.py`；
  Android 对应标识是仓库内 vector XML。提示音由 `src/local_typeless/sounds.py` 合成。
  这些事实说明实现来源，不代替所有者决定自有作品许可。
- `evals/asr/audio/*.ogg` 的合成语音由 `tools/make_tts_samples.py` 通过 Microsoft Edge TTS 生成，
  音色记录在 `evals/asr/samples.tsv`。edge-tts 客户端的代码许可**不能直接当作微软声音或输出音频的再分发授权**。
  本次没有获得允许随公开源码仓库再分发这些录音的明确依据；发布负责人应取得适用授权证据，
  或以具有明确同意/许可的录音替换，或从拟公开的源码交付范围排除它们。
  这是一项未解决的来源问题，不是已认定侵权。参见 [Microsoft 版权资源](https://www.microsoft.com/en-us/legal/intellectualproperty/copyright)。
- 录音是否进入应用安装包与录音是否随 Git 仓库公开，是两个独立检查点。只从 EXE 排除不能解决源码分发的来源问题。

## 7. 版本核验要求

本次交付是这份清单及 `licenses/` 的固定来源许可原文。具体文件来源、修订、字节数和 SHA-256
见 [licenses/README.md](licenses/README.md)。

- 最终 EXE/APK 与安装程序包含其适用的许可、版权及通知；具体材料和核验结果见各平台报告。
- PySide6/Shiboken wheel 缺少的开源许可文本由构建明确补齐。
- Qt/PySide6/Shiboken 与实际发布的音频库提供对应版本源码、构建材料和库替换说明。
- Windows 原生制品清单保留相对路径、摘要、架构与导入表；ASIO 和不需要的可选 DLL 不分发。
- Android 解析依赖、AAR/JAR NOTICE 与补充材料固定摘要，并在 APK 和配套 ZIP 提供。
- [x] 首次公开快照排除 Edge TTS 评测录音；保留文本用例和使用自有录音的说明。
- [x] Sayrift 自有代码与原创资源采用 MIT；本目录的第三方作品保留原许可。
