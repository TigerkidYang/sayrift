# Android 历史保留与删除边界

2026-10-05，基于发布准备提交 `0022150`。本次仅修改 `Store.kt`；数据库仍是
`history.db`、schema version 1，不改表结构、不重建数据库、不改界面和控制器。

## 保留期限

`Store` 每次新增、读取历史、预览删除数量、读取首页统计或花费统计时，都重新读取
既有 `settings` SharedPreferences 的 `keep` 值。与 `Prefs.keep` 使用同一存储，不缓存启动时的值。

- `forever`：保留历史；不存在或无法解析的值沿用原有无限期行为。
- 正整数天数：删除 `time < 当前时间 - 天数 × 86_400_000` 的历史；恰好位于边界的记录保留。
- `never`、零或负整数：删除全部历史，包括未来时间戳，不新增历史正文。
- `keepEntry = false` 仍然只记录用量。即使调用方传入 `true`，也不能绕过当前的保留期限。
  因此旧 JSON 导入和延迟到达的结果不会重新保存已经过期的正文。

新增时，过期清理、用量新增和允许保存的历史新增在同一事务内完成；写入失败时回滚，
不留下只有半条会话的数据变更。删除、清空及保留期清理只操作 `entries`，不删除 `usage`。
用量记录仍包含时间、模式和数值统计，不保存正文或音频。

读取时确实删掉记录才发出 `revision` 更新，避免观察者因无变化的清理反复加载。
`countDeleted` 先执行已生效的保留策略，再计算候选策略的删除数量；仅预览候选策略不会应用它。

这不是定时清理任务：进程闲置、已停止或页面没有再次请求数据时，不保证在到期瞬间删除。
每次操作按当时读到的设置和设备时钟执行；随后发生的设置变化由下一次操作处理。
已经交给界面、剪贴板或其他应用的文本不受数据库清理控制。

## SQLite 连接设置

在 `onConfigure`、任何建表或写入之前启用 `PRAGMA secure_delete = ON`。

- 所有支持的 Android 版本均在打开时通过 `rawQuery` 设置；每次写事务开始后再次设置。
  事务把线程固定到执行写入的连接，避免连接被替换后失效。不声称配置了所有只读连接。
- 未使用 API 30 的 `execPerConnectionSQL`：初始 Android 11 的原生执行路径会拒绝此 PRAGMA
  返回的结果行；不能用新版本框架行为推定旧版本兼容。此限制经 Android 11 AOSP 源码复核。
- 用 `finally` 结束事务。没有在事务中执行 `VACUUM`、检查点或切换日志模式。

依据：[Android API 30 新增方法](https://developer.android.com/sdk/api_diff/30/changes/android.database.sqlite.SQLiteDatabase)、
[SQLiteDatabase API](https://developer.android.com/reference/android/database/sqlite/SQLiteDatabase.html)、
[SQLiteOpenHelper 生命周期](https://developer.android.com/reference/android/database/sqlite/SQLiteOpenHelper)。

## 旧空闲页：本次没有清理迁移

`secure_delete = ON` 影响启用后的删除和更新，不会追溯清理此前已释放页面里的内容。
SQLite 官方建议对先前删除的数据执行 `VACUUM`；但它会重写数据库，可能需要额外空间和较长时间。
当前 `App.onCreate` 同步打开 Store，读写也可能由界面线程调用；没有适合维护迁移的后台调度、
失败重试和并发协调机制。`SQLiteOpenHelper.onUpgrade` 又在事务内运行，不适合执行 `VACUUM`。
在本次仅限 Store 的修改范围、且没有 Android SDK 的条件下，不加入无法验证的启动阻塞或后台维护任务。

因此没有版本升级标记、没有一次性 `VACUUM`，也没有删除数据库、清空有效历史或重算用量。
日后若增加维护迁移，应在后台、事务外执行，协调其他访问，处理空间不足及中断，仅在成功后标记完成，
并用合成的旧数据库验证历史 ID、正文和用量均保留。

**不承诺磁盘擦除或不可恢复。** 旧空闲页、旧日志、系统或手工备份、文件系统和闪存的历史副本
可能仍有残留；本次不扫描或覆盖这些位置。设置也不等于数据库加密。
详见 [SQLite secure_delete](https://www.sqlite.org/pragma.html#pragma_secure_delete) 和
[VACUUM 的空间与事务限制](https://www.sqlite.org/lang_vacuum.html)。

## 本次验证及限制

全部使用源码、合成数据或本地测试替身；没有接触真实历史、手机、模型 API，也没有推送。

- `gradlew.bat --offline :core:test --no-daemon --console=plain`：10 个核心测试通过，零失败和错误。
  首次运行遇到 Java loopback 临时路径问题；按 `android/README.md` 使用独立短 TEMP/TMP 后通过。
  **core 测试不编译或验证 Android app/Store。**
- 缓存的 Kotlin 2.0.21 编译器编译实际修改后的 `Store.kt`，配合轻量 Android 内存测试替身：
  51 个断言通过，分别模拟 API 29、30、35。覆盖读时清理、无变化不触发 revision、
  新增时清理、过期导入、设置即时变化、never、未来时间戳、clear/delete、用量保留、
  各版本写连接替换后的重新配置，以及插入失败时回滚并结束事务。
  临时测试替身位于本工作树忽略的 `build/history-privacy-check/`，不作为 Android 框架实现证明。
- Python SQLite 3.39.4 合成库：DELETE、WAL 两种日志模式共 18 个断言通过。
  覆盖事务内启用 secure_delete、严格小于的时间边界、清理后的有效行和用量保留、回滚、
  全部删除及 `integrity_check`。不以文件字节检查声称磁盘擦除。
- `git diff --check` 通过。没有 Android SDK，未构建 APK，未运行 Android instrumentation 或真机测试。

后续 Android 验收需要合成测试库：API 29 与 API 30+ 的打开/关闭/重新打开、WAL 多连接、
长时间存活进程的到期读取和新增、保留设置切换、磁盘写入失败回滚，以及旧版本库升级后
有效历史和全部用量不变。应同时观察大历史库的主线程延迟；本次未测量真机延迟。

兼容性复核：[Android 11 SQLiteConnection](https://android.googlesource.com/platform/frameworks/base/+/android-11.0.0_r1/core/java/android/database/sqlite/SQLiteConnection.java)、[Android 11 原生执行路径](https://android.googlesource.com/platform/frameworks/base/+/android-11.0.0_r1/core/jni/android_database_SQLiteConnection.cpp)。修正后的 51 个测试替身断言通过，仍不等同真机验证。
