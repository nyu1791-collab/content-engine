# content-engine 引き継ぎ

## 目的と構成

事業4（CSVからのSEO記事）と7（トレンド記事・SNS）を統合した基盤です。入口だけを `collect` / `pseo` に分け、文章生成・ファイル保存・配信先別の履歴を共用します。SEO用とSNS用に同じ処理を複製する必要はありません。

[3リポジトリの構成・合併判断](https://github.com/nyu1791-collab/office-worker/blob/bde57750200924a357414216a13248c7a1720894/docs/BUSINESS_ARCHITECTURE.md)。動画リポジトリは対象外です。

## 今回の修正

- 配信先ごとに `pending/in_progress/succeeded/failed/uncertain` を保存。失敗を成功扱いにしない。
- `retry [post_id] -n 10` で失敗した公開先だけ再試行。成功済みの記事を再作成しない。
- Xの部分投稿IDを保存。結果不明・部分投稿・途中停止は無条件で再送しない。
- fileだけの運用でも記事と `*-tweets.json` を保存し、SNS文面を確認できるようにする。
- WordPressは既定 `draft`。下書きURLをXへ案内しない。再試行でも当初の公開/下書き設定を維持。
- SEO生成済みキーを投稿履歴の表示上限とは別に保持。状態JSONを一時ファイル経由で保存。
- HNに過去24時間と分野キーワードの条件を追加。全ソースが同じ期間条件を使うわけではない。
- 基本導入でvendor/AIブラウザを不要にし、Actionsを軽量化。定期実行の重複とエラー時の状態保存を改善。
- 実体験を装わないpersonaに変更し、仮の紹介リンクは初期設定から除去。

## 見直しで追加した修正

- 元ニュースのIDを生成記録に保存。公開成功後に状態保存で失敗しても、元ニュースを再生成して二重投稿しない。
- SNS生成結果は空でない文字列の配列だけ受理。不正応答は下書き失敗として保持し、外部投稿しない。
- CSVの列数不足・超過は行番号を表示してスキップし、後続の正常行を処理。重複ヘッダーはエラーにする。
- Xの明確な初回400/401/403/429等の拒否は再試行可能。408・通信断・部分投稿は引き続き結果確認待ち。
- Markdownの見出し情報はYAMLとして書き出し、改行・引用符・Windowsパスを保つ。
- 紹介リンクは本文を書き換えず末尾の関連紹介欄へ追加。既存リンクやコードを破壊しない。
- CLIの件数は0以上の整数。`-n 0` / `--limit 0` は設定読み込みや収集・投稿を行わない。

## 再開コマンド

```powershell
.\setup.ps1
.\.venv\Scripts\python -m engine status
.\.venv\Scripts\python -m unittest discover -s tests -v
# GEMINI_API_KEYなどを設定してから、まずファイル下書きで1件
.\.venv\Scripts\python -m engine run -n 1
# CSVの内容と根拠データを確認してから
.\.venv\Scripts\python -m engine pseo data\pseo.csv --limit 1
# 失敗履歴を確認してから再試行
.\.venv\Scripts\python -m engine retry -n 1
```

初期 `publishers: []` は外部投稿を行いません。`output/` のMarkdownとSNS用JSONを確認します。AIブラウザは `setup.ps1 -WithBrowser`、Firecrawlは `-WithFirecrawl` で追加。Linuxは `bash setup.sh` と同名の `--with-*` オプションです。

## 再試行と結果不明

`status` の表示と `data/state.json` の各投稿 `deliveries` を確認します。`retry` は `pending/failed` とSNS下書き生成失敗を対象にします。`uncertain/in_progress` は投稿済みか確認できない状態で、再送すると重複し得るため自動再送しません。

この状態は投稿先の管理画面、Xの保存済みID、ファイルの有無を確認してから解消します。現在は確認専用の管理UIがないため、状態JSONをバックアップし、該当公開先の結果を確認して `succeeded` とURLを記録するか、実際に未投稿と確認できた場合だけ `failed` に戻します。Xの部分投稿がある場合は `failed` に戻すだけで再試行せず、投稿先と残りの文面を照合して手動で補完します。

投稿時の公開設定を履歴に固定しています。後でconfigを `publish` に変えても既存のWordPress下書きは自動公開されません。公開はWordPressで確認して行います。

## 検証範囲と制約

Python 3.12の専用venvに基本依存を導入し、見直し後の回帰テスト46件を確認しました。vendorの導入は不要でした。テストパッケージで実HTTPとソケット接続を遮断し、モック外の通信が試みられた場合はテストを失敗させます。

Windows PowerShell 5.1での基本セットアップと回帰テストをCIへ追加しています。実行結果はPRの `windows-setup` ジョブで確認できます。`setup.ps1` は日本語を正しく読むためUTF-8 BOM付きで保存します。旧形式の投稿履歴には配信先別の失敗情報がないため、過去の失敗を今回の形式へ自動復元することはできません。

出力先が日本語を扱えない場合は、その文字だけをエスケープして処理を続けます。日本語のログをそのまま保存したい場合は、起動前に `PYTHONIOENCODING=utf-8` を設定します。コンソールの既存の文字コードは自動変更しません。

回帰テストは配信失敗・重複防止・X部分投稿・下書きURL・SEO再開・HN絞り込みを外部通信なしで確認します。実際のGemini、WordPress、X、note、Firecrawl、Docker、定刻のActions実行は今回未検証です。Actionsの成功表示だけで外部投稿成功を判断せず、配信履歴を確認してください。

HNは取得した上位候補内で条件を満たす記事を選ぶため、指定件数に届かない場合があります。RSS/GitHub等は各サービスの並び順や期間指定に従います。Xの文字数処理は概算で、投稿先の厳密な検証とは一致しない場合があります。

WordPressのdescriptionはexcerptへ保存します。SEOプラグイン固有のメタディスクリプション設定は未対応です。記事量産だけで検索流入や収益は保証されず、根拠データ、比較対象の実在、価格・住所・日付は人間の確認が必要です。紹介リンクは契約済みURLを設定してから使います。

ローカル実行とActionsで同じ状態を並行更新しないでください。実行前後に状態を同期します。同時の手動pushなどで状態のコミットが失敗した場合は、Actionsの `content-state-<run_id>` artifactから状態と出力を回収し、投稿先の結果と照合して復旧します。まず少数の記事・SNS下書きで `office-worker` の同じ商品への相談導線を整える段階です。

記事の生成自体が3回失敗した元ネタは、既存仕様としてキューから外します。生成記録がないため配信の `retry` 対象ではありません。原因を修正して元ネタを再処理する場合は、状態JSONをバックアップし、該当IDの `seen` を解除して再収集するか、元の項目を `tries: 0` で `queue` へ戻します。失敗元ネタの専用保管・管理画面は未実装です。

## 2026-10-31 追記
- 配信が全部成功した記録は `state.json` から記事本文を外す（本文は `output/` にある）。Actions が毎日コミットする state の肥大化対策。再試行が必要な記録は本文を保持
- `cta`（記事末尾の商品・相談案内）を追加。空なら付かない
- 商品「売上CSV集計」の紹介記事: `python -m engine pseo data/pseo_sales_csv.csv --prompt pseo_sales`。`prompts/pseo_sales.md` は**実証済みの事実だけ**を書くよう限定。生成には GEMINI_API_KEY が必要（未実行）

## 2026-10-31 見直し（2回目）
- 元記事の本文が取れない元ネタ（Google ニュースの転送リンク・PDF等・同意画面/ボット判定ページ）は**記事を書かずに見送る**（`min_source_chars` 既定400字）。見出しだけで本文を作り話で埋めるのを防ぐ。見送りは本数に数えない。Google ニュースの本文取得には Firecrawl が必要
- 記事プロンプト: 元ネタにある事実だけ、**原文の翻訳記事にしない**（要約＋解説、引用は短く出典明記）、根拠の無い比較表・FAQ を作らない、文字数は「目安」に（水増し防止）。X 文面も誇張・本文に無い数字を禁止
- WordPress 送信前に HTML から script/iframe/on*属性/javascript: リンクを除去。既存タグ（term_exists）の ID を拾う

## 2026-10-31 promo を追加
- `python -m engine promo catalog.csv [--publish]`: 作品カタログ → 言語別の告知文。下書きは output/promo に保存、手直し後 --publish で X。投稿済みだけをローテーション対象（7日）、結果不明は再送しない
- LLM は OpenRouter も可（`LLM_PROVIDER=openrouter`）
