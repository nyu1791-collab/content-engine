# content-engine — トレンド収集 → 記事/X投稿生成 → 自動公開（プログラマティックSEO）

GitHub Actionsの定期実行で、**GitHub Trending / Hacker News / Googleニュース / RSS** から新ネタを拾って
Gemini で日本語解説記事＋Xツリーを作り、**WordPress / X / note下書き / Markdownファイル** に公開。
初期設定は記事とSNS文面のファイル下書きです。外部への公開は配信先の設定と認証後に行います。契約済みの紹介URLを登録すると、関連語のある記事へ末尾の紹介欄を追加できます。本文や既存リンクは変更しません。

[現在地・再開手順・失敗時の扱い](docs/HANDOFF.md) を先に確認してください。事業4と7はすでに本リポジトリに統合済みです。営業と顧客ファイル処理は別リポジトリで継続します。

```
collect(GitHub/HN/News/RSS/Firecrawl検索) → state.json(既出除外・スコア順キュー) → write(Gemini) → affiliate差込 → publish(file / wordpress / x / note・x_browser[browser-use])
pseo(CSV×テンプレ) ─────────────────────────────────────┘
```

## 取り込んだリポジトリ
| 元リポジトリ | 取り込み方 | このエンジンでの役割 |
|---|---|---|
| [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl)（本体 AGPL / SDK MIT） | `vendor/firecrawl`（submodule）。本体は Docker 起動、SDK は editable install | 元記事の本文抽出（JS描画サイトも Markdown 化）・`firecrawl_search` ソース（過去24時間の検索結果をネタに） |
| [browser-use/browser-use](https://github.com/browser-use/browser-use)（MIT） | `vendor/browser-use`（submodule）を editable install | `note`（下書き/公開）と `x_browser`（スレッド投稿）を **API 無しで画面操作**。長文は CDP で一括挿入するカスタムアクション付き |
| GitHub Actions cron ボット / auto-blogger / pSEO 系 | 設計を採用 | 状態JSONコミットで無料常時運用・CSV×テンプレ量産 |

## 最短スタート
```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
notepad .env          # GEMINI_API_KEY
notepad config.yaml   # ジャンル・ペルソナ・ソース・アフィリエイト
python -m engine run -n 1     # output/ に記事ができる
```

基本導入ではvendorの取得やAIブラウザ導入は不要です。必要な時だけ `./setup.ps1 -WithBrowser` / `./setup.ps1 -WithFirecrawl` で追加します。Linuxは `bash setup.sh` と `--with-browser` / `--with-firecrawl` です。

Firecrawlをローカル起動する場合は `-WithFirecrawl` でSDKを追加してから `./scripts/firecrawl.ps1 up`（要Docker）を実行し、`.env` の `FIRECRAWL_API_URL=http://localhost:3002` を設定します。既存のFirecrawl設定を引き継ぐ場合もSDKの追加が必要です。

## 定期実行（GitHub Actions）
1. このリポジトリの Settings → Secrets and variables → Actions に `GEMINI_API_KEY`（WordPress/X を使うならそのキーも）
2. `config.yaml` の `publishers:` を `[wordpress, x]` などに
3. 以後毎日 07:17 JST に自動実行（Actions タブの「Run workflow」で手動実行も可）

指定時刻は実行予定で、サービス側の遅延があり得ます。ActionsやAPIの利用枠・料金は契約に従います。WordPressは既定で下書きです。実行後は `status` と配信先別の結果を確認してください。

## コマンド
| コマンド | 内容 |
|---|---|
| `collect` | ネタ収集 → キュー |
| `write -n 2` | キュー上位を記事化して公開 |
| `run -n 2` | collect + write |
| `pseo data/pseo.csv --limit 10` | CSV 1行 = 1記事 で量産（列は自由。例: 地域×サービス、ツール×用途） |
| `login note` / `login x` | ブラウザ投稿用のログインを保存（一度だけ。`data/browser_profile`） |
| `status` | キュー・投稿履歴 |
| `retry [post_id] -n 10` | 失敗した公開先のみ再試行。成功済み・結果不明・X部分投稿は自動再送しない |

## 公開先
| 名前 | 必要なもの |
|---|---|
| file（常時） | なし。`output/*.md`（frontmatter付き → Hugo/Astro/Jekyll で GitHub Pages ブログにも） |
| wordpress | `WP_URL` `WP_USER` `WP_APP_PASSWORD`（`wp_status: draft` で下書き運用も） |
| x | X Developer の4キー（Read and Write）。記事URLつきツリー投稿 |
| x_browser | `-WithBrowser`、Geminiキー、`login x`。browser-use が画面からスレッド投稿（ローカル実行） |
| note | `-WithBrowser`、Geminiキー、`login note`。browser-use が下書き保存（`note_publish: true` で公開まで） |

※ note / x_browser はログイン済みブラウザが要るので、PC 上の定期実行（タスクスケジューラで `python -m engine run`）で回す。GitHub Actions は file / wordpress / x 向け。

file運用でも `output/<post_id>-tweets.json` にSNS文面を保存します。`data/state.json` には公開先別の成功・失敗・結果不明を記録します。投稿後に応答を受け取れなかった場合やXの部分投稿は、投稿先を確認してから対処してください。旧形式の履歴から過去の失敗先を復元する機能はありません。

HNは `max_age_hours: 24` と `keywords` で期間・分野を絞れます。RSSなど他のソースは同じ条件ではありません。記事の比較対象・価格・所在地は根拠を確認してから公開します。WordPressのdescriptionはexcerptへ保存し、SEOプラグイン固有の設定は行いません。

## 収益化のコツ
- `affiliates:` に契約済みの紹介URLを登録 → 関連語が本文にある記事だけ末尾紹介欄＋PR表記を追加（リンク・コード内の語句は対象外）
- ジャンルは絞る（`niche` と `sources` を合わせる）。雑多より「AI自動化ツール専門」のほうが伸びる
- 1日2記事×継続が目安。`pseo` で比較・まとめ系のロングテール記事を一気に積む

## 販売作品・サービスの告知（promo）
翻訳した同人作品の海外向け告知や、自社商品（office-worker の商品）の紹介を、カタログから言語ごとに作る。
```powershell
python -m engine promo data\catalog.csv                # output/promo/日付/ に下書き（手で直してよい）
python -m engine promo data\catalog.csv --publish      # 確認した下書きを X へ。同じ作品は7日に1回まで（--every-days）
```
- カタログ列: `title,url,langs,blurb,tags,adult`（例: `data/catalog_example.csv`）。`adult=1` は `[18+]` を付け、文面は非露骨に
- 成人向けを投稿するアカウントは X の「センシティブな内容」設定を必ず有効に
