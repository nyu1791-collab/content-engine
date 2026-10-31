# content-engine — トレンド収集 → 記事/X投稿生成 → 自動公開（プログラマティックSEO）

毎朝 GitHub Actions が勝手に動き、**GitHub Trending / Hacker News / Googleニュース / RSS** から新ネタを拾って
Gemini で日本語解説記事＋Xツリーを作り、**WordPress / X / note下書き / Markdownファイル** に公開。
記事内のキーワードは自動でアフィリエイトリンク化。PCの電源は切っていてOK。

```
collect(sources) → state.json(既出除外・スコア順キュー) → write(Gemini) → affiliate差込 → publish(file / wordpress / x / note)
pseo(CSV×テンプレ) ─────────────────────────────────────┘
```

## 参考にした仕組み
| 元ネタ | 取り込んだ部分 |
|---|---|
| 各種 auto-blogger / AI ブログ自動化リポジトリ | ネタ → LLM記事 → WordPress REST 投稿の流れ |
| プログラマティックSEO 系ツール | データCSV × プロンプトテンプレで記事量産（`pseo`） |
| GitHub Actions cron ボット（自動更新リポジトリ系） | 状態JSONをコミットして永続化＝サーバー不要・無料 |
| n8n の RSS/HTTP ノード | ソースを config で足し引きするだけのプラガブル設計 |

## 最短スタート
```powershell
.\setup.ps1 ; .\.venv\Scripts\Activate.ps1
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
| `note-login` | note 下書き用のログイン保存（`pip install playwright` 必要・ローカル専用） |
| `status` | キュー・投稿履歴 |

## 公開先
| 名前 | 必要なもの |
|---|---|
| file（常時） | なし。`output/*.md`（frontmatter付き → Hugo/Astro/Jekyll で GitHub Pages ブログにも） |
| wordpress | `WP_URL` `WP_USER` `WP_APP_PASSWORD`（`wp_status: draft` で下書き運用も） |
| x | X Developer の4キー（Read and Write）。記事URLつきツリー投稿 |
| note | `note-login` 後、下書き保存（公開は手動） |

## 収益化のコツ
- `affiliates:` に A8.net / もしも / Amazon のリンクを登録 → 関連語が出た記事だけ自動挿入＋PR表記
- ジャンルは絞る（`niche` と `sources` を合わせる）。雑多より「AI自動化ツール専門」のほうが伸びる
- 1日2記事×継続が目安。`pseo` で比較・まとめ系のロングテール記事を一気に積む
