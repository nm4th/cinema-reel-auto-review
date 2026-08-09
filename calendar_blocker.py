"""Google カレンダー 準備時間ブロック自動挿入モジュール

スペースマーケットの予約の開始15分前に「準備時間」イベントを自動作成する。
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))


class CalendarPrepBlocker:
    """スペースマーケット予約の前に準備時間ブロックを挿入する"""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.service = None

    def authenticate(self):
        """Google Calendar API に認証する"""
        logger.info("Google Calendar API に認証中...")

        creds_json = config.GOOGLE_CREDENTIALS_JSON
        if not creds_json:
            # ファイルパスとして試す
            creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
            if creds_path and os.path.exists(creds_path):
                with open(creds_path, "r") as f:
                    creds_json = f.read()
            else:
                raise ValueError("GOOGLE_CALENDAR_CREDENTIALS が設定されていません")

        creds_data = json.loads(creds_json)
        credentials = Credentials.from_service_account_info(
            creds_data,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        self.service = build("calendar", "v3", credentials=credentials)
        logger.info("認証完了")

    def get_spacemarket_events(self, target_date: datetime | None = None) -> list[dict]:
        """スペースマーケットの予約イベントを取得する

        「【予約完了】」かつ「スペースマーケット」を含むイベントを検索。
        """
        if target_date is None:
            target_date = datetime.now(JST)

        # 翌日〜7日後のイベントを検索（準備時間は未来の予約に必要）
        time_min = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = time_min + timedelta(days=7)

        logger.info(f"スペースマーケット予約を検索中: {time_min.date()} 〜 {time_max.date()}")

        events_result = self.service.events().list(
            calendarId=config.GOOGLE_CALENDAR_ID,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        logger.info(f"  全イベント数: {len(events)}件")

        # スペースマーケットの予約をフィルタ
        sm_events = []
        for event in events:
            title = event.get("summary", "")
            if "【予約完了】" in title and "スペースマーケット" in title:
                start = event["start"].get("dateTime", "")
                end = event["end"].get("dateTime", "")
                sm_events.append({
                    "id": event["id"],
                    "title": title,
                    "start": start,
                    "end": end,
                })
                logger.info(f"  → 対象: {title}")
                logger.info(f"       {start} 〜 {end}")

        logger.info(f"スペースマーケット予約数: {len(sm_events)}件")
        return sm_events

    def check_prep_block_exists(self, prep_start: str, prep_end: str) -> bool:
        """指定時間帯に既に準備時間ブロックが存在するか確認する"""
        events_result = self.service.events().list(
            calendarId=config.GOOGLE_CALENDAR_ID,
            timeMin=prep_start,
            timeMax=prep_end,
            singleEvents=True,
        ).execute()

        events = events_result.get("items", [])
        for event in events:
            if event.get("summary", "") == config.PREP_EVENT_TITLE:
                return True
        return False

    def create_prep_block(self, event: dict) -> bool:
        """スペースマーケット予約の前に準備時間ブロックを作成する"""
        title = event["title"]
        start_str = event["start"]

        if not start_str:
            logger.warning(f"  → {title}: 開始時間が不明、スキップ")
            return False

        # 開始時間の15分前を計算
        start_dt = datetime.fromisoformat(start_str)
        prep_start_dt = start_dt - timedelta(minutes=config.PREP_TIME_MINUTES)
        prep_end_dt = start_dt

        prep_start = prep_start_dt.isoformat()
        prep_end = prep_end_dt.isoformat()

        # 既に準備時間ブロックがあるか確認
        if self.check_prep_block_exists(prep_start, prep_end):
            logger.info(f"  → {title}: 準備時間ブロック既存、スキップ")
            return False

        logger.info(f"  → {title}: 準備時間ブロックを作成")
        logger.info(f"       {prep_start_dt.strftime('%m/%d %H:%M')} 〜 {prep_end_dt.strftime('%H:%M')}")

        if self.dry_run:
            logger.info("    [ドライラン] 作成をスキップしました")
            return True

        # イベントを作成
        prep_event = {
            "summary": config.PREP_EVENT_TITLE,
            "start": {"dateTime": prep_start, "timeZone": "Asia/Tokyo"},
            "end": {"dateTime": prep_end, "timeZone": "Asia/Tokyo"},
            "description": f"自動作成: {title} の準備時間",
        }

        self.service.events().insert(
            calendarId=config.GOOGLE_CALENDAR_ID,
            body=prep_event,
        ).execute()

        logger.info("    作成完了！")
        return True

    def run(self):
        """メイン処理: スペースマーケット予約の前に準備時間ブロックを挿入する"""
        mode = "ドライラン" if self.dry_run else "本番"
        logger.info(f"=== Google カレンダー 準備時間ブロック挿入 開始 ({mode}モード) ===")

        try:
            self.authenticate()
            events = self.get_spacemarket_events()

            if not events:
                logger.info("対象のスペースマーケット予約はありません。")
                return

            created_count = 0
            for event in events:
                try:
                    if self.create_prep_block(event):
                        created_count += 1
                except Exception as e:
                    logger.error(f"  → エラー: {e}")

            logger.info(f"=== 完了: {created_count}件 準備時間ブロック作成 ({mode}) ===")

        except Exception as e:
            logger.error(f"処理中にエラーが発生: {e}")
            raise
