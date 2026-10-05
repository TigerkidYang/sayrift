# Windows 音频库的固定源码构建

此构建只把 Ogg 1.3.5、Opus 1.5.2 静态链接进 libsndfile 1.2.2 共享 DLL。
使用官方 llvm-mingw 20260922 的 Windows x64 UCRT 工具链（Clang 23.1.2），动态链接 Windows UCRT。
不使用 wheel 自带的 libsndfile，也不链接 FLAC、Vorbis、LAME、mpg123 或未知 vcpkg 构建材料。
内置 PCM/ADPCM/ALAC 等 libsndfile 自有格式保留；外部编解码器仅有 Ogg/Opus。
因此 Windows 安装版不再支持 MP3、FLAC、Ogg Vorbis 输入；应用录音和历史重试使用 Ogg Opus。

## 重建

Windows x64、Python 3.12、uv，从完整 Sayrift 仓库运行：

```powershell
uv sync --locked
uv run python tools/build_windows_audio.py
```

单独使用源码 kit（其中没有应用的 pyproject.toml）时：

```powershell
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe cmake==3.31.6 ninja==1.11.1.4
.venv/Scripts/python.exe tools/build_windows_audio.py
```

在已有开发环境中跳过 `uv venv`。构建工具仅装入虚拟环境，不修改项目运行依赖或 uv.lock。
编译器 ZIP 约 191 MB，首次运行从上游下载并按固定 SHA-256 验证；已有正确缓存不会重复下载。
三个库的未修改原始源码归档和工具链 URL/摘要在 `tools/windows-audio-sources.json`。
源码 kit 内已包含三个库的归档，编译器本身不随 kit 重新分发。

上游 1.2.2 的 `HAVE_EXTERNAL_XIPH_LIBS` 同时控制三个 Xiph 编解码器；因此本构建需要源代码修改。
`tools/libsndfile-opus-only.json` 精确记录每处原文、替换文本和次数；不匹配即失败。
修改禁用 FLAC/Vorbis 实现、移除对应链接项/格式公告，并让格式检查返回不支持。
MPEG 通过上游 `ENABLE_MPEG=OFF` 禁用。构建产生标准 unified diff，便于审查或手工应用。

输出：

- `dist/windows-audio/libsndfile_x64.dll`：应用实际使用的 DLL。
- `dist/windows-audio/build-report.json`：源码/工具链摘要、命令、构建工具版本/摘要、DLL 摘要。
- `dist/windows-audio/libsndfile-opus-only.patch`：本次实际应用的补丁。
- `dist/sayrift-windows-audio-source.zip`：原始库源码、完整修改与重建脚本、DLL 及构建报告。

`tools/build_installer.py` 检查本地构建结果及报告；缺失或与当前 recipe 不匹配时自动调用重建。
父集成分支把 CMake/Ninja 固定为开发依赖，因此现有 CI 构建命令无需修改。
没有 wheel DLL 的回退路径，重建失败即停止打包。
应用冻结后用此 DLL 替换 wheel 副本；安装包里的 DLL 摘要必须与报告相同。
父集成工作树可以复制整个 `dist/windows-audio/`，但必须与集成的构建脚本/补丁/manifest 一致。
更新 helper 后应重新生成报告和 source kit，不能手工改摘要绕过检查。

修改 DLL 不需要签名或密钥。安装目录的 `_internal/_soundfile_data/libsndfile_x64.dll` 可以替换；
详见 `windows-library-replacement.md`。此路径保持 libsndfile LGPLv2.1 的修改/重新组合能力。
重建源码和此补丁必须与二进制一起在发行下载页提供。
