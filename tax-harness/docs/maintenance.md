# 版本维护与回滚说明

本文于2026年11月2日建立，11月4日更新。目标是让每次改动有来源、可验证，并能在独立目录恢复代码和数据。第三阶段新增记忆与规则审计表，旧库须执行 `python -m tax_harness migrate`，升级前自动备份。详见第三阶段说明。

## 从哪里看每一步

| 文件 | 用途 |
| --- | --- |
| README.md | 当前版本的使用入口，后续可以更新 |
| docs/stages/phase1-README.md | 第一阶段使用说明的整理恢复版，说明导入、查询、校验、保存和测试步骤 |
| reports/第一阶段验收结果.md | 第一阶段当时保留的验收报告 |
| reports/第二阶段进展与验证说明.md | 第二阶段实现、验证和下一步目标 |
| CHANGELOG.md | 按版本追加的变更记录 |
| docs/maintenance.md | 版本管理、数据备份和恢复操作 |

第一阶段原README后来随第二阶段更新，未单独存档。此前Git没有任何提交。因此整理恢复版不能等同于历史原件，也没有可以精确恢复第一阶段全部代码的标签。今后每个阶段必须同时保留阶段说明、验收记录和Git标签。

## 代码版本

Git仓库根目录是项目目录的上一层：

```powershell
cd "C:\Users\wsco\Documents\ChatGPT\云账房比赛"
git log --oneline --decorate
git tag
git status --short
```

- `phase2-v0.2.0`：补建的第二阶段文件基线。
- `maintenance-v0.2.1`：本次维护与备份恢复工具版本。
- `phase3-v0.3.0`：跨会话任务、偏好与规则维护，包含备份后增量迁移。
- `phase4-v0.4.0`：本地网页和故障验证，未改变数据库结构。

最初的维护基线在本地建立；用户随后指定GitHub仓库 `https://github.com/darkalleys/yunzhangfang_competition.git` 用于同步代码和阶段标签。具体同步状态以 `git remote -v`、`git log --all --decorate` 及远端分支校验为准。基线提交作者为Codex，没有修改用户的全局Git身份配置。后续开发使用codex/开头的功能分支，当前分支以git status为准。

后续每个改动应从已提交状态创建 `codex/功能名称` 分支，先实现、再执行相关测试、记录结果、审查差异、提交，验收通过后才打新的阶段标签。已有阶段标签不移动，阶段文档和证据不原地替换；新运行的报告使用新的批次目录。未通过的验证也保留，并在说明中标注适用版本。

提交时只选择本次任务的文件，避免把其他未完成工作一起加入。发布前检查 `git diff --cached` 和 `git status`。数据库、私有运行日志、备份、模型文件和Office临时锁文件不进入代码提交。初始化永远不能作为回滚操作，因为它不代表恢复历史数据。

## 数据备份

以下命令在tax-harness目录执行：

```powershell
python scripts/backup.py create
```

程序会创建 `backups/时间戳-随机编号/`，包含：

- `database.sqlite3`：SQLite备份API生成的一致性快照，含业务数据和审计记录。
- `manifest.json`：SHA256、结构指纹、材料版本、程序版本、Git提交号及是否有未提交项目改动。

不能只复制正在使用的数据库主文件，因为已提交内容可能还在WAL日志中。备份操作会执行完整性、外键和结构检查。备份包含当前业务数据，应另外复制到独立磁盘或可靠存储；当前实现只有本机备份，不是异地容灾。

Git提交号只说明备份时的代码状态。若 `working_tree_dirty` 为true，该备份对应的代码还有未提交改动，不能把提交号当成全部代码的唯一标识。正式阶段备份应在代码提交后、工作区干净时生成。

## 恢复数据到新文件

```powershell
python scripts/backup.py restore --snapshot "backups/实际备份目录" --to "data/recovered.sqlite3"
python -m tax_harness --db data/recovered.sqlite3 totals --user U001 --company C001 --month 2026-09
python -m tax_harness --db data/recovered.sqlite3 menu
```

恢复会校验备份SHA256、数据库完整性、外键、材料版本和当前代码的结构兼容性。目标文件存在时拒绝覆盖，没有强制覆盖选项。先在新文件核对，再用全局 `--db` 参数选择它。默认业务库保留原样。

当前恢复工具明确兼容第二、第三阶段两种已知结构，拒绝未知结构。旧备份恢复后要使用新聊天功能，须先迁移；完整回滚旧版代码时应配套恢复升级前备份到新文件。未来结构变更继续要求明确迁移与恢复测试。

## 恢复旧代码到独立目录

在仓库根目录执行，目标目录应选择尚不存在的位置：

```powershell
git archive --format=zip --output=tax-harness/backups/code-phase2-v0.2.0.zip phase2-v0.2.0
Expand-Archive -LiteralPath tax-harness/backups/code-phase2-v0.2.0.zip -DestinationPath rollbacks/phase2-v0.2.0
cd rollbacks/phase2-v0.2.0/tax-harness
python -m unittest discover -s tests -v
```

运行前先使用一次备份命令，确保 `tax-harness/backups/` 已创建。Git代码归档不包含当前数据库、私有日志或Ollama模型。旧代码的35项自动测试可以离线执行，模型验收仍需Ollama和相应模型。

需要配套业务数据时，从当前维护版本调用恢复工具，将所选数据快照恢复到旧代码目录中的新文件，再用旧代码的 `--db` 指向该文件。先核对结构兼容性、金额、缺项、权限和审计，再考虑切换日常入口。这个过程不覆盖当前代码，不要求丢弃当前未提交改动。

## 恢复验证

```powershell
python -m unittest discover -s tests -v
python scripts/verify_recovery.py
```

新增测试覆盖保存与审计恢复、拒绝覆盖、损坏检测、结构不兼容及WAL中的已提交内容。恢复演练脚本从真实Git标签导出旧代码，在隔离目录运行旧测试，再恢复当前数据库快照并用旧CLI核对发票与金额。脚本不会替换当前业务库或工作区，结果保存在 `reports/recovery-verification.json`。

代码已按用户授权同步指定GitHub仓库；业务库仍只有本机备份，不会随Git上传。Git基线与本机备份不能追溯未保存的原件，也不能抵御整个磁盘损坏，后续可按需增加异地数据备份及持续集成。
