# Android 运行时告知构建

`runtime-notices.gradle` 从 Gradle **实际解析的 `releaseRuntimeClasspath`** 获取外部制品，
不从声明版本或缓存目录猜测依赖。`tools/runtime_notices.py` 核对已审核的制品 SHA-256，
收集 AAR/JAR（包括嵌套 JAR）的原始告知，并加入 `notices/` 中固定版本的上游材料。
依赖、版本或制品字节变化时生成任务失败，必须重新收集和审核。

## 构建与交付

需要 Python 3.10+（仅标准库；项目推荐 3.12）、JDK 21 和现有 Gradle wrapper。
默认命令是 `python`，Ubuntu CI 可用 `actions/setup-python` 提供；需要时传
`-PnoticePython=/absolute/path/to/python`。无需安装额外 Python 包。

在 `android/` 运行：

```powershell
./gradlew.bat :app:generateReleaseRuntimeNotices --no-daemon --console=plain
```

该任务不要求签名或 Android SDK，也不调用模型 API。Gradle 可能下载运行时制品；
告知生成自身完全离线，使用已提交的上游证据。缓存齐全时可以加 `--offline`。
Linux 使用 `./gradlew`。

输出：

- `app/build/generated/runtimeNotices/assets/third_party/`：完整告知、公共清单、原始 POM、
  源码版权段落、上游许可和原始嵌入告知。
- `app/build/outputs/notices/sayrift-android-runtime-notices.zip`：同一目录内容，固定 ZIP
  时间戳与排序，相同输入逐字节可复现；随最终 APK 一起放入发布 ZIP。
- `app/build/reports/notices/release-runtime-local.json`：供生成器使用的本地路径报告，
  **不能放进发布包**。公共 `inventory.json` 只用坐标、制品文件名、哈希、公共 URL
  和制品内的相对路径；不含本地绝对路径、开发者用户名或签名信息。

`mergeReleaseAssets` 自动依赖生成任务，APK/AAB 包含 `assets/third_party/`。
debug 也带同一份明确标注为 release 输入清单的材料，便于不接触发布密钥的打包验证。
本改动不涉及 Kotlin UI；接收者可解压 APK 或直接打开配套 ZIP 中的
`third_party/THIRD_PARTY_NOTICES.txt`。R8 后输入类可能已裁剪，清单不冒充最终存活类清单。
本地 `:core` 是项目自身代码，BOM 约束和测试/构建工具不计入外部运行时制品。

最终签名 APK 由发布负责人运行字节级检查：

```powershell
python tools/runtime_notices.py verify-apk `
    --apk app/build/outputs/apk/release/app-release.apk `
    --zip app/build/outputs/notices/sayrift-android-runtime-notices.zip
```

检查必须在最终构建后进行；它比较告知资源列表与全部文件内容，不只是检查文件名存在。
此任务不修改签名配置、版本号、设备或发布渠道。

## 2026-10-06 核验依据

从 `0b9cfe3` 依赖图解析出 **60 个不同的外部 AAR/JAR、60 个模块**；重复引用的同一个
core AAR 去重。每个模块均取得准确版本的 Google Maven / Maven Central POM 和 sources JAR，
URL 与哈希记录在 `notices/manifest.json`。Guava `listenablefuture:1.0` 许可继承自
`guava-parent:26.0-android`，父 POM 也完整保存。原始 POM 里的上游作者信息按原文保留。

特别补充的材料：

| 实际组件 | 已收集证据 |
|---|---|
| AndroidX | 每个模块的原始 POM、版本 sources JAR 的版权/许可段落；core/core-ktx AAR 内原始 LICENSE |
| Kotlin stdlib 2.0.21 | JetBrains COPYRIGHT、上游许可索引、GWT/Guava 文本、MathJVM 派生代码的 Boost-1.0 文本 |
| kotlinx.coroutines 1.9.0 / serialization 1.7.3 | 各自版本的完整 LICENSE 与 NOTICE；coroutines 发布的 sources JAR 不含版权头，因此另取上游 NOTICE |
| OkHttp 4.12.0 / Okio 3.6.0 / annotations 23.0.0 | 准确版本的上游 LICENSE、源代码版权告知 |
| OkHttp publicsuffixes.gz | JAR 内原始 Mozilla NOTICE、MPL-2.0 全文，以及从实际压缩数据无损还原的全部可编辑规则（保留 `!` 例外规则）；不拿当前在线列表冒充该版本的数据 |
| graphics-path 1.0.1 | 四个 ABI 的原始 `.so` 哈希；发布源码的 CMake、C++ 和 Filament math 头文件；其编译工具链版本的 LLVM/compiler-rt/libc++/libc++abi 原始许可，含 Apache 例外与上游 MIT/UIUC 文本 |

graphics-path 的源码定位来自 [Google 发布说明](https://developer.android.com/jetpack/androidx/releases/graphics#graphics_path_1.0.1)
指向的提交 `8a05a22af450d589ef911d772a001a49dcb05b71`。
保存的 CMake 目标只编译 `Conic.cpp`、`PathIterator.cpp`、`pathway.cpp`；没有另外链接 Skia 库。
这些文件及 math 头文件有 AOSP 的 Apache-2.0 版权头，已逐文件保留。不能仅凭路径名给它们
重新归类成一个假定的 Skia 许可证。四个 `.so` 的编译器字符串一致指向 Clang 14.0.7、
LLVM 提交 `4c603efb0cca074e9238af8b4106c30add4418f6`，相应工具链许可已保守附带。

这份材料的范围是当前已解析运行时；不是对任意未来依赖或最终签名 APK 的预先保证。
调试 APK 构建和资源核验不等于真机行为验证。

## 更新依赖后的流程

```powershell
./gradlew.bat :app:exportReleaseRuntimeArtifacts --no-daemon --console=plain
python tools/runtime_notices.py refresh `
    --inventory app/build/reports/notices/release-runtime-local.json
```

`refresh` 最多四个并行下载，获取该版本 POM（必要时父 POM）及 sources JAR；
从源码提取不同版权段落和许可文件。`notices/supplements.json` 另行列出人工核验的补充材料
与固定 SHA-256。更新含原生库、数据包或有额外告知的依赖时，要先审核对应版本的来源，
更新补充材料，不能只重新生成一个 Apache 标签。下载内容变化、缺少 POM 许可都会报错。
重新生成后检查 Git diff，移除不再引用的旧证据文件，再提交变更。

验证命令（从仓库根目录）：

```powershell
python -m unittest discover -s android/tools -p test_runtime_notices.py
uv run ruff check android/tools
uv run ruff format --check android/tools
```

测试覆盖嵌套 JAR、不同作者的版权段落、去重与路径脱敏、public-suffix 例外规则、
未审核制品/被修改证据拒绝生成，以及 APK 文件缺失或内容变化。

本次结果：7 项单元测试、仓库 Ruff lint/format 通过；JDK 21 / SDK 35 下 debug APK
构建通过（包括离线增量构建），APK 内 153 个告知文件与配套 ZIP 逐字节相同；
两次独立生成 ZIP 的 SHA-256 相同。公共清单检查无本机用户名或绝对路径，并记录四个原生库。
`notices/.gitattributes` 禁止 Git 对上游材料转换换行，确保 Windows/Unix 检出的证据哈希一致。
最终 0.2.1 签名 APK 的检查由集成发布任务在重建后执行。
