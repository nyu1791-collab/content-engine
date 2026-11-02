# アフィリエイト計画（決めたことと守る規則）

2026-11-02に利用者と決めた内容。承認の仕組みは `engine/approval.py`、公開の判定は `python -m engine approve`（`engine/__main__.py`）。商品記事は既存の `pseo`（CSV1行＝記事1本）で作る。

## 1. 対象

| 区分 | 対象 | 作り方 | 設定と状態 |
|---|---|---|---|
| 無限アフィ（確認つき） | Amazon・楽天・Yahoo!ショッピングの商品紹介 | `affiliate_products.csv` の1行を1記事にし、1本ずつ Discord で承認してから公開 | `config.affiliate.yaml`。口座の申込みは利用者 |
| 高単価アフィ | 料金・条件が公式に書かれたA8.netの案件 | 同じ仕組みで、公式の情報だけを CSV に書いて紹介する。広告表記を入れる | 規則を決めた。案件の申込みは利用者 |
| アダルト系 | 成人向け商品の紹介（例: FANZA アフィリエイト） | 別サイト（18歳以上の確認つき）と別のWordPressを用意してから公開する | `config.adult.yaml`。公開は無効（`publishers` が空）。別サイトは未着手 |

「無限」は記事を増やす意味です。承認なしの大量公開はしません。1回に書く本数は `--limit`（今は2本）で決めます。

## 2. 全区分で守る規則

- 公開は、Discord で「承認 記録ID」と返信された記事だけ。
- 体験談、効果、収益額、「必ず稼げる」は書かない。使っていない商品を使ったようには書かない。
- 価格・送料・在庫・条件は、CSVに書いた値だけを使う。値の確認日（`checked_date`）が空なら価格は書かれず、販売ページで確認するよう書かれる。
- 記事の1段落目に「本記事はアフィリエイト広告を含みます」と書く（成人向けは「成人向けのアフィリエイト広告」）。
- 投資、仮想通貨、副業、金融商品、健康・美容効果の断定は対象外。
- 成人向けは、サイトのトップで18歳以上の確認を出す。性的な描写は文章にもAI画像にも作らない。本人の同意がない画像、未成年に見える素材は使わない。ASPが配布する素材だけを使う。
- WordPress の記事は下書きのまま（`wp_status: draft`）。管理画面で読み直してから公開する。
- 紹介URLは、ASPの管理画面で作った自分のURLだけを `affiliate_url` 列に貼る。AIにURLを作らせない。

## 3. 利用者がする手順

### 3-1. Discord（承認の受け取り）

1. ブラウザで https://discord.com/developers/applications を開き、右上の「New Application」を押す。名前は「記事承認」など何でよい。
2. 左メニューの「Bot」を開き、「Reset Token」を押して表示された文字列をコピーする。一度しか表示されないので、すぐ次へ進む。
3. 同じ「Bot」の画面を下へ送り、「Privileged Gateway Intents」の「MESSAGE CONTENT INTENT」をONにして「Save Changes」を押す。これをONにしないと、返信の文字を読めない。
4. 左メニューの「OAuth2」→「URL Generator」を開く。「SCOPES」の「bot」にチェックを入れる。下の「BOT PERMISSIONS」で「View Channels」「Send Messages」「Read Message History」にチェックを入れる。一番下に出たURLをコピーしてブラウザで開き、自分のDiscordサーバーを選んで追加する。
5. Discordアプリで、左下の歯車（ユーザー設定）→「詳細設定」→「開発者モード」をONにする。
6. 承認に使うチャンネル（例: #承認）を右クリック→「チャンネルIDをコピー」。
7. 自分の名前を右クリック→「ユーザーIDをコピー」。
8. メモ帳で `C:\Users\nyu17\yu-lab\repos\content-engine\.env` を開き、次の3行に値を入れて保存する。**値はチャットに貼らない。**

```
DISCORD_BOT_TOKEN=（手順2でコピーした文字列）
DISCORD_APPROVAL_CHANNEL_ID=（手順6のID）
DISCORD_APPROVER_ID=（手順7のID）
```

### 3-2. アフィリエイトの申込み（利用者本人が行う）

- Amazon アソシエイト: https://affiliate.amazon.co.jp/ （審査あり）
- 楽天アフィリエイト: https://affiliate.rakuten.co.jp/
- Yahoo!ショッピング: 参加の窓口と条件は公式の最新案内で確認する。
- A8.net: https://www.a8.net/ （案件ごとに申込み）
- 成人向け: FANZA アフィリエイトなど。年齢確認を入れたサイトができてから申込む。

### 3-3. 商品データを作る

1. `C:\Users\nyu17\yu-lab\repos\content-engine\data\affiliate_products.example.csv` をコピーし、名前を `affiliate_products.csv` に変える（同じフォルダ。成人向けは `adult_products.csv`）。
2. Excelで開き、1行に1商品を書く。保存するときは「CSV UTF-8（コンマ区切り）」を選ぶ（普通のCSVはShift_JISになり、読めません）。列の意味は次のとおり。

| 列 | 書くもの |
|---|---|
| product_name | 商品名 |
| shop | Amazon / 楽天 / Yahoo! など |
| price_yen | 販売ページの税込価格（数字だけ） |
| checked_date | 価格を確認した日（例: 2026-11-02）。空だと価格は記事に書かれない |
| official_url | 販売ページのURL（ASPの紹介URLではない） |
| affiliate_url | ASPの管理画面で作った自分の紹介URL |
| features | 公式ページに書いてある特徴を `;` で区切って書く |
| notes | 送料・保証・返品など、公式ページに書いてあること |

## 4. 動かし方

記事を作る。承認待ちの記事が作られる（まだ公開されない）。`--limit` で本数を決める。

```bash
cd /c/Users/nyu17/yu-lab/repos/content-engine && CONFIG=config.affiliate.yaml STATE_PATH=data/affiliate_state.json .venv/Scripts/python.exe -m engine pseo data/affiliate_products.csv --prompt affiliate_product --limit 2
```

承認依頼をDiscordへ送る。承認された記事だけ公開される。

```bash
cd /c/Users/nyu17/yu-lab/repos/content-engine && CONFIG=config.affiliate.yaml STATE_PATH=data/affiliate_state.json .venv/Scripts/python.exe -m engine approve
```

1. `pseo` で記事を作る。
2. `approve` を実行すると、Discordに承認依頼が届く。
3. Discordで「承認 記録ID」と返信する（却下は「却下 記録ID」）。
4. もう一度 `approve` を実行すると、承認された記事だけが公開される。

`CONFIG` と `STATE_PATH` は、作るときと承認するときで同じものを使う。別々にすると、保存先や記録が混ざる。

今の `config.affiliate.yaml` の `publishers` は空なので、承認後は `output/affiliate/` にファイルを保存するだけです。WordPressに下書きを送るには、WordPressの設定（`.env` の `WP_URL` など）を入れてから、`publishers: [wordpress]` にする。

成人向けは `CONFIG=config.adult.yaml STATE_PATH=data/adult_state.json` を付け、`--prompt affiliate_adult` と `adult_products.csv` を使う。別サイトを用意するまで、公開先は空のままにしてください。

## 5. まだ作っていないもの

- 成人向けの別サイト、18歳以上の確認画面、別のWordPressの設定。
- 商品の価格を自動で取る処理。Amazonの商品情報APIは、一定の売上実績のあとに使える。今は CSV に人が書く。
- 高単価案件の選定。案件ごとに上の規則へ照らして決める。
- GitHub Actions での承認の運用。GitHubへの反映は利用者の指示があってから。
- 実際のDiscord承認の動作確認。ボットのトークンを入れたあとに、利用者と一緒に1回行う。
