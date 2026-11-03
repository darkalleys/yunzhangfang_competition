# 第三阶段 持久任务偏好与规则维护

完成日期：2026年11月3日。版本0.3.0。本阶段开始前，第二阶段代码已确认与GitHub一致。

## 已完成

- 每个用户、企业最多保存一个未完成的九月用途检查任务，记录月份、待补编号及更新时间。完成后关闭活动任务；新会话及保存后重新查询当前数据。
- 新会话恢复任务和月份，不恢复对话全文、草稿或修改授权；旧任务不能直接用于保存。
- 明确偏好支持设置、查看、更正、删除，带来源且按用户和企业隔离。每组最多10项，每项最多500字符，仅影响表达方式，不能改变权限或规则。
- 本地规则管理员可查找、导入新版本、启用和停用规则。正文与结构化执行条件一起提交；程序校验字段、日期、门槛和冲突，再通过事务保存。
- 同编号同版本内容不可覆盖，更新通过新版本完成。同一生效日期的冲突启用会回滚，停用规则不参与当前判断。
- 模型可查询适用规则。运行记录保留选用的记忆和规则，新模型验收按批次保存，不再覆盖旧阶段证据。

规则正文与执行条件的语义一致性仍须维护者审核；程序不自动证明自然语言全文与条件等价。规则管理属于本地可信管理员入口，没有开放给模型写入。普通业务权限继续由程序检查。

## 升级与启动

在tax-harness目录运行：

```powershell
python -m tax_harness migrate
python -m tax_harness chat --user U001 --company C001
```

旧库升级前自动生成SQLite一致性备份，然后在事务内增加tasks、preferences、state_events、rule_events四张表。原业务、权限、规则和审计不重置。重复迁移不重复创建，新初始化直接使用新结构。

本机已升级。升级前备份为 `backups/20261103T135333Z-14a59780`，升级前后逐表比较了全部原记录，均未改变。自测使用临时库，默认库没有自测产生的偏好和任务。

## 跨会话演示

先输入：

```text
检查2026年9月哪些发票需要补用途。
/pref style 回答保持简洁
将F002用途填写为客户培训资料打印。
/exit
```

重新启动同一用户和企业后输入：

```text
/memory
/confirm
继续上次检查，列出还需要补用途的发票。
将F002用途填写为员工培训资料打印。
/confirm
/exit
```

退出前的草稿不会恢复，因此新会话第一条/confirm应提示没有草稿。必须重新明确要求修改并确认，才会保存；再次启动继续检查时，应看到最新四张缺项。

## 偏好与任务管理

```text
/prefs
/pref style 回答详细
/forget style
/memory
/task-clear
```

偏好采用显式命令管理，当前不从普通自然语言自动抽取隐含偏好。删除后不再注入新轮次上下文；历史审计日志不会作为偏好载入。

独立管理入口：

```powershell
python scripts/manage.py memory --user U001 --company C001 show
python scripts/manage.py memory --user U001 --company C001 set --key style --value "回答简洁"
python scripts/manage.py memory --user U001 --company C001 delete --key style
python scripts/manage.py memory --user U001 --company C001 task-clear
python scripts/manage.py memory --user U001 --company C001 task-set --month 2026-09
```

task-set重新检查并替换活动任务，用途任务仍限2026年9月。查询失败、权限变化或规则缺失时保留任务，不误报完成；恢复受阻时需先修复规则或通过管理入口清除任务。

## 规则维护

```powershell
python scripts/manage.py rules list --query 甲企业
python scripts/manage.py rules import --file path/to/new-rules.json
python scripts/manage.py rules status --rule R002 --version 2.0 --status inactive
python scripts/manage.py rules status --rule R002 --version 2.1 --status active
```

导入文件格式参考data/rules.json，使用JSON数组。新版本先以inactive导入，核对正文、企业、日期、kind及整数分门槛，再停用需替换的旧版并启用新版。先导入新版本，不能直接执行示例中的2.1启用命令。相同日期的冲突版本不会同时启用。

规则变化演示请用练习库：先 `python -m tax_harness --db data/practice.sqlite3 init`，再将全局参数 `--db data/practice.sqlite3` 放在manage.py与rules之间。默认初赛规则保持原样。

## 验证

- 52项程序测试通过，含原40项和12项新增测试，输出在reports/phase3/unit-tests.txt。
- 原10项真实模型回归通过，记录在reports/phase3/stage2-regression/result.json。
- 新8项真实验收通过：跨会话继续、最新进度、无旧授权、偏好载入、更正、删除、用户企业隔离、规则查询。记录在reports/phase3/20261103T135450Z-f2be063d/result.json。
- 恢复演练5项通过，旧代码可读取恢复副本，旧备份继续可恢复。
- 规则变化导致检查结果变化、停用、冲突、版本覆盖拒绝和原子回滚均由数据库测试验证。

```powershell
python -m unittest discover -s tests -v
python scripts/verify_stage3.py
python scripts/verify_ollama.py --model qwen3:8b
python scripts/verify_recovery.py
```

真实模型为qwen3:8b，bge-m3仍未接入。以上结论只代表所列验收样例，不保证任意自然语言表达均可靠。

## 回滚与下一步

保留phase2-v0.2.0和maintenance-v0.2.1，第三阶段使用phase3-v0.3.0。完整回滚第二阶段时，配套将升级前备份恢复到新文件，避免旧维护工具处理新增表。当前维护工具兼容已知新旧两种结构，拒绝未知结构。迁移前备份是数据回滚依据，Git标签本身不包含业务数据。

尚未提供网页界面、自动偏好抽取、完整会话恢复或长对话语义摘要。规则执行器支持amounts、bank、purpose_all、purpose_threshold四类，不能执行任意新增自然语言规则。

下一阶段建议增加便于评委查看的本地可视化入口，再补长对话、故障恢复和更广泛表达验证，最后制作2至3页设计说明及五分钟演示。继续保留每阶段文档、测试批次、提交、标签和升级前备份。
