"""設定管理モジュール"""

import os
from dotenv import load_dotenv

load_dotenv()

# 共通認証情報（スペースマーケット・インスタベース共通）
SPACEMARKET_EMAIL = os.getenv("SPACEMARKET_EMAIL", "")
SPACEMARKET_PASSWORD = os.getenv("SPACEMARKET_PASSWORD", "")

# ドライランモード（デフォルト: ON）
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# レビュー設定（共通）
REVIEW_STARS = 5
REVIEW_MESSAGE = "ご利用いただきまして、ありがとうございました！"

# スペースマーケットURL
BASE_URL = "https://dashboard.spacemarket.com"
LOGIN_URL = "https://www.spacemarket.com/login?done=https%3A%2F%2Fdashboard.spacemarket.com%2F"
INBOX_URL_PREFIX = f"{BASE_URL}/sop_geaeuhcrx1dr/inbox"

# インスタベースURL
INSTABASE_LOGIN_URL = "https://www.instabase.jp/partners/sign_in"
INSTABASE_PENDING_REVIEWS_URL = "https://www.instabase.jp/partners/bookings/user_review_creatables"

# スケジュール設定
SCHEDULE_TIME = "23:00"
