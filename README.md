# mcp-agent

---

`mcp-agent` は、Model Context Protocol（MCP）を使用したAI エージェントのデモ用コードです。
MCPはFastMCPをベースに実装されており、AIエージェントはLangGraphを用いて構築されています。
LLMにはローカル環境で動作する Qwen3-30B-A3B を Ollama を通じて使用しています。

---

### MCPホスト・クライアントの概要

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
#UTF-8
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

TAVILY_API_KEY=tvly-xxxxxxxx
GITHUB_TOKEN=ghp_xxxxxxxxx

LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=ls__xxxxxxxx

# MySQL
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=app_user
MYSQL_PASSWORD=app_pass_change_me
MYSQL_DATABASE=classicmodels
MYSQL_ROOT_PASSWORD=root_pass_change_me

MYSQL_ROOT_USER=root
APP_USER=app_user
APP_PASSWORD=app_pass_change_me

# Filesystem
DEFAULT_FS_PATH=/app/mcp-demo/src/

#Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:30b-a3b
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

### MCPサーバー群を起動

```bash
cd src
bash run_all.sh
```

---

### 別ターミナルでMCPクライアント実行

```bash
docker exec -it mcp-agent /bin/bash
cd src
python mcp_client.py
```

> クライアントが起動したら、プロンプトに質問を入力することで、エージェントが応答を開始します。

```bash
root@6504cf879b88:/app/mcp-agent/src# python mcp_client.py
[Tools] -> Loaded 33 tools from MCP servers
MCP Agent Session: guest-a426a7da-177f-4ad8-a7b1-6279c783e029
LangSmith Project: mcp-agent-bb17da02-9a0d-4003-8db4-924759c7f103
終了するには 'exit' と入力してください。

質問を入力:
```

---

## ハードウェア構成

NVIDIA A100 40GB または 80GB での動作確認を行っています。

---
