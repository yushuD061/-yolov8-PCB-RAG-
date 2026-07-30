# PostgreSQL Docker 部署

该配置只容器化 PostgreSQL；FastAPI 和 React 仍按当前方式在宿主机运行。后端已有自动建表逻辑，首次连接后会创建 RAG 和长期记忆相关表。

## 1. 准备配置

在项目根目录复制环境变量模板：

```powershell
Copy-Item .env.postgres.example .env.postgres
```

编辑 `.env.postgres`，至少将 `POSTGRES_PASSWORD` 替换为强密码。该文件已加入 `.gitignore`。

## 2. 启动数据库

```powershell
docker compose --env-file .env.postgres -f docker-compose.postgres.yml up -d
docker compose --env-file .env.postgres -f docker-compose.postgres.yml ps
```

数据库只绑定到宿主机 `127.0.0.1`，默认端口为 `5432`；数据保存在 Docker 命名卷 `pcb_postgres_data`。

## 3. 配置后端

在 `backend/agent/.env` 中设置与 `.env.postgres` 一致的连接信息：

```dotenv
PG_ENABLED=true
PG_HOST=127.0.0.1
PG_PORT=5432
PG_USER=pcb_app
PG_PASSWORD=与_POSTGRES_PASSWORD_相同
PG_DBNAME=agent_memory
```

宿主机运行后端时使用 `127.0.0.1`。如果以后将 FastAPI 也加入同一个 Compose 网络，应将 `PG_HOST` 改为服务名 `postgres`，且后端容器内端口始终使用 `5432`。

当前 RAG 使用 PostgreSQL 的条件是 `PG_ENABLED=true`。如需使用 embedding 向量检索，还需按项目现有配置设置 `EMBEDDING_ENABLED=true` 和 `RAG_VECTOR_ENABLED=true`；当前 PostgreSQL embedding 字段是 `JSONB`，没有依赖 pgvector 扩展。

## 4. 验证

查看健康状态：

```powershell
docker inspect --format '{{.State.Health.Status}}' pcb-postgres
```

进入数据库并查看自动创建的表：

```powershell
docker compose --env-file .env.postgres -f docker-compose.postgres.yml exec postgres psql -U pcb_app -d agent_memory -c "\dt"
```
查看表中文档数量
'''powershell
docker compose --env-file .env.postgres `
  -f docker-compose.postgres.yml exec postgres `
  psql -U pcb_app -d agent_memory `
  -c "SELECT COUNT(*) FROM rag_docs; SELECT COUNT(*) FROM rag_chunks;"
'''

启动后端并上传一次 RAG 文档后，预期至少可见：

- `rag_chunks`
- `rag_docs`
- `long_term_memory`

## 5. 日常操作

```powershell
# 查看日志
docker compose --env-file .env.postgres -f docker-compose.postgres.yml logs -f postgres

# 停止服务，保留数据卷
docker compose --env-file .env.postgres -f docker-compose.postgres.yml down

# 再次启动
docker compose --env-file .env.postgres -f docker-compose.postgres.yml up -d
```

删除命名卷会永久删除数据库数据，因此本文不提供自动删卷命令。升级镜像前请先完成数据库备份。

## 6. 备份示例

```powershell
docker compose --env-file .env.postgres -f docker-compose.postgres.yml exec -T postgres pg_dump -U pcb_app -d agent_memory -Fc > agent_memory.dump
```

备份文件可能包含业务数据，不应提交到 Git。

