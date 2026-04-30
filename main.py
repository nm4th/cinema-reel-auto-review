"""ゲストレビュー自動投稿 - メインエントリーポイント

スペースマーケットとインスタベースの両方のレビューを自動投稿する。

使い方:
  python main.py                       # 今日分を即時実行（ドライラン）
  python main.py --date 2026-03-30     # 指定日分を即時実行（ドライラン）
  python main.py --no-dry-run          # 今日分を本番モードで実行
  python main.py --service spacemarket # スペースマーケットのみ
  python main.py --service instabase   # インスタベースのみ
  python main.py --schedule            # 毎日22:30に自動実行
"""

import argparse
import logging
import os
import time
from datetime import date, datetime

import schedule

import config
from spacemarket_reviewer import SpaceMarketReviewer
from instabase_reviewer import InstabaseReviewer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def run_review_job(dry_run: bool = True, target_date: date | None = None, service: str = "all"):
    """レビュー投稿ジョブを実行する"""
    os.makedirs("screenshots", exist_ok=True)

    # スペースマーケット
    if service in ("all", "spacemarket"):
        try:
            logger.info("========================================")
            logger.info("  スペースマーケット レビュー投稿")
            logger.info("========================================")
            sm_reviewer = SpaceMarketReviewer(dry_run=dry_run)
            sm_reviewer.run(target_date=target_date)
        except Exception as e:
            logger.error(f"スペースマーケット処理でエラー: {e}")

    # インスタベース
    if service in ("all", "instabase"):
        try:
            logger.info("========================================")
            logger.info("  インスタベース レビュー投稿")
            logger.info("========================================")
            ib_reviewer = InstabaseReviewer(dry_run=dry_run)
            ib_reviewer.run()
        except Exception as e:
            logger.error(f"インスタベース処理でエラー: {e}")


def main():
    parser = argparse.ArgumentParser(description="ゲストレビュー自動投稿ツール（スペースマーケット＋インスタベース）")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="スペースマーケットの対象日 (YYYY-MM-DD形式)。省略時は今日。",
    )
    parser.add_argument(
        "--service",
        type=str,
        default="all",
        choices=["all", "spacemarket", "instabase"],
        help="実行するサービス (デフォルト: all)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help=f"毎日{config.SCHEDULE_TIME}に自動実行するスケジューラモード",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="本番モード（実際にレビューを投稿する）",
    )
    args = parser.parse_args()

    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    dry_run = config.DRY_RUN
    if args.no_dry_run:
        dry_run = False

    if dry_run:
        logger.info("ドライランモード: 実際にはレビューを投稿しません")
    else:
        logger.warning("本番モード: 実際にレビューを投稿します！")

    if not config.SPACEMARKET_EMAIL or not config.SPACEMARKET_PASSWORD:
        logger.error("ログイン情報が設定されていません。.envファイルを確認してください。")
        return

    if args.schedule:
        logger.info(f"スケジューラモード: 毎日 {config.SCHEDULE_TIME} に実行します")
        schedule.every().day.at(config.SCHEDULE_TIME).do(
            run_review_job, dry_run=dry_run, target_date=None, service=args.service
        )

        logger.info("初回実行を開始します...")
        run_review_job(dry_run=dry_run, target_date=target_date, service=args.service)

        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run_review_job(dry_run=dry_run, target_date=target_date, service=args.service)


if __name__ == "__main__":
    main()
