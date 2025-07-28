# mcp-agent

---

`mcp-agent` は、Model Context Protocol（MCP）に準拠した AI エージェント実装フレームワークです。
MCPはFastMCPをベースに実装されており、AIエージェントはLangGraphを用いて構築されています。
LLMにはローカル環境で動作する Qwen3-30B-A3B を Ollama を通じて使用しています。

---

## MCPホスト・クライアントの概要

LangGraphベースのエージェントを「MCPホスト」、MCPサーバー群と接続するためのクライアントを「MCPクライアント」として実装しています。

### MCPホスト（LangGraph エージェント）

* LangGraphのReActエージェントとして構築され、LLMとMCPツールを組み合わせて実行します。
* LLMにはローカル Ollama モデル（Qwen3-30B-A3B）を利用。
* LangSmith によるトレース機能にも対応。

### MCPクライアント（`MultiServerMCPClient`）

* 各 MCP サーバー（search, rag, db, fs）と非同期に接続し、使用可能なツールを自動取得。
* `mcp_client.py` の中で、LLM・ツール・エージェントの初期化からユーザー対話ループまでを一貫して処理。

---

### MCPサーバー

* `search_mcp_server.py`：Web検索・GitHub検索・論文検索などの外部APIベースの検索ツール
* `db_mcp_server.py`：MySQLの操作ツール
* `fs_mcp_server.py`：ローカルのファイルシステム操作用のツール
* `rag_mcp_server.py`：RAG検索ツール

---

## ディレクトリ構成

```
.
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── src/
    ├── db_mcp_server.py
    ├── fs_mcp_server.py
    ├── rag_mcp_server.py
    ├── search_mcp_server.py
    ├── mcp_client.py
    ├── llm_utils.py
    ├── logger_utils.py
    └── run_all.sh
```

---

## クイックスタート

### リポジトリクローン & `.env` 設定

```bash
git clone https://github.com/shanigoro48256/mcp-agent.git
cd mcp-agent
```

`.env` に以下を設定：

```dotenv
TAVILY_API_KEY=tvly-xxxxxxxx
GITHUB_TOKEN=ghp_xxxxxxxxx

LANGSMITH_TRACING=true
LANGSMITH_API_KEY=ls__xxxxxxxx

MYSQL_ROOT_PASSWORD=root_pass
APP_USER=app_user
APP_PASSWORD=app_pass

OLLAMA_MODEL=qwen3:30b
OLLAMA_BASE_URL=http://localhost:11434
```

---

### Docker 起動と初期セットアップ

```bash
docker compose up -d
docker exec -it mcp-agent /bin/bash
pip install -e .
```

> Ollama が起動したら、以下を実行して Qwen モデルを取得してください（VRAM 約24GB 必要）：

```bash
ollama pull qwen3:30b-a3b
```

---

### MCP サーバー群を起動

```bash
cd src
bash run_all.sh
```

---

### 別ターミナルでクライアント実行

```bash
docker exec -it mcp-agent /bin/bash
cd src
python mcp_client.py
```

---

## ハードウェア構成

NVIDIA A100 40GB または 80GB での動作確認を行っています。

---
