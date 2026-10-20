"""Google カレンダー 準備時間・片付け時間ブロック自動挿入モジュール

- スペースマーケットの予約: 開始15分前に「準備時間」
- インスタベースの予約: 開始15分前に「準備時間」、終了後15分に「片付け時間」
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

# 対象予約の判定ルール（タイトルに全キーワードを含むもの）と、入れるブロックの種類
BOOKING_RULES = [
    {
        "name": "スペースマーケット",
        "keywords": ["【予約完了】", "スペースマーケット"],
        "prep": True,
        "cleanup": False,
    },
    {
        "name": "インスタベース",
        "keywords": ["【インスタベース】"],
        "prep": True,
        "cleanup": True,
    },
]


class CalendarPrepBlocker:
    """予約の前後に準備時間・片付け時間ブロックを挿入する"""

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

    def get_target_events(self) -> list[dict]:
        """今日〜7日後の対象予約イベントを取得する"""
        time_min = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = time_min + timedelta(days=7)

        logger.info(f"予約を検索中: {time_min.date()} 〜 {time_max.date()}")

        events_result = self.service.events().list(
            calendarId=config.GOOGLE_CALENDAR_ID,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        logger.info(f"  全イベント数: {len(events)}件")

        targets = []
        for event in events:
            title = event.get("summary", "")
            for rule in BOOKING_RULES:
                if all(k in title for k in rule["keywords"]):
                    start = event["start"].get("dateTime", "")
                    end = event["end"].get("dateTime", "")
                    targets.append({
                        "id": event["id"],
                        "title": title,
                        "start": start,
                        "end": end,
                        "rule": rule,
                    })
                    logger.info(f"  → 対象[{rule['name']}]: {title}")
                    logger.info(f"       {start} 〜 {end}")
                    break

        logger.info(f"対象予約数: {len(targets)}件")
        return targets

    def block_exists(self, block_title: str, block_start: str, block_end: str) -> bool:
        """指定時間帯に同じタイトルのブロックが既に存在するか確認する"""
        events_result = self.service.events().list(
            calendarId=config.GOOGLE_CALENDAR_ID,
            timeMin=block_start,
            timeMax=block_end,
            singleEvents=True,
        ).execute()

        for event in events_result.get("items", []):
            if event.get("summary", "") == block_title:
                return True
        return False

    def create_block(self, booking_title: str, block_title: str,
                     block_start_dt: datetime, block_end_dt: datetime) -> bool:
        """ブロックイベントを作成する（既存ならスキップ）"""
        block_start = block_start_dt.isoformat()
        block_end = block_end_dt.isoformat()
        span = f"{block_start_dt.strftime('%m/%d %H:%M')} 〜 {block_end_dt.strftime('%H:%M')}"

        if self.block_exists(block_title, block_start, block_end):
            logger.info(f"    {block_title} ({span}): 既存、スキップ")
            return False

        if self.dry_run:
            logger.info(f"    {block_title} ({span}): [ドライラン] 作成をスキップ")
            return True

        self.service.events().insert(
            calendarId=config.GOOGLE_CALENDAR_ID,
            body={
                "summary": block_title,
                "start": {"dateTime": block_start, "timeZone": "Asia/Tokyo"},
                "end": {"dateTime": block_end, "timeZone": "Asia/Tokyo"},
                "description": f"自動作成: {booking_title} の{block_title}",
            },
        ).execute()

        logger.info(f"    {block_title} ({span}): 作成完了")
        return True

    def create_blocks_for_booking(self, booking: dict) -> int:
        """予約1件に対して必要なブロックを作成し、作成数を返す"""
        title = booking["title"]
        rule = booking["rule"]

        if not booking["start"] or not booking["end"]:
            logger.warning(f"  → {title}: 終日予定または時間不明、スキップ")
            return 0

        logger.info(f"  → {title}")
        start_dt = datetime.fromisoformat(booking["start"])
        end_dt = datetime.fromisoformat(booking["end"])
        created = 0

        if rule["prep"]:
            prep_start = start_dt - timedelta(minutes=config.PREP_TIME_MINUTES)
            if self.create_block(title, config.PREP_EVENT_TITLE, prep_start, start_dt):
                created += 1

        if rule["cleanup"]:
            cleanup_end = end_dt + timedelta(minutes=config.CLEANUP_TIME_MINUTES)
            if self.create_block(title, config.CLEANUP_EVENT_TITLE, end_dt, cleanup_end):
                created += 1

        return created

    def run(self):
        """メイン処理: 対象予約の前後にブロックを挿入する"""
        mode = "ドライラン" if self.dry_run else "本番"
        logger.info(f"=== Google カレンダー ブロック挿入 開始 ({mode}モード) ===")

        self.authenticate()
        bookings = self.get_target_events()

        if not bookings:
            logger.info("対象の予約はありません。")
            return

        created_count = 0
        for booking in bookings:
            try:
                created_count += self.create_blocks_for_booking(booking)
            except Exception as e:
                logger.error(f"  → {booking['title']}: エラー: {e}")

        logger.info(f"=== 完了: {created_count}件 ブロック作成 ({mode}) ===")
