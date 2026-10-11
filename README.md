# PEX corner ITF 生成器

`metal_option.json` 配置模板和层序，通过 `"parameter_file": "parameters.json"` 引用独立参数文件。每个 option 生成 `build/<option>/CMAX.itf`、`TYPICAL.itf`、`CMIN.itf`。需要 Python 3.7 或更高版本，无第三方依赖。

## 使用 Excel 编辑参数

1. 用 Excel 打开 `parameters.csv`，修改参数行，保存为 **CSV UTF-8（逗号分隔）**。不要改列标题。
2. 运行 `py scripts/parameter_csv.py to-json parameters.csv parameters.json` 生成参数 JSON。
3. 运行 `py scripts/generate_itf.py`，或使用已有构建快捷键生成 ITF。

CSV 第一列是组件名，第二列是参数名，第三列是类型，第四至六列分别是数值、增量或百分率、方向。组件名和参数名分别填写，例如第一列 `INTER_METAL`、第二列 `TK_M`，不再使用点号拼接。全局参数的组件列留空。

```csv
component,parameter,type,typical,delta_or_percent,direction
INTER_METAL,ER_IMDA,same,5.0,,
INTER_METAL,TK_M,delta,0.3,0.03,-+
INTER_METAL,TK_IMDB,ratio,0.05,10,-+
INTER_METAL,RSH_M,ratio,0.05,30,+-
```

| 类型 | 第四列 | 第五列 | 第六列 | 生成值 `[CMAX, TYPICAL, CMIN]` |
| --- | --- | --- | --- | --- |
| same | 固定值 | 留空 | 留空 | 所有 corner 共用单值 |
| delta | typical 值 t | 非负增量 d | -+ | `[t-d, t, t+d]` |
| delta | typical 值 t | 非负增量 d | +- | `[t+d, t, t-d]` |
| ratio | typical 值 t | 非负百分率 p | -+ | `[t-abs(t)*p/100, t, t+abs(t)*p/100]` |
| ratio | typical 值 t | 非负百分率 p | +- | `[t+abs(t)*p/100, t, t-abs(t)*p/100]` |

百分率填写 `10` 或 `10%` 均表示 10%，`0.1` 表示 0.1%。方向按 CMAX、CMIN 排列，不代表物理量的大小。以上示例生成 `5.0`、`[0.27, 0.3, 0.33]` 、`[0.045, 0.05, 0.055]` 和 `[0.065, 0.05, 0.035]`。

当前 CSV 中独立介电厚度（TK_IMDC1、TK_IMDB、TK_IMDA、TK_PASS1～TK_PASS6）使用 `ratio,10,-+`，金属方阻 RSH_M 使用 `ratio,30,+-`，均以 TYPICAL 为基准对称增减。金属厚度 TK_M 保持原值，与金属平齐的 IMDc2 继续共用 TK_M；VIA RPV 保持原值。

CSV 使用 UTF-8 BOM 和标准逗号分隔，数值使用小数点。Excel 若未自动分列，可通过“数据 → 从文本/CSV”选择 UTF-8 和逗号分隔；方向列选择文本。保存 CSV 时保留 `-+`、`+-` 原文。

CSV 是日常编辑来源，JSON 是生成结果。生成前会检查全部行，格式错误显示英文行号信息。使用十进制计算，并以字符串写入 JSON。Excel 可能改变尾随零或超过 15 位的数字精度，需要保留时将相应单元格设置为文本。

已有参数 JSON 也可导出为 CSV：

```powershell
py scripts/parameter_csv.py to-csv parameters.json parameters_export.csv
```

JSON 只保存最终值，不记录最初使用 delta 还是 ratio。导出时单值变为 same，对称三值变为 delta；非对称三值会报错。日常请继续编辑原始 `parameters.csv`，保留自己选择的类型。

## 独立参数 JSON

```json
{
  "parameters": {},
  "components": {
    "INTER_METAL": {
      "ER_IMDA": "5.0",
      "TK_M": ["0.27", "0.3", "0.33"],
      "RSH_M": ["0.065", "0.05", "0.035"]
    }
  }
}
```

列表固定按 **[CMAX, TYPICAL, CMIN]**，必须正好三项；单值用于所有 corner。同一组件类型的所有实例共享其参数。根级 `parameters` 定义全局变量，`components` 中的参数覆盖同名全局值。MID、CORNER 等内置变量不能作为参数名称。

`parameter_file` 相对于 `metal_option.json` 所在目录，也支持绝对路径。仍兼容配置中的内联 parameters，同一作用域的内联值覆盖外部文件值。迁移保留原有 corner 数据，不进行工艺换算。

## 层序与 VIA 连接

metal_options 列表按从高到低书写：ALPA → 顶层金属 → inter metal，所有 VIA 条目放最后。例如五层金属：

```json
[
  "ALPA2", "MTT", "TM", "INTER_METAL", "INTER_METAL", "INTER_METAL",
  {"component": "VIA", "name": "PA", "connect": [5, 6]},
  {"component": "VIA", "connect": [4, 5]},
  {"component": "VIA", "connect": [3, 4]},
  {"component": "VIA", "connect": [2, 3]},
  {"component": "VIA", "connect": [1, 2]}
]
```

输出导体依次为 ALPA、metal5、metal4、metal3、metal2、metal1。MID 表示金属组编号，最低金属始终为 1，向上递增；ALPA 不占 MID。模板中的介电层与所属金属共用 MID。

每个 VIA 必须设置 connect，按 `[下方导体序号, 上方导体序号]` 引用该 option 的导体。导体序号从底部向上计数，包含 ALPA：上述例子中 1～5 是 metal1～metal5，6 是 ALPA。它不计入 frontend 中固定声明的 poly/diff 层。

连接不依赖导体名称；自定义 metal 名称后 VIA 自动引用最终名称。VIA_ID 默认使用 connect 的下方序号，所以上述 VIA 依次命名为 PA、V4、V3、V2、V1。名称可通过实例 name 或组件 name 覆盖。

## 文件输出顺序

1. `header_template`：`templates/header.itf.j2`，始终最先输出，包含 TECHNOLOGY，可追加全局定义。
2. metal_options 中的非 VIA 组件：ALPA、top metal、inter metal，由高到低。
3. `suffix_templates`：当前为 frontend.itf.j2，保留 npoly、ppoly、tox、FOXB、ndiff、pdiff、FOXA 等前中段结构。
4. metal_options 末尾的 VIA 组件。
5. `via_templates`：当前为 frontend_vias.itf.j2，包含从原 frontend 拆出的接触孔，保证所有 VIA 位于末尾。

header、suffix、via 模板使用全局 parameters。所有模板路径相对于 metal_option.json 所在目录；支持绝对路径。模板内部的空行、缩进和换行原样保留，脚本不清理空白。每个模板末尾应保留所需换行，避免相邻片段粘连。

## 名称与模板变量

默认命名规则为 `metal{{ MID }}`、ALPA、`V{{ VIA_ID }}`。名称优先级为实例 name → 组件 name → naming。例如 `{"component": "MTT", "name": "top{{ MID }}"}` 只改当前实例名。

所有模板变量使用大写：MID、PAD_ID、VIA_ID、LAYER_ID、LAYER、COMPONENT、LOWER_LAYER、UPPER_LAYER、PREVIOUS_LAYER、NEXT_LAYER、METAL_OPTION、CORNER。CORNER 为 CMAX、TYPICAL 或 CMIN。MID 只在 metal 类型实例中提供；LAYER 是最终名称，LOWER_LAYER/UPPER_LAYER 是 VIA 的连接名称。

导体字段统一为：

```text
CONDUCTOR {{ LAYER }} { THICKNESS={{ TK_M }} RPSQ={{ RSH_M }} WMIN={{ WMIN }} SMIN={{ SMIN }} RESISTIVE_ONLY_ETCH={{ RETCH }} CAPACITIVE_ONLY_ETCH={{ CETCH }} }
```

inter_metal、tm、mtt 组内顺序为 IMDc2 → 导体 → IMDc1 → IMDb → IMDa；TK_M 同时用于导体与 c2，ER_IMDC 用于 c1/c2；a/b 分别使用 TK_IMDA/ER_IMDA、TK_IMDB/ER_IMDB。ALPA1、ALPA2 均使用 PASS6～PASS1 结构。ALPA2 已同步更新后的模板参数，移除旧的 IMD 参数，保留原有金属参数；PASS 参数使用示例值：典型厚度 0.05（CMAX 减 10%、CMIN 加 10%）、ER 3.0，PASS6/PASS5 的 TW/SW 为 0，可在 CSV 中独立调整。

VIA 保留用户模板的 `RPV={{ RPV_M }}`，目前 RPV_M 填写演示单值 10，并未从此前 RSH_M 换算。所有示例参数需按工艺填写，脚本不验证 ITF 语法、单位或物理合法性。MIM10 仅为 option 名的一部分，不隐式生成结构。

## 校验与迁移

全部目标渲染成功后才写文件。缺失变量、错误长度的 corner 列表、重复实例名、无效 VIA 连接以及 VIA 后出现非 VIA 组件会报错。仅支持双括号变量替换，不支持 Django 表达式、循环或过滤器。

已移除 --config 参数及独立 corners.json。原配置和旧 rcmax/rcmin 输出归档于 `.review/corner-migration/`；默认构建不读取归档。新输出采用大写 corner 文件名；同名文件覆盖，其余用户文件保留。

## VS Code 快捷键

默认构建任务已指向组合生成脚本。已有的 `Ctrl+B` 构建快捷键可继续使用；本次无需修改用户快捷键。VS Code 默认构建快捷键为 `Ctrl+Shift+B`，默认 `Ctrl+B` 用于侧边栏。

如果尚未配置 `Ctrl+B`，在 VS Code 的用户快捷键 JSON 数组中合并以下条目。VS Code 不读取工作区中的 `keybindings.json`：

```json
{
  "key": "ctrl+b",
  "command": "workbench.action.tasks.build",
  "when": "editorTextFocus && resourcePath =~ /^d:[\\\\/]proj[\\\\/]public[\\\\/]pex_editor[\\\\/]/i"
}
```

此快捷键仅在编辑器聚焦本项目文件时生效；移动项目后需要调整路径。也可从命令面板运行默认构建任务。

## 命令行

```powershell
py scripts/generate_itf.py
py scripts/generate_itf.py --metal-option 1P5M_4Ic_1MTTc_ALPA1_MIM10
py scripts/generate_itf.py --corner CMAX
py scripts/generate_itf.py --metal-options path/to/metal_option.json --output-dir build/custom
py -m unittest discover -s tests -v
```

--corner 接受 CMAX、TYPICAL、CMIN 或 all，不区分大小写。默认生成所有 option 和三个 corner。VS Code 默认构建任务已同步，不再传 --config。Linux/macOS 将 py 替换为 python3。
