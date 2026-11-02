# 财税 Harness

版本：0.2.1。主README说明最新用法，历史阶段与维护方式请从以下入口查看：

- [第一阶段说明（整理恢复版）](docs/stages/phase1-README.md)
- [第一阶段原有验收报告](reports/第一阶段验收结果.md)
- [第二阶段实现及验证](reports/第二阶段进展与验证说明.md)
- [版本维护、备份和回滚](docs/maintenance.md)
- [按版本追加的变更记录](CHANGELOG.md)

这是云账房赛题二的本地业务工具项目。已实现原始数据导入、金额查询、九月用途检查、权限控制、用途与备注修改、保存后回读，以及修改审计记录。当前提供命令行和交互菜单。

第二阶段已增加Ollama自然语言对话、工具调用、同一会话内的追问与更正和逐轮运行记录。跨会话任务记忆和完整知识管理仍待下一阶段实现。原有第一阶段命令保持可用。

## 第二阶段 AI 对话

先启动Ollama并准备模型：

```powershell
ollama pull qwen3:8b
python -m tax_harness chat --user U001 --company C001
```

也可双击 `chat.cmd`。此入口固定U001和甲企业，不预设月份。切换企业或用户须退出后重新启动，例如 `python -m tax_harness chat --user U002 --company C001`。U002仍只有查看权限。模型名称可通过 `--model` 指定；0.6B模型已在初步实测中出现明显错误，不建议用于比赛演示。

可按顺序输入：

```text
查一下发票总额。
查2026年9月发票总额、银行收入和支出。
这个月哪些发票必须补用途？
给F002补一下用途。
用途填：客户资料打印。
还是改成：员工培训资料打印。
/confirm
现在再检查用途缺项。
/exit
```

修改先生成草稿，明确显示尚未保存；输入 `/confirm` 才真正提交并回读，`/cancel` 取消。任何普通新消息都会使旧草稿失效，更正内容会重新生成草稿。用户本轮必须明确给出所填写的文本，程序拒绝模型推测的用途。当前同一时刻仅支持一张发票的修改草稿。发票在等待确认时被其他操作更改，会拒绝提交旧草稿。

`data/traces/` 下按会话生成JSONL记录，包含用户输入、实际模型输入、工具定义、工具结果及保存回读。记录留在本地，含模拟业务数据，按需保管。新启动是新会话；该文件只用于追溯，不会自动成为跨会话记忆。

真实模型验收命令：

```powershell
python scripts/verify_ollama.py --model qwen3:8b
```

该命令使用独立临时库，真实模型输入和结果保存在 `reports/stage2-traces/`，汇总保存在 `reports/stage2-live-qwen3-8b.json`。它会检查追问、金额、用途缺项、草稿、更正、确认保存、最新数据及权限等流程。原有 `data/business.sqlite3` 不会被自测修改。

工具调用接入依据：[Ollama官方说明](https://github.com/ollama/ollama/blob/main/docs/capabilities/tool-calling.mdx)。

## 立即使用

项目位置：`C:\Users\wsco\Documents\ChatGPT\云账房比赛\tax-harness`

最方便的方式是双击本目录中的 `start.cmd`，按菜单数字操作。默认身份为 U001、企业为 C001、月份为 2026-09。菜单 1 可以切换；2 查金额；3 查用途缺项；4 查单张发票；5 修改用途或备注；6 查看修改记录；0 退出。修改菜单输入空内容会清空选定字段。

也可以在 VS Code 中打开本目录，打开终端运行：

```powershell
cd "C:\Users\wsco\Documents\ChatGPT\云账房比赛\tax-harness"
python -m tax_harness menu
```

只使用 Python 标准库，无需执行 pip install，无需启动 Ollama。已在本机 Python 3.13.5 上验证。若终端中文显示异常，可使用 `python -X utf8` 替换示例中的 `python`，或使用已经设置 UTF-8 的 `start.cmd`。

如安装了 VS Code Python 调试扩展，可用项目内的启动配置调试菜单或自动测试。

## 命令行操作

以下命令均在项目目录内执行。

### 初始化

```powershell
python -m tax_harness init
```

默认读取 `data/source/02_示例数据.xlsx`，将40张发票、48条流水、企业与权限导入 `data/business.sqlite3`，同时导入五条规则记录。首次使用菜单也会自动初始化。已有数据库时保留当前数据，重复启动和重复 init 都不会覆盖修改。

源文件是赛题材料的副本，保留在 `data/source/`，程序不会写入源文件。`data/rules.json` 是按同包业务规则整理的初始结构化规则摘要，保留规则编号、版本、企业、生效日期、状态和执行条件。完整依据保留在 `data/source/03_业务规则.docx`。修改规则 JSON 不会自动改变已经导入的数据库。

如需一套独立练习数据，可指定新的数据库文件，无需删除当前数据：

```powershell
python -m tax_harness --db data/practice.sqlite3 init
python -m tax_harness --db data/practice.sqlite3 menu
```

### 查金额

```powershell
python -m tax_harness totals --user U001 --company C001 --month 2026-09
```

初始结果：发票10张，合计9622.06元；银行12条，收入13000.50元，支出7180.74元。三个金额分别计算，不相互抵销。

### 查用途缺项

```powershell
python -m tax_harness check --user U001 --company C001 --month 2026-09
python -m tax_harness check --user U001 --company C002 --month 2026-09
```

初始甲企业缺 F002、F003、F004、F006、F009，使用甲企业2.0版规则；乙企业缺 F002、F005、F006，使用乙企业1.0版规则。仅检查2026年9月用途完整性，8月可查询金额。

### 查单张发票

```powershell
python -m tax_harness invoice --user U001 --company C001 --invoice F002
```

企业和发票编号共同定位，两家企业的同号发票是不同记录。

### 保存并回读

```powershell
python -m tax_harness update --user U001 --company C001 --invoice F002 --purpose "客户资料打印" --remark "用户补充说明"
python -m tax_harness invoice --user U001 --company C001 --invoice F002
python -m tax_harness check --user U001 --company C001 --month 2026-09
```

执行后真实修改本地数据库，用新连接回读。甲企业初始5张缺项变为4张，乙企业F002不变。用途和备注可分别修改；未指定的字段保持原值。不能修改金额、日期、销售方、票面项目、企业或任何银行流水。不能从票面项目自动猜用途；备注不替代用途。

可选参数 `--operation-id demo-001` 用于避免同一次请求重复写入。重试时使用相同编号和内容；新的更正使用新的编号，或省略该参数由程序自动生成。历史操作重试只回读当前值，不会覆盖之后的更正。

### 验证权限

```powershell
python -m tax_harness totals --user U002 --company C001 --month 2026-09
python -m tax_harness totals --user U002 --company C002 --month 2026-09
python -m tax_harness update --user U002 --company C001 --invoice F002 --purpose "测试"
```

第一条允许查询；后两条应报 `permission_denied` 并返回退出码1，数据不变。U001可查看两家企业并修改发票用途、备注；U002仅可查看甲企业。命令行用户参数是本地演示身份选择入口，当前没有账号登录认证。后续模型接入时，用户身份须由入口固定注入。

### 查修改记录

```powershell
python -m tax_harness audit --user U001 --company C001
```

查看该企业最近100条保存记录，包括操作编号、用户、时间、修改前后数据及请求内容。只有保存操作产生审计记录；完整模型输入与工具调用追踪属于后续阶段。

### 结构化输出

```powershell
python -m tax_harness --json totals --user U001 --company C001 --month 2026-09
```

全局参数 `--db`、`--json` 写在子命令之前。成功输出到stdout，错误输出到stderr。成功退出码0，业务或存储失败退出码1，命令参数错误退出码2。成功无记录返回零及 `no_records: true`；无权限或失败返回错误，不伪装成零。月份必须明确指定，不能默认当前月份。

## 自测

```powershell
python -m unittest discover -s tests -v
python scripts/smoke_test.py
```

也可双击 `selftest.cmd` 运行自动测试。

自动测试覆盖全部第一阶段验收目标，以及字段白名单、空白用途、备注不能替代用途、规则停用、幂等、失败回滚、持久化和错误退出码。每项使用独立临时数据库，位于项目 data 目录，运行后清理，不污染 `business.sqlite3`。

冒烟测试会启动独立Python进程执行真实命令行，包括导入、四组金额、用途清单、修改、跨企业隔离、权限拒绝、重复初始化和交互菜单。最新记录保存到 `reports/stage1-smoke.json`。

| 企业 | 月份 | 发票合计 元 | 银行支出 元 | 银行收入 元 |
| --- | --- | --- | --- | --- |
| C001 | 2026-08 | 9046.35 | 5720.99 | 14850.75 |
| C001 | 2026-09 | 9622.06 | 7180.74 | 13000.50 |
| C002 | 2026-08 | 13667.05 | 9341.10 | 18800.25 |
| C002 | 2026-09 | 12667.24 | 8087.24 | 13700.75 |

两家企业七月均无记录，有权用户查询时三个金额均为0.00。

## 项目结构

```text
tax-harness/
  tax_harness/
    excel.py          只读XLSX导入和整数分转换
    store.py          数据库结构和初始化
    service.py        查询、规则检查、权限、保存和回读工具
    __main__.py       命令行和交互菜单
  data/
    source/           原始材料副本
    rules.json        初始结构化规则摘要
    business.sqlite3  当前保存的数据，首次初始化生成
  tests/              自动化验收
  scripts/            独立进程冒烟测试
  reports/            验收记录
  .vscode/            调试配置
  start.cmd           双击启动
  selftest.cmd        双击测试
```

后续接入模型时可以直接调用 Service.totals、invoice、check、update 等工具。金额按整数分存储和汇总，权限在业务工具层执行，修改与审计在同一事务中提交。当前规则表保存五条初始记录，尚未提供规则导入、更新、停用的管理命令。
