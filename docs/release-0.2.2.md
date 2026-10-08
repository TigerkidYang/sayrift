# Sayrift 0.2.2 发布核验

日期：2026-10-08。发布分支 `codex/release-0.2.2`，独立 worktree `sayrift-release-0.2.2`，基于 `dbc8d2a`。
整合 0.2.1 之后的全部听写 prompt 改进；模型、依赖版本和持久化标识未变。

## 制品

| 附件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `sayrift-Setup-0.2.2.exe` | 84,562,728 | `38309590fee6c6d7cb91b38c11ad7f43a65f9621de37bd83dd91956fea55bacd` |
| `sayrift-0.2.2-android.apk` | 2,956,744 | `e29790fb8535308a901250b8e9dbf36ae63f96ade116d511e799fbbc4771f7ed` |
| `sayrift-0.2.2-android-notices.zip` | 486,591 | `722d1c96a7e453a08ff051de5955c93e7de1aca037e0d128758ec7b794a18896` |

[正式发布页](https://github.com/TigerkidYang/sayrift/releases/tag/v0.2.2) 同时提供 `SHA256SUMS.txt`、`release-metadata.json` 和 `windows-verification.json`。

## 共同检查

- 新 worktree 重新安装锁定依赖：`uv.lock` 仅本项目版本从 0.2.1 变为 0.2.2，外部依赖条目逐项相同。
- Python 185 项通过；Ruff lint 与 96 个文件的格式检查通过；Android core 19 项通过。
- Windows 主程序、图形安装器、外层 EXE 的版本资源均为 0.2.2；Android `versionName=0.2.2`、`versionCode=4`。
- 从 Windows 安装负载和最终签名 APK 逐字节核对三个 prompt，均与源码相同。听写 prompt SHA-256：`3583953ca24f401bfc104ba3f6e54f74959fad6af5b2b8b80b087116a0cc68b3`。
- 沿用同一 prompt 的[最终评测](typeless-history-comparison-2026-10-08.md)：43 用例 × 3 次 × 2 模型，各 129/129；没有为版本号变更重复付费评测。真实音频的 PR/P2 失败及排版差距仍在报告中保留。

## Windows

`tools/build_installer.py` 重新生成三个 EXE 和负载。`tools/verify_windows_bundle.py` 对最终 EXE 的实际解包、隔离安装/重复覆盖、Qt 和音频库替换后运行、Opus/PCM 编解码与离线 TLS/CA 加载检查全部通过。

另用 0.2.1 的原负载在隔离目录安装，再以 0.2.2 负载覆盖；版本资源确认从 0.2.1 变为 0.2.2，无关文件和独立模拟用户数据哨兵保留。没有修改真实用户安装目录、注册表、快捷方式或历史数据库。检查脚本初次读取 EXE 时未关闭 PE 文件句柄，造成自身锁文件；关闭检查句柄后重新运行通过，不涉及产品代码修复。

音频 DLL 沿用已审核构建，打包前重新验证 recipe、源码 manifest、补丁和 DLL 哈希。冻结运行检查也核对 DLL 与报告一致。Windows EXE 仍未商业代码签名。

## Android

JDK 21 / Android SDK 35 离线执行 `:core:test :app:assembleRelease`，含 R8、资源压缩与 release lint；使用仓库外既有发布私钥，口令只在构建进程环境中短暂存在。

- APK v2 / RSA 4096 签名验证通过，证书 SHA-256 与 0.2.1 相同：`7199eda9e10df933d19bfb1bc40eed3ba67244641ebd046d3cc3172b786ba0ba`。
- 包名 `app.localtypeless.android`，最低 API 29，目标 API 35，未开启 debuggable；`zipalign -c 4` 与 ZIP 完整性检查通过。
- 153 个最终 APK 告知资产与配套 ZIP 逐字节一致。
- APK 内容未发现本机用户名或完整 OpenRouter key 格式；两个平台负载的凭据/历史文件名及 key 格式检查通过。

签名、包名及版本码满足覆盖公开版 0.2.1 的条件，但本轮未安装或更新实体手机。早期个人 debug 签名版本仍不能用此公开证书直接覆盖，不能通过卸载来保留数据。

## 对应依赖源码

审核过的 Windows/Android 依赖和音频构建配方未变，逐项比对 manifest 并重新计算旧源码归档哈希。本版附带小型音频源码 kit；1.1 GB 的完整依赖源码沿用 [0.2.1 已公开归档](https://github.com/TigerkidYang/sayrift/releases/download/v0.2.1/sayrift-0.2.1-dependency-sources.zip)，SHA-256 为 `2b61df2afc9ae4e6e4a9043e77e3be8d2a0c2690acdfba412f76c76052a11b79`。

发布附件 `dependency-sources.json` 明确列出来源链接、大小和摘要；不是用不同版本源码替代。Sayrift 本身源码由 `v0.2.2` 标签提供。
