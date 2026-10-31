# content-engine — トレンド収集 → 記事/X投稿生成 → 自動公開（プログラマティックSEO）

毎朝 GitHub Actions が勝手に動き、**GitHub Trending / Hacker News / Googleニュース / RSS** から新ネタを拾って
Gemini で日本語解説記事＋Xツリーを作り、**WordPress / X / note下書き / Markdownファイル** に公開。
記事内のキーワードは自動でアフィリエイトリンク化。PCの電源は切っていてOK。

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
.\setup.ps1 ; .\.venv\Scripts\Activate.ps1
.\scripts\firecrawl.ps1 up   # （任意・要Docker）→ .env に FIRECRAWL_API_URL=http://localhost:3002
notepad .env          # GEMINI_API_KEY
notepad config.yaml   # ジャンル・ペルソナ・ソース・アフィリエイト
python -m engine run -n 1     # output/ に記事ができる
```

## 完全自動化（GitHub Actions・無料）
1. このリポジトリの Settings → Secrets and variables → Actions に `GEMINI_API_KEY`（WordPress/X を使うならそのキーも）
2. `config.yaml` の `publishers:` を `[wordpress, x]` などに
3. 以後毎日 07:17 JST に自動実行（Actions タブの「Run workflow」で手動実行も可）

## コマンド
| コマンド | 内容 |
|---|---|
| `collect` | ネタ収集 → キュー |
| `write -n 2` | キュー上位を記事化して公開 |
| `run -n 2` | collect + write |
| `pseo data/pseo.csv --limit 10` | CSV 1行 = 1記事 で量産（列は自由。例: 地域×サービス、ツール×用途） |
| `login note` / `login x` | ブラウザ投稿用のログインを保存（一度だけ。`data/browser_profile`） |
| `status` | キュー・投稿履歴 |

## 公開先
| 名前 | 必要なもの |
|---|---|
| file（常時） | なし。`output/*.md`（frontmatter付き → Hugo/Astro/Jekyll で GitHub Pages ブログにも） |
| wordpress | `WP_URL` `WP_USER` `WP_APP_PASSWORD`（`wp_status: draft` で下書き運用も） |
| x | X Developer の4キー（Read and Write）。記事URLつきツリー投稿 |
| x_browser | `login x` だけ。browser-use が画面からスレッド投稿（API 不要・ローカル実行） |
| note | `login note` だけ。browser-use が下書き保存（`note_publish: true` で公開まで） |

※ note / x_browser はログイン済みブラウザが要るので、PC 上の定期実行（タスクスケジューラで `python -m engine run`）で回す。GitHub Actions は file / wordpress / x 向け。

## 収益化のコツ
- `affiliates:` に A8.net / もしも / Amazon のリンクを登録 → 関連語が出た記事だけ自動挿入＋PR表記
- ジャンルは絞る（`niche` と `sources` を合わせる）。雑多より「AI自動化ツール専門」のほうが伸びる
- 1日2記事×継続が目安。`pseo` で比較・まとめ系のロングテール記事を一気に積む
