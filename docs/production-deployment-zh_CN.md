# Ubuntu 24.04 生产部署

本项目尚未在公网服务器完成验收；本文是部署与演练手册，不代表已经稳定运行。

1. 在域名 DNS 中创建 `A`/`AAAA` 记录指向服务器，安装 Docker Engine 与 Compose 插件。
2. 克隆仓库，复制 `.env.example` 为 `.env`，设置 `RAG_DOMAIN`，并用 `caddy hash-password --plaintext '强密码'` 生成 `RAG_CADDY_BASIC_AUTH=用户名 哈希`。
3. 设置 `RAG_LLM_PROVIDER=ollama`、`RAG_EMBEDDING_PROVIDER=ollama`，启动：`docker compose -f compose.yaml -f compose.production.yaml up -d --build`。
4. 下载模型：`docker compose -f compose.yaml -f compose.production.yaml exec ollama ollama pull qwen3:4b`，随后下载 `bge-m3`。重排模型需要在 API 镜像中另行安装可选的 `FlagEmbedding` 依赖后启用。
5. 用 `curl -u 用户名:密码 https://域名/` 验证 HTTPS；`docker compose ... ps` 查看健康状态，`docker compose ... logs -f api` 查看日志。生产环境 `/docs` 自动关闭，API 8000 与 Web 8501 不对公网发布。

防火墙只开放 `22`、`80`、`443`。每日执行 `sh scripts/backup.sh /srv/rag-backups`，备份 SQLite 和上传文件/Chroma 归档。恢复时停止服务，解压归档到 `rag-data` 持久卷、恢复 `rag.db`，再启动并通过文档列表与一次问答验证。升级前先备份；失败时使用上一镜像标签重新 `up -d`。
