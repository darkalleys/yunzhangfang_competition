# 版本维护与回滚说明

本文于2026年11月2日建立。目标是让每次改动有来源、可验证，并能在独立目录恢复代码和数据。当前没有修改数据库结构，本阶段不需要数据库迁移。

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

所有提交均在本地，未推送远端；本轮提交作者为Codex，没有修改用户的全局Git身份配置。当前开发分支为 `codex/maintenance-baseline`。

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

如果数据库结构与代码不同，工具会拒绝恢复。未来引入结构变更时，应单独编写版本化迁移、兼容性检查和迁移恢复测试，不允许仅修改表结构后继续沿用旧版程序。当前工具只覆盖本阶段既有结构。

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

Git基线和本机备份提高了可回滚性，但不能追溯此前未保存的原件，也不能抵御整个磁盘损坏。下一步应按需要增加远端代码备份、异地数据备份和持续集成；是否发布到远端由用户另行决定。
