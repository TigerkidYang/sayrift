# Sayrift Android

`0.2.1`（`versionCode = 3`）将原来的 local-typeless 更名为 Sayrift，沿用 Glass 光球图标。
改名覆盖启动器、系统应用与无障碍服务标签、引导和故障提示、录音通知、Gradle 项目名及 OpenRouter 的 `X-Title`。

## 升级兼容性

以下是已有安装使用的持久标识，不能随展示名称一起改：

| 项目 | 保留的标识 |
|---|---|
| applicationId / namespace | `app.localtypeless.android` |
| Kotlin 包与核心资源路径 | `app.localtypeless.android`、`app.localtypeless.core` 及其子包 |
| Activity 与 Service 组件 | `.MainActivity`、`.VoiceAccessibilityService`、`.MicService`（包名同上） |
| SharedPreferences | `settings`、`ui`，以及其中所有既有 key（包括 `api_key`） |
| Android Keystore alias | `openrouter_key`，加密格式不变 |
| 历史和用量数据库 | `history.db`，schema version 仍为 `1` |
| 通知 | channel ID `dictation`、notification ID `7`，动作 `stop` / `cancel` |

这次没有数据迁移或清空设置。应用版本号与数据库版本号是两件事。内部的 `Theme.LocalTypeless`、包名和源码路径也保留，不代表界面仍使用旧名称。

**签名规则：**debug 使用开发签名；release 必须显式配置签名凭据，缺失时拒绝构建。
旧个人安装曾使用 debug 签名。更新它时必须显式使用原来的签名身份；换电脑生成同名文件不能代替原证书。
不要为解决签名不匹配而卸载旧应用，这会删除历史、设置和设备 Keystore 材料。
配置、备份与核验步骤见[签名说明](signing.md)。[v0.2.1](https://github.com/TigerkidYang/sayrift/releases/tag/v0.2.1) 提供使用独立发布证书签署的 APK，不可直接覆盖原个人 debug 签名版本。

## 本地验证与构建

需要 JDK（本项目用 JDK 21 构建、输出 Java 17 字节码）；APK 构建还需要 Android SDK Platform 35 与对应 build-tools。
SDK 路径通过 `ANDROID_HOME` 或未提交的 `local.properties` 中的 `sdk.dir` 配置，不在共享配置里写本机绝对路径。

在 `android/` 目录的新 PowerShell 会话中运行；临时目录仅对该会话及子进程生效：

```powershell
# 长 TEMP 路径可能触发 Java 的 Unix-domain socket 路径限制。
# 每次构建使用独立短目录，避免并行任务共享临时文件。
$buildTemp = Join-Path $env:USERPROFILE ('.gradle/udtmp/sayrift-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $buildTemp | Out-Null
$env:TEMP = $buildTemp
$env:TMP = $buildTemp
./gradlew.bat :core:test --no-daemon --console=plain
if ($LASTEXITCODE -ne 0) { throw 'Core tests failed' }
./gradlew.bat :app:assembleDebug --no-daemon --console=plain
if ($LASTEXITCODE -ne 0) { throw 'APK build failed' }
Copy-Item -LiteralPath app/build/outputs/apk/debug/app-debug.apk `
    -Destination app/build/outputs/apk/debug/sayrift-0.2.0-debug.apk
```

若用户目录本身很长，把 `$buildTemp` 改为当前用户可写的更短目录。依赖已缓存时可为 Gradle 加 `--offline`。
核心测试使用本地 MockWebServer，不需要 API key，也不调用付费模型。以上命令不会安装到手机或启动模拟器。
