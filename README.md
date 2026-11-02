# 云账房 AI Coding 比赛

本仓库保存财税 Agent Harness 的实现、阶段说明、测试证据和维护记录。当前程序版本为0.2.1，提供本地业务工具和Ollama自然语言对话。

## 开始使用

```powershell
git clone https://github.com/darkalleys/yunzhangfang_competition.git
cd yunzhangfang_competition/tax-harness
python -m tax_harness init
python -m tax_harness menu
```

Python部分只使用标准库，已在Python 3.13.5验证。AI对话另外需要本机Ollama及模型：

```powershell
ollama pull qwen3:8b
python -m tax_harness chat --user U001 --company C001
```

Windows也可双击项目中的 `start.cmd` 打开业务菜单，或 `chat.cmd` 打开AI对话。数据库在首次初始化时生成，不随Git发布。

## 文档导航

- [完整使用说明](tax-harness/README.md)
- [赛题解读与实施路线](赛题解读与实施路线.md)
- [第一阶段说明（整理恢复版）](tax-harness/docs/stages/phase1-README.md)
- [第一阶段验收报告](tax-harness/reports/第一阶段验收结果.md)
- [第二阶段实现与验证](tax-harness/reports/第二阶段进展与验证说明.md)
- [版本维护与回滚](tax-harness/docs/maintenance.md)
- [维护与恢复验收](tax-harness/reports/维护与恢复验收.md)
- [变更记录](tax-harness/CHANGELOG.md)

第一阶段说明为后续整理恢复的说明文档，没有当时完整代码的历史快照。可回滚代码从补建的第二阶段基线开始。

## 验证与版本

```powershell
cd tax-harness
python -m unittest discover -s tests -v
python scripts/verify_recovery.py
python scripts/verify_ollama.py --model qwen3:8b
```

在仓库根目录开始时才执行上面的 `cd tax-harness`；若已在该目录则直接运行Python命令。模型验收需要运行中的Ollama，其余自动测试可离线执行。

已保留40项自动测试、独立恢复演练及10项正式模型验收的结果。新增维护测试前的第二阶段基线有35项自动测试。

- `phase2-v0.2.0`：第二阶段代码基线。
- `maintenance-v0.2.1`：维护与数据备份恢复工具版本。

业务数据库、备份、日常对话日志、Ollama模型和真实密钥不纳入Git。仓库中的原始材料和选定验收记录使用比赛模拟数据。代码版本与业务数据快照分别管理，恢复操作默认写入新文件。

下一阶段计划是跨会话任务恢复、长期偏好管理和规则导入、更新、停用入口。
