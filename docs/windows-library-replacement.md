# Windows 库替换与重新构建

Sayrift 的应用和图形安装程序使用 Qt、PySide6、Shiboken（LGPLv3），应用还使用
libsndfile（LGPLv2.1）。完整许可位于 `licenses/`。Sayrift 不限制用户修改这些库，
也不限制为调试这些修改而进行的逆向工程。应用源码采用 MIT。

## 不重新编译 Sayrift 的替换方法

1. 退出 Sayrift。备份安装目录；不要删除 `%APPDATA%/local-typeless` 的个人数据。
2. 在安装目录 `_internal/PySide6/` 替换兼容的 Qt6 DLL、PySide 扩展和相应插件；
   Shiboken 在 `_internal/shiboken6/`，libsndfile 在 `_internal/_soundfile_data/libsndfile_x64.dll`。
   使用 Windows x64、相容 ABI 和依赖的库。替换文件无需签名、密钥或修改 EXE 校验值。
3. 正常运行 `sayrift.exe`。离线诊断可运行 `sayrift.exe --library-probe C:/Temp/app-probe.json`。
   诊断只检查 Qt 栅格绘制和合成静音的 OGG/Opus 编解码，不启动主窗口、不录音、不联网。

安装程序也可替换库。在 PowerShell 中运行并等待结束：

```powershell
Start-Process -Wait -FilePath .\sayrift-Setup-0.2.1.exe -ArgumentList '--extract-to', 'C:/Temp/SayriftSetup'
```

目标目录必须尚不存在。此操作仅解包，不安装、不修改注册表、不退出正在运行的程序。
在解包目录 `_internal/PySide6/` 和 `_internal/shiboken6/` 替换库后运行 `SayriftSetup.exe`，
会显示原来的安装界面。`SayriftSetup.exe --library-probe C:/Temp/setup-probe.json` 可先离线验证。
不要再次运行外层 EXE，否则会解出另一份原始库。外层只是 Python 标准库解包器，不加载 Qt。

安装负载在解包目录 `_internal/payload.zip`。需要安装自定义应用库时，可以用 ZIP 工具解开该文件，
替换其中 `_internal` 的库，再以原目录结构重新压缩覆盖 `payload.zip`。安装器不校验签名或固定哈希。
后续官方升级会覆盖程序目录；请保留修改版库并在升级后重新应用。

## 源码与构建

发布者必须把本版本对应的源码归档和 manifest 与安装包放在同一下载页，明确提供源码下载。
仅链接上游首页不足以代替这个交付步骤。`docs/windows-binary-evidence.md` 记录实际核验范围和未解决项。

完整 Sayrift 源码、`uv.lock`、`tools/build_installer.py`、`tools/windows_setup_launcher.py` 和
`tools/windows_runtime_hook.py` 是重新组合应用和安装器需要的材料。Windows x64 / CPython 3.12：

```powershell
uv sync --locked
uv run python tools/build_installer.py
```

Qt 源码归档提供 `configure.bat`、CMake 构建脚本及第三方源代码；使用相同版本 MSVC x64 工具链
构建共享库（`configure.bat -opensource -confirm-license -shared -release -nomake examples -nomake tests`，
然后 `cmake --build . --parallel`、`cmake --install .`）。请在独立构建目录配置，并按源码 README
安装该版本要求的 CMake/Ninja/Windows SDK。PySide 源码的 `README.md`、`setup.py` 和 `build_scripts/`
提供绑定构建方法；使 `--qtpaths` 指向所构建 Qt 的 `bin/qtpaths.exe`，使用 CPython 3.12 和对应 LLVM/Clang。
库源码不包含 Sayrift 修改。版本相同不等于已证明 wheel 的准确构建来源；核验报告明确区分两者。


本发行版的 libsndfile 来自固定源码重建，只有 Ogg/Opus 外部编解码器；MP3、FLAC、Vorbis
不可用。原始源码、带日期的修改、准确编译器摘要与重建命令见 `windows-audio-build.md`
及发行附件 `sayrift-windows-audio-source.zip`。可自行修改并重建兼容 DLL，再按上述路径替换。
