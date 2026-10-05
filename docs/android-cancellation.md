# Android 会话取消与剪贴板隐私

本修复基于 `0022150`，范围仅限 Android 请求生命周期、无障碍服务插入回退和专项测试。

## 请求所有权

- 每次开始听写创建新的 `RequestSession`。主线程创建并捕获 client、设置、时长和令牌，然后交给工作线程；取消后再次开始不会复用旧令牌。
- 每个实际 OkHttp `Call` 在执行前登记到所属令牌，响应体读取结束后才解除登记。登记与取消使用同一把锁；若取消先发生，新 Call 会直接取消并抛出 `CancellationException`。
- `cancel()`、服务解绑或销毁调用 `abort()`，同时取消正式请求和预热请求。解绑带服务实例检查，旧服务销毁不会取消新服务的会话。
- 取消异常不属于 `OpenRouterException`，因此不进入网络重试、模型 fallback 或界面网络报错路径；每次重试、fallback 和流水线阶段边界再次检查令牌。
- 预热拥有独立令牌，在独立线程任务上运行。开始正式处理时取消预热，不等待预热结束。共享连接池不等于共享取消范围，不调用 dispatcher 的 `cancelAll()`。
- 主线程仍按会话编号和服务实例丢弃过期回调，避免已排队的结果插入新输入框。已完整返回的旧结果仍沿用现有逻辑只记录费用数字。

取消不能撤回已经到达服务商的请求，也不能保证免计费；若取消时未取得用量响应，本地费用可能少于服务商账单。本补丁不修改 Store 或费用记账模型。

## 剪贴板：受限制时不自动覆盖

Android 10 起，非当前焦点应用且非默认输入法通常不能读取剪贴板。无障碍输入连接不应被当作默认输入法的剪贴板权限；读取不到也不能解释为“原来为空”。公开 ClipboardManager API 没有原子的 compare-and-restore：先检查自有标记、再恢复/清空仍可能覆盖两步之间用户复制的新内容。

因此本补丁采用安全降级，而不声称实现了平台无法保证的恢复：

- 自动插入仍优先 InputConnection，其次 ACTION_SET_TEXT。
- 上述方式失败后，不再写入临时剪贴板并执行 ACTION_PASTE；显示现有结果卡片，由用户明确点击复制。隐藏输入框且无输入连接时也改为结果卡片，不再自动复制。
- 所有此服务的复制入口统一通过 `SensitiveClipboard.copy` 写入 `android.content.extra.IS_SENSITIVE=true`，兼容本项目 API 29 下限。
- 显式复制用于手动粘贴，保留内容供用户使用；没有定时恢复/清空，也不在取消、解绑、销毁时改动剪贴板。所以后续用户复制不会被旧会话的清理覆盖。
- “条件恢复/清理”的安全条件是能够可靠确认当前内容归属，并原子地替换它；当前平台接口无法满足，所以不创建需要自动恢复的临时剪贴板内容。**本补丁未实现尽力而为的自动恢复**。

行为代价：依赖 ACTION_PASTE 的旧应用现在需要用户在结果卡片点复制后手动粘贴。敏感标志用于隐藏受支持系统/键盘的预览，不是加密，也不保证所有 OEM 键盘不保留历史。显式复制仍会按用户意图覆盖当前剪贴板，不恢复复制前的内容。

依据：[Android 10 剪贴板读取限制](https://developer.android.com/about/versions/10/privacy/changes#clipboard-data)、[安全剪贴板处理](https://developer.android.com/privacy-and-security/risks/secure-clipboard-handling)、[ClipboardManager API](https://developer.android.com/reference/android/content/ClipboardManager)。

## 离线验证

`CancellationTest` 使用 localhost MockWebServer 或进程内拦截器，不连接 OpenRouter，不读取真实 key：

1. 取消先于任务开始/Call 登记时不发请求。
2. ASR 挂起、chat 挂起和响应体读取期间均取消实际 Call，并阻止后续请求。
3. 取消同时遇到网络、超时和 HTTP 错误时不重试、不 fallback。
4. ASR 完成与 chat 开始之间取消时不启动下一阶段。
5. 旧令牌反复取消不影响已经在途的新会话。
6. 预热卡住时正式请求仍可完成，取消预热不取消正式请求。
7. 未取消的普通网络错误仍保留一次重试。

运行（PowerShell，仓库根目录）：

```powershell
./android/gradlew.bat -p android :core:test --offline --no-daemon --console=plain
```

Windows 上如遇 JDK Unix socket 临时路径过长，请先按 [Android README](../android/README.md) 设置独立的短 TEMP 目录。本次运行：BUILD SUCCESSFUL；19 项全部通过（新增 CancellationTest 9 项、既有隐私 5 项、流水线 5 项），无跳过。`git diff --check` 通过。

SDK 不可用，本次未编译 Android app、构建 APK、安装手机或执行真机验证。核心 JVM 测试不验证 Android 系统敏感预览、OEM 键盘行为、真实取消按钮/解绑事件、结果卡片和插入兼容性；这些仍需设备验收。

建议设备验收：慢网络下取消后立即开始新会话；处理中停用再启用无障碍服务；在插入失败卡片点击复制确认敏感预览；随后手动复制另一段内容，再取消或解绑服务，确认新内容保持不变。
