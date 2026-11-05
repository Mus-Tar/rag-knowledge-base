# PROGRESS

## 2026-11-05
- T-0.2 契约冻结：完成（contracts.py + 两个测试 + ADR）
- 验收：目标测试 15 passed；全量 32 passed, 1 skipped（e2e 无栈）；ruff/format 全绿
- 实际耗时：0.5 h / 预算 3.75h
- 遗留：span_map 负例测试；frozen list 只读约定；541 页 <2MB；30 样本 confidence 校准；四路径 HTTP/DB 集成（T-2.1）
- 下一步：T-0.5 官方资产 → T-0.1 真模型栈（需要 .env 密钥）

- T-0.5 官方资产：完成（check_official.py + accept_official.py + manifest + README + .gitignore）
- 验收：4/4 官方文件页数/哈希 ok；accept_official --check-assets exit 0；ruff 64 files 全绿
- 资产：official_pdf/pdf 共 39 篇 PDF / 125.7MB（4 个官方用例 + 35 篇语料）；541 页书 22.3MB
- 实际耗时：0.3 h / 预算 1.5h
- 遗留：541 页书 22.3MB > 当前 20MB 上传上限（T-1.1 改 64MB）；E2E 待 T-1.1/T-2.1
- 红队修复：check_official 增语料≥35 + manifest 一致性 + 损坏 PDF 干净报错；accept_official 同步
- 红队验收：4/4 + corpus 35 + manifest ok；accept exit 0；全量 32 passed 1 skipped；ruff 64 files
- 下一步：T-0.1 真模型栈（DeepSeek + BGE-M3 1024 + MinerU smoke）

