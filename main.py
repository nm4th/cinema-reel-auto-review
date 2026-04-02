"""スペースマーケット ゲストレビュー自動投稿 - メインエントリーポイント

使い方:
  python main.py              # 即時実行（ドライラン）
  python main.py --schedule   # 毎日23:00に自動実行（ドライラン）
  python main.py --no-dry-run # 即時実行（本番モード）※許可後のみ使用
"""

import argparse
import logging
import os
import time

import schedule

import config
from spacemarket_reviewer import SpaceMarketReviewer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def run_review_job(dry_run: bool = True):
    """レビュー投稿ジョブを実行する"""
    # screenshotsディレクトリを作成
    os.makedirs("screenshots", exist_ok=True)

    reviewer = SpaceMarketReviewer(dry_run=dry_run)
    reviewer.run()


def main():
    parser = argparse.ArgumentParser(description="スペースマーケット ゲストレビュー自動投稿ツール")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help=f"毎日{config.SCHEDULE_TIME}に自動実行するスケジューラモード",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="本番モード（実際にレビューを投稿する）※許可後のみ使用",
    )
    args = parser.parse_args()

    # ドライランの判定: コマンドライン引数 > 環境変数
    dry_run = config.DRY_RUN
    if args.no_dry_run:
        dry_run = False

    if dry_run:
        logger.info("🔒 ドライランモード: 実際にはレビューを投稿しません")
    else:
        logger.warning("⚠️  本番モード: 実際にレビューを投稿します！")

    if not config.SPACEMARKET_EMAIL or not config.SPACEMARKET_PASSWORD:
        logger.error("ログイン情報が設定されていません。.envファイルを確認してください。")
        logger.error("  cp .env.example .env  でテンプレートをコピーし、値を設定してください。")
        return

    if args.schedule:
        logger.info(f"スケジューラモード: 毎日 {config.SCHEDULE_TIME} に実行します")
        schedule.every().day.at(config.SCHEDULE_TIME).do(run_review_job, dry_run=dry_run)

        # 初回はすぐに実行
        logger.info("初回実行を開始します...")
        run_review_job(dry_run=dry_run)

        # スケジューラループ
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        # 即時実行モード
        run_review_job(dry_run=dry_run)


if __name__ == "__main__":
    main()
