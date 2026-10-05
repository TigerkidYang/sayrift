# Windows 原生组件告知来源

此目录的许可适用于其标注的第三方组件，不改变 Sayrift 的 MIT 许可。
各归档来源与 SHA-256 在 `tools/windows-sources.json`。聚合文件的每段以 `SOURCE FILE:`
列出上游路径，后面保留许可/版权原文；UTF-8 解码和换行合并是唯一的呈现处理。

Qt/PySide 的聚合文件由 `tools/collect_windows_source_notices.py` 从官方 6.11.2 源码归档生成，
包括 `qt_attribution.json` 所引用的许可文件。范围保守包含未使用平台/构建工具的材料，
不能从聚合文件反推全部代码进入了二进制。实际 PE 清单由 `tools/verify_windows_bundle.py` 输出。

Ogg 1.3.5、Opus 1.5.2、libsndfile 1.2.2 的告知从相应源码归档提取。
libsndfile-embedded-notices.txt 还保留 src/ 下的版权头与内嵌 BSD 代码告知。
libsndfile 是本项目固定源码重建版本，源码和补丁交付详见 docs/windows-audio-build.md。
已移除旧 wheel 中不再分发的 FLAC/Vorbis/LAME/mpg123 的独立告知。

PortAudio-LICENSE.txt 来自 PortAudio v19.7.0 上游 LICENSE.txt；包含完整许可和其要求的告知。
OpenSSL-LICENSE.txt 来自 openssl/openssl 的 openssl-3.0.13 标签，匹配 CPython ssl 报告的版本。
llvm-mingw-LICENSE.txt 来自已核验的 LLVM-MinGW 20260922 编译器归档，包含 LLVM runtime 例外。
mingw-w64-runtime-COPYING.txt 来自该工具链 build-mingw-w64.sh 固定的源码提交
57b595039040eaa15bece85b7cc71d952281b269 下
COPYING.MinGW-w64-runtime/COPYING.MinGW-w64-runtime.txt。
其他 Python/NumPy/运行库告知在打包时从发行包和解释器目录复制，不重复手抄。
