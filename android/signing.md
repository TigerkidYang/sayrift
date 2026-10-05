# Android 签名与密钥保管

`release` 必须显式配置签名，不再自动使用 debug 密钥。源码使用者无需发布密钥即可构建
`debug`；公开源码不包含私钥、口令或可供下载的签名材料。本页取代旧文档中
“release 默认使用 debug signingConfig”的说明；这不代表已签发或验收公开安装包。

## 配置

在 `android/` 目录运行 Gradle。以下四项全部必填；每项环境变量优先于本地文件，
即使环境变量为空也不会回退。口令按原值读取，不会自动去掉空格。

| 环境变量 | `android/key.properties` 属性 |
| --- | --- |
| `SAYRIFT_SIGNING_STORE_FILE` | `storeFile` |
| `SAYRIFT_SIGNING_STORE_PASSWORD` | `storePassword` |
| `SAYRIFT_SIGNING_KEY_ALIAS` | `keyAlias` |
| `SAYRIFT_SIGNING_KEY_PASSWORD` | `keyPassword` |

个人构建可在本机创建 UTF-8 `android/key.properties`（Git 已忽略）：

```properties
# 以下均为占位内容，必须替换；不要提交填写后的文件。
storeFile=/absolute/private/path/sayrift-release.jks
storePassword=REPLACE_LOCALLY
keyAlias=REPLACE_LOCALLY
keyPassword=REPLACE_LOCALLY
```

Windows 路径使用正斜线，例如 `C:/private/sayrift-release.jks`；相对路径从 `android/`
解析，而非 `android/app/` 或当前终端目录。不展开 `~` 或路径中的环境变量。
文件采用 Java Properties 语法：反斜线是转义符，特殊口令优先通过环境变量注入。
配置文件是明文，限制为当前用户可读，勿放共享盘或同步目录。

CI 使用受保护的 secret 环境变量和临时挂载的 keystore 文件，注入上表四项。
不要在命令参数、脚本、日志、构建扫描或工作流 YAML 中填写真实口令。
不要给不受信任的 PR 注入签名凭据；签名任务不要启用 configuration cache，
不要上传整个工作目录或 Gradle 缓存。环境变量也属于敏感数据，关闭 shell trace。
任务结束后清理临时凭据，上传产物时仅选择经过检查的 APK/AAB。

## 构建与核验

Windows 使用 `./gradlew.bat`，macOS/Linux 使用 `./gradlew`（下例命令其余部分相同）。
JDK、SDK 和 Windows 短临时目录要求见 [README](README.md)。

```sh
# 开源贡献者 / 无凭据 CI：使用正常 debug 配置，不需要发布密钥。
./gradlew :core:test :app:assembleDebug --no-daemon --no-configuration-cache

# 无 SDK 也可检查必填项和文件可读性；缺项时给出名称，不打印值。
./gradlew :app:verifyReleaseSigning --no-daemon --no-configuration-cache

# 需要 SDK 和完整凭据；APK 与 AAB 都依赖签名预检。
./gradlew :app:assembleRelease --no-daemon --no-configuration-cache
./gradlew :app:bundleRelease --no-daemon --no-configuration-cache
```

依赖已缓存时可加 `--offline`。预检不读取私钥、不验证口令或 alias 是否正确；
完整构建由 Android Gradle Plugin 校验这些内容。错误口令、无效文件或错误 alias
会让签名失败。不要跳过验证任务（`-x`），也不要把手工修改构建脚本生成的 unsigned
产物当成正式发布包。无 SDK 的机器应先直接运行预检；完整构建可能先报告 SDK 缺失。

APK 位于 `app/build/outputs/apk/release/app-release.apk`；AAB 位于
`app/build/outputs/bundle/release/app-release.aab`。在安装或分发前，用已安装的
Android SDK build-tools 中的 `apksigner` 检查 APK：

```sh
apksigner verify --verbose --print-certs app/build/outputs/apk/release/app-release.apk
```

核对 SHA-256 签名证书指纹与独立保存的发布记录一致；旧 APK 也用同一命令核对。
Windows 对应 `apksigner.bat`。AAB 用 JDK 的 `jarsigner -verify -verbose -certs`
验证签名，并通过 `keytool -printcert -jarfile` 核对证书。Google Play 的 upload key
与最终分发 APK 的 app signing key 可能不同，必须分别记录。

## 既有个人安装的升级边界

包名仍为 `app.localtypeless.android`，不因签名改动而变化。原先个人安装使用的 debug
签名不能自动切换到新的生产证书；原地升级还要求兼容的版本号和相同签名身份。
**不要卸载旧应用来规避签名不匹配**：这会删除历史、设置及设备 Keystore 材料。

需要继续更新个人安装时，必须找到实际签署旧 APK 的原始 `debug.keystore`，并显式通过
上表填写它的文件路径、alias 与口令。这里没有自动寻找或重建原始密钥的功能。
这种显式配置只供个人兼容构建，不是公开生产签名；不要将这种 APK 作为生产发行包。
另一台电脑生成的同名 debug 文件并不是同一密钥。签名预检不判断密钥是否适合公开发布，
发布者须核对证书。公开生产密钥需另行由发布负责人安全创建或选定；本次改动不生成密钥，
不实施签名迁移、不安装手机。

## 备份与跨机器恢复

1. 将 keystore 存在仓库外的受限目录。JKS / PKCS12 文件、`key.properties` 已被忽略，
   但忽略规则不替代加密与权限管理，也不能阻止 `git add -f`。
2. 至少保留两份独立的加密备份，其中一份离线。用密码管理器单独保存 store password、
   key password、alias、格式（JKS / PKCS12）与恢复步骤，不把口令和未加密密钥一起分发。
3. 保存证书 SHA-256 指纹、包名、版本号和已签名产物的校验值。公开证书不是私钥备份。
4. 在可信机器恢复 keystore，调整本机路径，再注入凭据。用 `keytool -list -v -keystore`
   加文件路径交互输入口令核对证书；不要用命令行 `-storepass` 明文参数。
   有 SDK 时构建并校验签名，与原始记录比对后才安排单独的升级验收。
5. 保留原个人签名与生产签名的区别。丢失自行管理的签名私钥可能导致无法更新既有安装；
   不要覆盖旧备份，也不要把重新生成的密钥当成恢复。

## 本次验证记录（2026-10-05）

使用缓存的 Temurin JDK 21.0.4、Gradle 8.10.2、AGP 8.7.3，所有 Gradle 检查均为
`--offline --no-daemon --no-configuration-cache`：

- `:app:help` 与 `:app:preDebugBuild` 成功；临时 init script 断言包名未变，debug 与
  release 使用不同签名配置，debug 不依赖发布预检，release prebuild 依赖预检。
- 无凭据时，直接运行 `:app:verifyReleaseSigning` 和 `:app:preReleaseBuild` 均按预期失败，
  错误列出缺失的四项名称与配置指引。
- 仅使用合成属性和普通文本文件验证本地属性读取、环境覆盖、相对路径及
  `validateSigningRelease` 的预检依赖；文件存在性预检成功不等于完成密码学签名验证。
- 不存在的文件、覆盖本地口令的空白环境值均按预期拒绝；临时 `key.properties` 已删除。
  Git 忽略规则覆盖属性文件及 JKS / keystore / P12 / PFX。
- `:app:assembleDebug` 因 SDK location not found 停止，未安装 SDK。因此未完成 APK/AAB
  构建、真实密钥签名、产物证书核对或真机升级验收；未生成或读取真实签名密钥，未调用模型 API。

参考：[Android 官方应用签名文档](https://developer.android.com/studio/publish/app-signing)、
[命令行构建](https://developer.android.com/build/building-cmdline)。
