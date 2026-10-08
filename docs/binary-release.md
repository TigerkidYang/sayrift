# Sayrift 安装版核验

当前版本为 **0.2.2**；本轮重新构建、签名及制品检查见 [0.2.2 核验记录](release-0.2.2.md)。下面保留 0.2.1 的历史记录，旧摘要不用于校验新版附件。

## 0.2.1 历史记录

日期：2026-10-06。整合分支 `codex/binary-release`；此版本不包含分级热词库实验。

默认 pytest：185 个测试通过，Ruff lint / format 通过。

## Android

- `versionName=0.2.1`、`versionCode=3`、应用 ID `app.localtypeless.android`、最低 API 29、目标 API 35。
- JDK 21、Gradle 8.10.2、AGP 8.7.3、Android SDK Platform 35 / build-tools 34.0.0；release 构建含 R8、资源压缩与 release lint。
- 19 个核心 JVM 测试通过；7 个告知生成/制品校验测试通过，已纳入默认 pytest 路径。
- 最终 APK 的 153 个告知与项目许可资产和配套 ZIP 逐字节一致；对应 60 个解析后的运行时制品。
- `apksigner verify` 通过；RSA 4096 / APK v2，证书指纹见 [签名记录](../android/signing.md)。`zipalign -c 4` 通过。
- 清单检查：未开启 debuggable、未开启测试用明文网络、`allowBackup=false`。ZIP 完整性检查通过。
- 未发现本机用户名、完整 OpenRouter key 格式、`dev.json`、签名私钥或口令配置。UI 中的 `sk-or-v1-…` 是占位提示，不是密钥。

正式证书和原个人 debug 证书不同，不覆盖原手机安装；未操作实体手机。

## Windows

- 应用与图形安装器保留动态库；标准库外层支持仅解包，用户可以修改依赖后运行图形安装程序。
- Qt/PySide6/Shiboken 6.11.2 完整版本源码、许可和替换说明随发布提供。详见 [Windows 核验](windows-binary-evidence.md)。
- 使用固定源码构建的 libsndfile 1.2.2 + Ogg 1.3.5 + Opus 1.5.2；补丁、构建配方与报告随音频源码 kit 提供。
- 额外实际测试：用产品 `Recorder._write_loop()` 分 50 次写入合成音调，重建 DLL 生成 Opus；原 wheel DLL 解码得到 16,000 帧 / 16 kHz，时长和音量检查通过。未开启麦克风。
- 发布包不包含 ASIO、其他架构的 PortAudio、软件 OpenGL 或从无关软件 PATH 收集的 Qt OpenSSL DLL。
- Windows EXE 未进行商业代码签名，不能声称已通过 SmartScreen 信誉认证。

最终安装包已通过 `tools/verify_windows_bundle.py`：在独立临时目录检查解包、负载安装、升级及替换库后的真实运行结果；未修改注册表、快捷方式或用户安装目录。安装包 84,553,870 字节；具体摘要见发布页 `SHA256SUMS.txt` 和 [Windows 核验](windows-binary-evidence.md)。

## 下载材料

[GitHub Release](https://github.com/TigerkidYang/sayrift/releases/tag/v0.2.1) 提供安装包、APK、Android 告知 ZIP、Windows 音频源码 kit、其他依赖源码归档和 SHA-256 校验值。源代码由同一版本标签提供。

自动检查证明构建、包内容和上述受控场景通过，不等于全面真机验收。未重复真人语音/微信输入测试，未调用付费模型。一般应用兼容限制见 [兼容性说明](compatibility.md)。
