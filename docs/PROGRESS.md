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

- T-0.1 Checkpoint A：代码与离线测试完成；全量 47 passed, 1 skipped；ruff check 与 format --check 全绿
- T-0.1 Checkpoint B：模型在线 smoke PASS（DeepSeek chat 11 in / 1 out / 12 total；BGE-M3 1024；SiliconFlow rerank PASS）；API health ok
- 三文档：v1(15p/56 chunks)、v7(15p/62)、N19-1423(16p/99) 上传 201；batch-rebuild 200；index_version=openai-BAAI-bge-m3-1024
- 三条引用问答：Q1 28.4 BLEU（4 citations，页 1/8/7 + v7 页 1）；Q2 8×P100 / 3.5 天（4 citations）；Q3 BERT-base 参数量拒答（4 citations，未命中 110M）→ 检索/切块缺口，转 T-1.2/T-1.3
- MinerU smoke：4.1.7；扫描版 1706.03762v1_img.pdf 第 1 页，standard + OCR；总耗时 566.3 秒（含首次模型下载），进程树峰值工作集 1,354.4 MiB，exit 0；生成 2,974 字节 Markdown，已核对包含论文标题和摘要
- NO_PROXY 坑：系统 NO_PROXY 含 [::1]，httpx 0.28 报 InvalidURL；`.env.live` 不会覆盖父进程；本次用 Python 进程内覆盖完成验收，系统侧待清理
- T-0.1 状态：条件通过（模型栈 + 3 篇可检索 + 每条 4 引用；Q1/Q2 正确，Q3 检索缺口转 T-1.2/T-1.3；541 页推 T-1.1；token 仅 smoke 计量）
- 实际耗时：待补 / 预算 4.5h
- 下一步：T-1.1 解析 + 异步上传（64MB/800 页 + OCR + block/bbox）

