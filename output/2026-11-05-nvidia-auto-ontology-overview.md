---
title: NVIDIA Auto Ontologyとは？AIエージェントのDB検索精度を高めるOSS
date: '2026-11-05'
description: NVIDIAが公開したOSS「Auto Ontology」の概要と特徴を解説。企業データの意味や関係性をメタデータから整理し、AIエージェントによる確実なSQL生成やデータ分析を支援する基盤の仕組みや導入手順をまとめました。
tags:
- AI
- NVIDIA
- OSS
- Text-to-SQL
- LLM
---

## NVIDIA Auto Ontologyで何ができるか

AIエージェントが社内データベースを検索して売上などの数値を回答する際、「計算方法が違う」「誤ったテーブルを参照している」といったトラブルが課題になっています。

NVIDIAがオープンソースとして公開している「Auto Ontology」は、企業内のメタデータ（データの属性情報）からデータの意味や関係性を整理し、AIが正しくデータを扱えるようにするセマンティック（意味論的）な推論レイヤーを構築するためのPythonフレームワークです。

公式ドキュメントでは、主に以下の5つのサイクルを実現できると説明されています。

- **Discover（発見）**: メタデータからオントロジー（概念の関係図）を自動生成し、AIが活用しやすいナレッジグラフを構築する。
- **Ground（意味づけ）**: システムごとに異なる指標やエンティティの定義をすり合わせ、エージェントに信頼できるビジネス上の意味を与える。
- **Validate（検証）**: 生成されたクエリ（問い合わせ文）が正規の定義やデータ系統（データがどこから来たか）に沿っているかを検証し、回答時にその根拠（出所）を返す。
- **Expose（連携）**: 構築したコンテキストを、MCP（Model Context Protocol）、CLI、API経由で外部のAIエージェント基盤に提供する。
- **Learn（学習）**: 修正履歴や利用実績をオントロジーにフィードバックし、質問を重ねるごとに共有コンテキストの精度を向上させる。

## 主な特徴とシステム構成

Auto Ontologyは単なるライブラリにとどまらず、UIからバックエンド、推論エンジン連携までを備えたフルスタック構成になっています。

### 1. 自然言語でのデータベース検索（Text-to-SQL）
ユーザーの自然言語による質問をSQLに変換し、接続されたデータベース上で実行します。この処理にはNVIDIAの推論基盤である「NVIDIA NIM」が活用されます。

### 2. 多層的なモデル構成（Model triplets）
処理内容に応じて複数のモデルを切り替えて利用する設計になっています。環境変数で以下の役割ごとにエンドポイントやAPIキー、モデル名を指定できます。

- **REASONING**: チャットや自然言語からSQLへの変換を行うメインモデル（デフォルト例: `nvidia/nemotron-3.5-lightning-30b-a3b`）
- **NON_REASONING**: エンティティ（データの構成要素）抽出を行う軽量モデル
- **EMBED**: テキスト埋め込み（ベクトル化）用モデル（デフォルト例: `nvidia/nemotron-3-embed-1b`）
- **RERANK**: 検索結果を関連度順に並び替えるリランカー（デフォルト例: `nvidia/llama-nemotron-rerank-vl-1b-v2`）

### 3. Web UIと認証・権限制御
Next.js製のWeb UIが付属しており、チャット、データ分析、データカタログの閲覧、設定変更が可能です。また「Better Auth」を用いたロールベースのアクセス制御（RBAC）にも対応しています。

### コンポーネント一覧
公開されているソフトウェア構成は以下の通りです。

| コンポーネント | 利用技術 | 役割 | デフォルトポート |
| --- | --- | --- | --- |
| Frontend | Next.js 16 (React 19, TypeScript, Tailwind CSS 4), Better Auth, Prisma | Web UI、認証、APIゲートウェイ | 3000 |
| Backend | FastAPI (Python 3.12+), LangChain | チャット、NL-to-SQL、カタログAPI | 3001 |
| Ingestion worker | FastAPI (Python 3.12+) | テーブルデータの取り込み、埋め込み生成 | 3002 |
| Postgres + pgvector | リレーショナルデータベース | アプリのメタデータ、カタログ・オントロジー、ベクトルストア | 5432 |
| HashiCorp Vault | オプション | 接続資格情報の保護 | — |

## 使い方・クイックスタート

公式リポジトリでは、Docker ComposeとMicrosoftのサンプル売上データベース「Wide World Importers（WWI）」を用いた検証手順が案内されています。

### 準備するもの
- Docker Compose（v2）
- パッケージマネージャーの「uv」
- NVIDIA APIキー（`build.nvidia.com` で取得可能な `nvapi-...`）

### 起動手順の抜粋

1. リポジトリを複製し、環境変数ファイルを作成します。

```bash
git clone https://github.com/NVIDIA/auto-ontology.git && cd auto-ontology
cp .env.example .env
```

`.env` 内で `DEFAULT_MODELS_API_KEY`（NVIDIA APIキー）、`AUTH_SECRET`、Postgresの各種パスワードを設定します。

2. Postgresを起動し、検証用リポジトリ（auto-ontology-eval）からサンプルデータを投入します。

```bash
docker compose up -d --wait postgres
git clone https://github.com/NVIDIA/auto-ontology-eval.git ../auto-ontology-eval
(cd ../auto-ontology-eval && uv sync && cp .env.example .env && \
  POSTGRES_PASSWORD='<設定したパスワード>' \
  uv run python scripts/seed/seed_wwi.py --database-name wideworldimporters --drop)
```

その後、残りのサービスをビルド・起動することで、ローカルで検証スタックが立ち上がります。

## どんな人に向いているか

- 社内データベースとLLMを接続して自動分析エージェントを構築したい開発者
- Text-to-SQLツールを試したものの、カラム名や業務指標の解釈ズレによる誤回答に悩んでいるチーム
- MCP（Model Context Protocol）などを通じて、自社のエージェント基盤に構造化データのコンテキストを安全に渡したいエンジニア

## 注意点

- **外部からのコントリビューション非対応**: リポジトリのライセンスはApache 2.0ですが、READMEには「This project is currently not accepting external contributions（現在、外部からのコントリビューションは受け付けていません）」と明記されています。プルリクエスト等を送る際は最新の動向に注意が必要です。
- **NVIDIA NIMの利用**: 推論にはホスト型のNVIDIA API catalog、または自前ホストのNVIDIA NIMエンドポイントとAPIキーが必要です。
- **Text-to-SQLのベンチマーク**: BIRDなどのText-to-SQL評価を実行する場合は、別リポジトリである `ontology-sql-eval` を参照する構成になっています。

## まとめ

NVIDIA Auto Ontologyは、LLMが社内データを扱う際の「意味の不一致」や「誤ったSQL生成」を防止するためのコンテキスト管理OSSです。Postgresやpgvector、NVIDIA NIMを活用し、データ定義の統一からクエリ検証、Web UIでの利用までを包括的にサポートしています。業務データとAIエージェントの連携精度に課題を抱えている開発者にとって、注目のプロジェクトといえます。

---
参考: [NVIDIA/auto-ontology](https://github.com/NVIDIA/auto-ontology)

