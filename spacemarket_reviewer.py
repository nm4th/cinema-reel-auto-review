"""スペースマーケット ゲストレビュー自動投稿モジュール"""

import logging
import os
import re
from datetime import date
from playwright.sync_api import sync_playwright, Page, Browser

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class SpaceMarketReviewer:
    """スペースマーケットのゲストレビューを自動投稿するクラス"""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.browser: Browser | None = None
        self.page: Page | None = None

    def start_browser(self, playwright):
        """ブラウザを起動する"""
        self.browser = playwright.chromium.launch(headless=True)
        context = self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
        )
        self.page = context.new_page()
        logger.info("ブラウザ起動完了")

    def close_browser(self):
        """ブラウザを終了する"""
        if self.browser:
            self.browser.close()
            logger.info("ブラウザ終了")

    def login(self):
        """スペースマーケットにログインする"""
        logger.info("ログイン開始...")
        self.page.goto(config.LOGIN_URL, wait_until="networkidle")
        self.page.wait_for_timeout(3000)

        # メールアドレス入力
        for selector in [
            'input[name="email"]', 'input[type="email"]',
            'input[placeholder*="メール"]', 'input[autocomplete="email"]',
        ]:
            el = self.page.query_selector(selector)
            if el:
                el.fill(config.SPACEMARKET_EMAIL)
                logger.info(f"  メール入力: {selector}")
                break
        else:
            text_inputs = self.page.query_selector_all('input[type="text"], input:not([type])')
            if text_inputs:
                text_inputs[0].fill(config.SPACEMARKET_EMAIL)

        # パスワード入力
        for selector in ['input[name="password"]', 'input[type="password"]']:
            el = self.page.query_selector(selector)
            if el:
                el.fill(config.SPACEMARKET_PASSWORD)
                logger.info(f"  パスワード入力: {selector}")
                break

        # ログインボタンクリック
        for selector in [
            'input[type="submit"][name="commit"]', 'input[type="submit"]',
            'button[type="submit"]', 'button:has-text("ログイン")',
            'input[value="ログイン"]', 'form button',
        ]:
            btn = self.page.query_selector(selector)
            if btn:
                btn.click()
                logger.info(f"  ログインボタン: {selector}")
                break
        else:
            self.page.keyboard.press("Enter")

        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(5000)
        logger.info(f"ログイン完了 (URL: {self.page.url})")

    def navigate_to_inbox(self):
        """受信トレイに移動する"""
        logger.info("受信トレイに移動中...")
        self.page.goto(config.INBOX_URL_PREFIX, wait_until="networkidle")
        self.page.wait_for_timeout(3000)
        logger.info("受信トレイ表示完了")

    def get_reservations_by_date(self, target_date: date) -> list[dict]:
        """受信トレイ一覧から対象日の「利用完了」予約を抽出する

        一覧の各スレッドには日付・ステータス・ゲスト名が表示されているので、
        ページ遷移なしで高速にフィルタできる。
        """
        logger.info(f"対象日 {target_date} のゲストを受信トレイから検索中...")

        # 日付フォーマット: 2026/3/30 or 2026/03/30
        target_str_1 = f"{target_date.year}/{target_date.month}/{target_date.day}"
        target_str_2 = f"{target_date.year}/{target_date.month:02d}/{target_date.day:02d}"

        reservations = []

        # 各スレッド（Reservation__Container）を取得
        containers = self.page.query_selector_all('a[class*="Reservation__Container"]')
        logger.info(f"  受信トレイのスレッド数: {len(containers)}件")

        for container in containers:
            # ステータスを取得
            status_el = container.query_selector('[class*="HeaderStatus__StatusText"]')
            status = status_el.inner_text().strip() if status_el else ""

            # 「利用完了」以外はスキップ
            if status != "利用完了":
                continue

            # 日時テキストを取得
            date_el = container.query_selector('[class*="Schedule__DateTimeText"]')
            date_text = date_el.inner_text().strip() if date_el else ""

            # 対象日と一致するかチェック
            if target_str_1 not in date_text and target_str_2 not in date_text:
                continue

            # スレッドIDを取得
            href = container.get_attribute("href") or ""
            match = re.search(r"/inbox/(\d+)", href)
            if not match:
                continue
            thread_id = match.group(1)

            # ゲスト名を取得
            name_el = container.query_selector('[class*="ListItemUserInfo__UserName"]')
            guest_name = name_el.inner_text().strip() if name_el else "不明"

            reservations.append({
                "thread_id": thread_id,
                "url": f"{config.INBOX_URL_PREFIX}/{thread_id}",
                "date_text": date_text,
                "guest_name": guest_name,
            })
            logger.info(f"  → 対象: {guest_name} ({date_text}) スレッド#{thread_id}")

        logger.info(f"対象ゲスト数: {len(reservations)}件")
        return reservations

    def post_review(self, thread_id: str, guest_name: str) -> bool:
        """指定スレッドのレビューを投稿する"""
        thread_url = f"{config.INBOX_URL_PREFIX}/{thread_id}"
        self.page.goto(thread_url, wait_until="networkidle")
        self.page.wait_for_timeout(3000)

        # 「レビューの投稿」ボタンがあるか確認（なければ投稿済み）
        review_btn = None
        for selector in [
            'a:has-text("レビューの投稿")',
            'button:has-text("レビューの投稿")',
        ]:
            review_btn = self.page.query_selector(selector)
            if review_btn:
                break

        if not review_btn:
            logger.info(f"  → {guest_name}: レビュー投稿済み、スキップ")
            return False

        # 「レビューの投稿」ボタンをクリック（サイドバー）
        logger.info(f"  → {guest_name}: レビューの投稿ボタンをクリック")
        review_btn.click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(3000)

        # 星5をクリック
        logger.info(f"  → 星{config.REVIEW_STARS}を選択")
        star_clicked = False

        for sel in ['[class*="star"]', '[class*="Star"]', '[class*="rating"]', 'svg', 'label']:
            stars = self.page.query_selector_all(sel)
            if stars and len(stars) >= 5:
                stars[4].click()
                self.page.wait_for_timeout(500)
                star_clicked = True
                break

        if not star_clicked:
            # 座標クリック方式
            rating_header = self.page.query_selector('text=星をクリックして評価')
            if rating_header:
                box = rating_header.bounding_box()
                if box:
                    self.page.mouse.click(box["x"] + 140, box["y"] + box["height"] + 20)
                    self.page.wait_for_timeout(500)
                    star_clicked = True

        if not star_clicked:
            logger.warning(f"  → {guest_name}: 星を選択できませんでした")
            self.page.screenshot(path=f"screenshots/star_failed_{thread_id}.png")
            return False

        # メッセージ入力
        logger.info(f"  → メッセージ入力: {config.REVIEW_MESSAGE}")
        textarea = self.page.query_selector("textarea")
        if textarea:
            textarea.fill(config.REVIEW_MESSAGE)
        else:
            logger.warning(f"  → {guest_name}: テキストエリアが見つかりません")
            self.page.screenshot(path=f"screenshots/textarea_failed_{thread_id}.png")
            return False
        self.page.wait_for_timeout(500)

        # ドライランチェック
        if self.dry_run:
            logger.info(f"  → {guest_name}: [ドライラン] 投稿をスキップしました")
            self.page.screenshot(path=f"screenshots/dryrun_{thread_id}.png")
            return True

        # 「レビューの投稿」送信ボタン（FloatBottom内）
        logger.info("  → フォーム下部の「レビューの投稿」ボタンをクリック")
        submit_button = None
        for selector in [
            '[class*="FloatBottom"] a:has-text("レビューの投稿")',
            '[class*="FloatBottom"] span:has-text("レビューの投稿")',
        ]:
            submit_button = self.page.query_selector(selector)
            if submit_button:
                break
        if not submit_button:
            all_btns = self.page.query_selector_all('a:has-text("レビューの投稿")')
            if all_btns:
                submit_button = all_btns[-1]

        if not submit_button:
            logger.warning(f"  → {guest_name}: 送信ボタンが見つかりません")
            self.page.screenshot(path=f"screenshots/submit_failed_{thread_id}.png")
            return False

        submit_button.click()
        self.page.wait_for_timeout(2000)

        # 確認ダイアログの「投稿」ボタン
        logger.info("  → 確認ダイアログの「投稿」ボタンをクリック")
        confirm_btn = None
        for selector in [
            '[class*="ConfirmContent"] a:has-text("投稿")',
            '[class*="Confirm"] a:has-text("投稿")',
            '[class*="modal"] a:has-text("投稿")',
        ]:
            confirm_btn = self.page.query_selector(selector)
            if confirm_btn:
                break
        if not confirm_btn:
            all_btns = self.page.query_selector_all('a:has(span:text-is("投稿"))')
            if all_btns:
                confirm_btn = all_btns[-1]

        if confirm_btn:
            confirm_btn.click()
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(3000)
            logger.info(f"  → {guest_name}: レビュー投稿完了！")
            self.page.screenshot(path=f"screenshots/done_{thread_id}.png")
            return True
        else:
            logger.warning(f"  → {guest_name}: 確認ダイアログの投稿ボタンが見つかりません")
            self.page.screenshot(path=f"screenshots/confirm_failed_{thread_id}.png")
            return False

    def run(self, target_date: date | None = None):
        """メイン処理: 対象日の利用完了ゲスト全員にレビューを投稿する"""
        if target_date is None:
            target_date = date.today()

        mode = "ドライラン" if self.dry_run else "本番"
        logger.info(f"=== スペースマーケット レビュー自動投稿 開始 ===")
        logger.info(f"  対象日: {target_date} / モード: {mode}")

        os.makedirs("screenshots", exist_ok=True)

        with sync_playwright() as playwright:
            try:
                self.start_browser(playwright)
                self.login()
                self.navigate_to_inbox()

                # 受信トレイ一覧から対象日のゲストを抽出
                reservations = self.get_reservations_by_date(target_date)

                if not reservations:
                    logger.info(f"対象日({target_date})のレビュー対象ゲストはいません。")
                    self.page.screenshot(path="screenshots/no_targets.png")
                    return

                success_count = 0
                for res in reservations:
                    try:
                        logger.info(f"--- {res['guest_name']} ({res['date_text']}) ---")
                        if self.post_review(res["thread_id"], res["guest_name"]):
                            success_count += 1
                    except Exception as e:
                        logger.error(f"  → {res['guest_name']}: エラー: {e}")
                        if self.page:
                            self.page.screenshot(path=f"screenshots/error_{res['thread_id']}.png")

                logger.info(f"=== 完了 ===")
                logger.info(f"  対象日: {target_date}")
                logger.info(f"  対象ゲスト: {len(reservations)}件")
                logger.info(f"  レビュー投稿: {success_count}件 ({mode})")

            except Exception as e:
                logger.error(f"処理中にエラーが発生: {e}")
                if self.page:
                    self.page.screenshot(path="screenshots/fatal_error.png")
                raise
            finally:
                self.close_browser()
