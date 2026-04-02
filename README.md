# スペースマーケット ゲストレビュー自動投稿

利用完了したゲストに対して、毎日23:00 (JST) に自動でレビューを投稿するツール。

- 星: ★★★★★（5つ星）
- メッセージ: 「ご利用いただきまして、ありがとうございました！」

## GitHub Actions で自動実行

### 1. GitHub Secrets を設定

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** から、以下の2つを登録してください。

| Secret 名 | 値 |
|---|---|
| `SPACEMARKET_EMAIL` | スペースマーケットのログインメールアドレス |
| `SPACEMARKET_PASSWORD` | スペースマーケットのログインパスワード |

### 2. ドライランモードの切り替え

デフォルトは**ドライラン（実際に投稿しない）**です。

本番モードに切り替えるには、リポジトリの **Settings → Secrets and variables → Actions → Variables** タブで：

| Variable 名 | 値 |
|---|---|
| `DRY_RUN` | `false` |

を設定してください。

### 3. 実行方法

- **自動実行**: 毎日 23:00 JST に自動実行されます
- **手動実行**: Actions タブ → 「SpaceMarket ゲストレビュー自動投稿」→ 「Run workflow」ボタンで即時実行可能（ドライラン選択可）

### 4. 実行結果の確認

実行後、Actions の各 run の **Artifacts** にスクリーンショットが保存されます（7日間保持）。
