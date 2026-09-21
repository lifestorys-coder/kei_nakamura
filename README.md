# 沖縄観光新聞

沖縄の天気・観光スポット・最新ニュースをまとめた「新聞」を毎日自動生成し、GitHub Pages で公開する仕組みです。

## 仕組み

- `scripts/generate_newspaper.py` が以下を取得・生成します。
  - **天気**: [Open-Meteo](https://open-meteo.com/) の無料APIから那覇市の3日間予報を取得
  - **ニュース**: Yahoo!ニュース 沖縄地域面のRSS（`https://news.yahoo.co.jp/rss/area/47.xml`）から最新ニュースを取得
  - **観光スポット**: `data/spots.json` に登録した沖縄の観光地から、日付に応じて3件をピックアップ
- 生成結果は以下に書き出されます。
  - `docs/index.html` … 最新号
  - `docs/archive/YYYY-MM-DD.html` … 過去号（自動でアーカイブされます）
  - `docs/archive/index.html` … バックナンバー一覧
- `.github/workflows/daily-newspaper.yml` が毎日 06:00 JST（21:00 UTC）に上記スクリプトを実行し、変更があれば自動でコミット・プッシュします。手動実行（`workflow_dispatch`）も可能です。

## セットアップ（初回のみ）

このリポジトリを GitHub Pages で公開するには、リポジトリ設定で1回だけ以下を行ってください（Actions からは変更できない設定のため）。

1. GitHub リポジトリの **Settings → Pages** を開く
2. **Source** を `Deploy from a branch` に設定
3. **Branch** を `main` / フォルダを `/docs` に設定して保存

設定後、`https://<ユーザー名>.github.io/<リポジトリ名>/` で沖縄観光新聞が閲覧できるようになります。

## ローカルでの動作確認

```bash
python3 scripts/generate_newspaper.py
```

`docs/index.html` と `docs/archive/` 以下が更新されます。ネットワークに接続できない環境では、天気・ニュースの取得に失敗しても処理は継続し、その旨を紙面上に表示します（観光スポットは常に表示されます）。

## 観光スポットの追加・編集

`data/spots.json` に `name` / `area` / `category` / `description` を持つオブジェクトを追加するだけで反映されます。
