# 上游许可原文与来源

获取日期：2026-10-05。这些文件以原始 UTF-8 字节保存，未替换版权年份、版权人、适用范围或条款。
它们只适用于相应第三方作品；Sayrift 自有代码采用根目录的 MIT 许可证。

| 本地文件 | 上游来源与固定修订 | 字节数 | SHA-256 |
|---|---|---:|---|
| [Lucide-ISC-Feather-MIT.txt](Lucide-ISC-Feather-MIT.txt) | [lucide-icons/lucide 的 LICENSE](https://raw.githubusercontent.com/lucide-icons/lucide/e715245d62667c800e7f54c94b1b023692e900a3/LICENSE)，提交 `e715245d62667c800e7f54c94b1b023692e900a3`（2026-03-20） | 3208 | `b495047bd93a9b06913511076f504daba17d5bbeb3e0650f3bb53a4220329c57` |
| [Feather-MIT.txt](Feather-MIT.txt) | [feathericons/feather 的 LICENSE](https://raw.githubusercontent.com/feathericons/feather/a299aad93bffe2b85ad49d49aa04aff735d52a65/LICENSE)，提交 `a299aad93bffe2b85ad49d49aa04aff735d52a65`（2023-08-20） | 1082 | `308028e93fcf84972523cdf6e616f73168546b4953895f516d01287f16fe7bee` |
| [Qt-LGPL-3.0-only.txt](Qt-LGPL-3.0-only.txt) | [Qt 官方 qtbase，v6.11.2，LICENSES/LGPL-3.0-only.txt](https://raw.githubusercontent.com/qt/qtbase/v6.11.2/LICENSES/LGPL-3.0-only.txt) | 7651 | `da7eabb7bafdf7d3ae5e9f223aa5bdc1eece45ac569dc21b3b037520b4464768` |
| [Qt-GPL-3.0-only.txt](Qt-GPL-3.0-only.txt) | [Qt 官方 qtbase，v6.11.2，LICENSES/GPL-3.0-only.txt](https://raw.githubusercontent.com/qt/qtbase/v6.11.2/LICENSES/GPL-3.0-only.txt) | 35147 | `8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903` |
| [libsndfile-LGPL-2.1.txt](libsndfile-LGPL-2.1.txt) | [libsndfile，1.2.2，COPYING](https://raw.githubusercontent.com/libsndfile/libsndfile/1.2.2/COPYING) | 26518 | `ad01ea5cd2755f6048383c8d54c88459cd6fcb17757c5c8892f8c5ea060f6140` |
| [Apache-2.0.txt](Apache-2.0.txt) | [JetBrains Kotlin，v2.0.21，license/LICENSE.txt](https://raw.githubusercontent.com/JetBrains/kotlin/v2.0.21/license/LICENSE.txt) | 11358 | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |

Lucide 文件本身含 ISC 和 Feather 派生图标的 MIT 两段条款；不要删掉后半段或将其改写为一个 ISC 标签。
Feather 独立文件的版权年份为 `2013-2023`；Lucide 文件里的 Feather 版权文字为 `2013-present`。
这里保留各自上游原文，没有人为统一。固定许可证修订不等于已证明每个内嵌 SVG 最初导入时的修订。

Qt LGPLv3 文本纳入 GPLv3 条款，因此一起收录。此举只补充许可文本，不声明 Qt/PySide6/Shiboken
二进制的准确对应源码、修改材料、源码获取安排或库替换验证已经完成。

本目录是仓库维护的补充材料，不重复收录所有安装环境中的 wheel 许可证。构建时提取的组件版权、
许可证、NOTICE 仍要随适用制品提供；通用 Apache/GPL 文本不能替代它们。
原生库、字体、编解码器、Qt 附带组件及评测语音的待办见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

更新任一文件时，重新从记录的上游获取，核对来源与全文，并同步更新修订、字节数和 SHA-256。
校验应以仓库中这些 `.txt` 的原始字节为准，不先转换换行符或编码。

`libsndfile-LGPL-2.1.txt` 第 149 行的行尾空白和末尾空行来自上游原文，为保持字节及哈希一致而保留；
`git diff --check` 会提示这两处。编辑本仓库说明时不应顺手格式化这些许可原文。
