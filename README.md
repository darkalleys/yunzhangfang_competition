# 云账房 AI Coding 比赛

本仓库保存财税 Agent Harness 的实现、阶段说明、测试证据和维护记录。当前程序版本为0.4.0，提供本地业务工具和Ollama自然语言对话。

## 开始使用

```powershell
git clone https://github.com/darkalleys/yunzhangfang_competition.git
cd yunzhangfang_competition/tax-harness
python -m tax_harness init
python -m tax_harness web
```

页面打开地址为 http://127.0.0.1:8765 。Python部分只使用标准库，本轮在Python 3.14.7验证，早期3.13.5记录仍保留。AI对话另外需要本机Ollama及模型：

```powershell
ollama pull qwen3:8b
python -m tax_harness chat --user U001 --company C001
```

Windows可双击web.cmd启动本地网页；也可双击项目中的 `start.cmd` 打开业务菜单，或 `chat.cmd` 打开AI对话。数据库在首次初始化时生成，不随Git发布。

## 文档导航

- [完整使用说明](tax-harness/README.md)
- [赛题解读与实施路线](赛题解读与实施路线.md)
- [第一阶段说明（整理恢复版）](tax-harness/docs/stages/phase1-README.md)
- [第一阶段验收报告](tax-harness/reports/第一阶段验收结果.md)
- [第二阶段实现与验证](tax-harness/reports/第二阶段进展与验证说明.md)
- [第三阶段实现、用法与验收](tax-harness/docs/stages/phase3-README.md)
- [第四阶段本地网页与验证](tax-harness/docs/stages/phase4-README.md)
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

当前60项程序测试通过，新增真实Edge与Ollama页面验收、长对话与故障恢复检查。早期模型验收与恢复证据按阶段保留。新增维护测试前的第二阶段基线有35项自动测试。

- `phase2-v0.2.0`：第二阶段代码基线。
- `maintenance-v0.2.1`：维护与数据备份恢复工具版本。
- `phase3-v0.3.0`：跨会话任务、显式偏好及规则维护。
- `phase4-v0.4.0`：本地网页、长对话及故障验证。

业务数据库、备份、日常对话日志、Ollama模型和真实密钥不纳入Git。仓库中的原始材料和选定验收记录使用比赛模拟数据。代码版本与业务数据快照分别管理，恢复操作默认写入新文件。

旧数据库升级请先在tax-harness目录运行 python -m tax_harness migrate，升级前自动备份。新初始化直接使用第三阶段结构。下一阶段计划为设计说明、演示脚本、更多自然语言与提交后状态验证及最终比赛交付。
