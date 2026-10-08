# StarRC ITF 开发样例

本目录提供 5 个虚构工艺 ITF 输入样例，覆盖 TYP、CMAX、CMIN、RCMAX、RCMIN，
用于共同开发解析器、叠层组装和 corner 输出功能。

## 脱敏范围

- 所有 1,065 个数值参数均替换为虚构值，并非按真实数据统一缩放。
- 删除公司及个人联系信息注释，TECHNOLOGY 改为 DEMO_PROCESS_<corner>。
- 保留层名、层引用、字段顺序、空格、换行、表格维度和坐标顺序。
- 保留科学计数法或普通小数表示以及小数位数；标识符中的层号不变。

数值用于功能开发，不代表真实工艺或经过校准的 RC corner，不可用于签核或制造。
目前完成文本结构、表格坐标、via 引用和脱敏检查；未执行 StarRC/grdgenxo。

## 文件

- starrc_TYP.itf
- starrc_CMAX.itf
- starrc_CMIN.itf
- starrc_RCMAX.itf
- starrc_RCMIN.itf
- SHA256SUMS.txt：上述 5 个 ITF 的校验值。
- validation.json：检查范围及结果，不包含真实参数或原始文件校验值。

在本目录内可用 `shasum -a 256 -c SHA256SUMS.txt` 核验文件完整性。
