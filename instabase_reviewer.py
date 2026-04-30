"""インスタベース ゲストレビュー自動投稿モジュール"""

import logging
import os
from playwright.sync_api import sync_playwright, Page, Browser

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class InstabaseReviewer:
    """インスタベースのゲストレビューを自動投稿するクラス"""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.browser: Browser | None = None
        self.page: Page | None = None

    def start_browser(self, playwright):
        self.browser = playwright.chromium.launch(headless=True)
        context = self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
        )
        self.page = context.new_page()
        logger.info("ブラウザ起動完了")

    def close_browser(self):
        if self.browser:
            self.browser.close()
            logger.info("ブラウザ終了")

    def login(self):
        """インスタベースにログインする"""
        logger.info("ログイン開始...")
        self.page.goto(config.INSTABASE_LOGIN_URL, wait_until="networkidle")
        self.page.wait_for_timeout(3000)
        self.page.screenshot(path="screenshots/insta_01_login_page.png")
        logger.info(f"  ログインページURL: {self.page.url}")

        # メールアドレス入力
        for selector in [
            'input[name="email"]', 'input[type="email"]',
            'input[placeholder*="mail@instabase"]',
            'input[placeholder*="メール"]', 'input[id*="email"]',
        ]:
            el = self.page.query_selector(selector)
            if el:
                el.fill(config.SPACEMARKET_EMAIL)
                logger.info(f"  メール入力: {selector}")
                break
        else:
            text_inputs = self.page.query_selector_all('input[type="text"], input[type="email"]')
            if text_inputs:
                text_inputs[0].fill(config.SPACEMARKET_EMAIL)
                logger.info("  メール入力: 最初のテキストinput")

        # パスワード入力
        for selector in ['input[name="password"]', 'input[type="password"]']:
            el = self.page.query_selector(selector)
            if el:
                el.fill(config.SPACEMARKET_PASSWORD)
                logger.info(f"  パスワード入力: {selector}")
                break

        self.page.screenshot(path="screenshots/insta_02_login_filled.png")

        # ログインボタンクリック
        for selector in [
            'input[type="submit"]',
            'button[type="submit"]',
            'button:has-text("ログイン")',
            'input[value="ログイン"]',
            'a:has-text("ログイン")',
            'form button',
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
        self.page.screenshot(path="screenshots/insta_03_after_login.png")
        logger.info(f"ログイン完了 (URL: {self.page.url})")

        # ログイン後のポップアップを全て閉じる
        self._close_popups()

    def _close_popups(self):
        """ポップアップやモーダルを全て閉じる"""
        logger.info("  ポップアップを閉じています...")

        # 方法1: Escapeキーを複数回押す（モーダルを閉じる最も確実な方法）
        for i in range(3):
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(800)

        self.page.screenshot(path="screenshots/insta_03b_after_escape.png")

        # 方法2: 残っているポップアップの閉じるボタンをクリック
        closed = 0
        close_selectors = [
            # 汎用的な閉じるボタン
            'button.close',
            '.close',
            'button[aria-label="close"]',
            'button[aria-label="Close"]',
            '[aria-label="close"]',
            '[aria-label="Close"]',
            # モーダル系
            '[class*="modal"] .close',
            '[class*="Modal"] .close',
            '[class*="modal-close"]',
            '[class*="modalClose"]',
            # Delightedアンケート
            'div[class*="delighted"] button',
            'iframe + div button',
            # 汎用: role=dialog内の閉じるボタン
            '[role="dialog"] button:first-child',
        ]

        for selector in close_selectors:
            try:
                buttons = self.page.query_selector_all(selector)
                for btn in buttons:
                    try:
                        if btn.is_visible():
                            btn.click()
                            closed += 1
                            self.page.wait_for_timeout(500)
                    except Exception:
                        pass
            except Exception:
                pass

        # 方法3: ✕ / × テキストを持つクリッカブルな要素を探す
        for char in ["✕", "×", "✖", "╳", "ᳵ"]:
            try:
                elements = self.page.query_selector_all(f'button:has-text("{char}"), a:has-text("{char}"), span:has-text("{char}"), div:has-text("{char}")')
                for el in elements:
                    try:
                        if el.is_visible():
                            box = el.bounding_box()
                            # 小さい要素（閉じるボタンらしいもの）のみクリック
                            if box and box["width"] < 80 and box["height"] < 80:
                                el.click()
                                closed += 1
                                self.page.wait_for_timeout(500)
                    except Exception:
                        pass
            except Exception:
                pass

        # 方法4: Delightedのiframe内の閉じるボタン
        try:
            frames = self.page.frames
            for frame in frames:
                try:
                    close_btn = frame.query_selector('button[aria-label="close"], button.close, .close')
                    if close_btn and close_btn.is_visible():
                        close_btn.click()
                        closed += 1
                        self.page.wait_for_timeout(500)
                except Exception:
                    pass
        except Exception:
            pass

        if closed > 0:
            logger.info(f"  → {closed}個のポップアップを閉じました")
        else:
            logger.info("  → Escapeキーで閉じました（またはポップアップなし）")

        self.page.wait_for_timeout(1000)
        self.page.screenshot(path="screenshots/insta_03c_popups_closed.png")

    def navigate_to_pending_reviews(self):
        """「投稿前のレビュー」ページに移動する"""
        logger.info("投稿前のレビューページに移動中...")
        self.page.goto(config.INSTABASE_PENDING_REVIEWS_URL, wait_until="networkidle")
        self.page.wait_for_timeout(3000)
        self.page.screenshot(path="screenshots/insta_04_pending_reviews.png")
        logger.info(f"  URL: {self.page.url}")

    def get_pending_reviews(self) -> list[dict]:
        """投稿前のレビュー一覧から「レビューする」ボタンがある予約を取得する"""
        logger.info("レビュー対象を検索中...")

        reviews = []

        # テーブルの行を取得
        rows = self.page.query_selector_all("table tbody tr, table tr")
        logger.info(f"  テーブル行数: {len(rows)}件")

        for i, row in enumerate(rows):
            # 「レビューする」ボタン/リンクがあるか確認
            review_btn = row.query_selector('a:has-text("レビューする"), button:has-text("レビューする")')
            if not review_btn:
                continue

            # 予約情報を取得
            cells = row.query_selector_all("td")
            booking_id = ""
            guest_name = ""
            date_text = ""

            if cells:
                # 予約ID
                id_link = cells[0].query_selector("a") if len(cells) > 0 else None
                booking_id = id_link.inner_text().strip() if id_link else f"row_{i}"

                # 予約者名
                if len(cells) > 2:
                    name_el = cells[2].query_selector("a")
                    guest_name = name_el.inner_text().strip() if name_el else cells[2].inner_text().strip()

                # 利用日時
                if len(cells) > 3:
                    date_text = cells[3].inner_text().strip()

            # レビューするボタンのリンク先を取得
            href = review_btn.get_attribute("href") or ""

            reviews.append({
                "booking_id": booking_id,
                "guest_name": guest_name,
                "date_text": date_text,
                "href": href,
                "row_index": i,
            })
            logger.info(f"  → 対象: {guest_name} (予約ID: {booking_id}, {date_text})")

        logger.info(f"レビュー対象数: {len(reviews)}件")
        return reviews

    def post_review(self, review: dict) -> bool:
        """指定の予約に対してレビューを投稿する"""
        guest_name = review["guest_name"] or review["booking_id"]
        logger.info(f"--- {guest_name} のレビューを投稿中 ---")

        # レビューページに移動
        href = review["href"]
        if href:
            url = href if href.startswith("http") else f"https://www.instabase.jp{href}"
            self.page.goto(url, wait_until="networkidle")
        else:
            # hrefがない場合は投稿前のレビューページに戻って該当行のボタンをクリック
            self.navigate_to_pending_reviews()
            rows = self.page.query_selector_all("table tbody tr, table tr")
            if review["row_index"] < len(rows):
                btn = rows[review["row_index"]].query_selector(
                    'a:has-text("レビューする"), button:has-text("レビューする")'
                )
                if btn:
                    btn.click()
                else:
                    logger.warning(f"  → {guest_name}: レビューするボタンが見つかりません")
                    return False
            else:
                logger.warning(f"  → {guest_name}: 行が見つかりません")
                return False

        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(3000)
        self.page.screenshot(path=f"screenshots/insta_05_review_form_{review['booking_id']}.png")
        logger.info(f"  レビューフォーム表示 (URL: {self.page.url})")

        # コメント入力
        logger.info(f"  → コメント入力: {config.REVIEW_MESSAGE}")
        textarea = self.page.query_selector("textarea")
        if textarea:
            textarea.fill(config.REVIEW_MESSAGE)
        else:
            # textareaが見つからない場合、input[type=text]やcontentEditableを試す
            for selector in [
                'input[name*="comment"]', 'input[name*="review"]',
                '[contenteditable="true"]',
            ]:
                el = self.page.query_selector(selector)
                if el:
                    el.fill(config.REVIEW_MESSAGE)
                    break
            else:
                logger.warning(f"  → {guest_name}: コメント入力欄が見つかりません")
                self.page.screenshot(path=f"screenshots/insta_06_textarea_failed_{review['booking_id']}.png")
                return False

        self.page.wait_for_timeout(500)
        self.page.screenshot(path=f"screenshots/insta_06_comment_filled_{review['booking_id']}.png")

        # ドライランチェック
        if self.dry_run:
            logger.info(f"  → {guest_name}: [ドライラン] 投稿をスキップしました")
            return True

        # 「レビュー投稿する」ボタンをクリック
        logger.info("  → 「レビュー投稿する」ボタンをクリック")
        submit_btn = None
        for selector in [
            'input[type="submit"][value*="レビュー"]',
            'button:has-text("レビュー投稿する")',
            'input[type="submit"]',
            'button[type="submit"]',
            'a:has-text("レビュー投稿する")',
        ]:
            submit_btn = self.page.query_selector(selector)
            if submit_btn:
                logger.info(f"    送信ボタン: {selector}")
                break

        if not submit_btn:
            logger.warning(f"  → {guest_name}: 送信ボタンが見つかりません")
            self.page.screenshot(path=f"screenshots/insta_07_submit_failed_{review['booking_id']}.png")
            return False

        submit_btn.click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(3000)
        self.page.screenshot(path=f"screenshots/insta_07_after_submit_{review['booking_id']}.png")

        # 確認ダイアログがある場合の対応
        confirm_btn = None
        for selector in [
            'button:has-text("投稿")',
            'a:has-text("投稿")',
            'button:has-text("OK")',
            'button:has-text("はい")',
        ]:
            confirm_btn = self.page.query_selector(selector)
            if confirm_btn:
                logger.info(f"    確認ダイアログ: {selector}")
                confirm_btn.click()
                self.page.wait_for_load_state("networkidle")
                self.page.wait_for_timeout(3000)
                self.page.screenshot(path=f"screenshots/insta_08_confirmed_{review['booking_id']}.png")
                break

        logger.info(f"  → {guest_name}: レビュー投稿完了！")
        return True

    def run(self):
        """メイン処理: 投稿前のレビュー全件を投稿する"""
        mode = "ドライラン" if self.dry_run else "本番"
        logger.info(f"=== インスタベース レビュー自動投稿 開始 ({mode}モード) ===")

        os.makedirs("screenshots", exist_ok=True)

        with sync_playwright() as playwright:
            try:
                self.start_browser(playwright)
                self.login()
                self.navigate_to_pending_reviews()

                reviews = self.get_pending_reviews()

                if not reviews:
                    logger.info("投稿前のレビューはありません。")
                    return

                success_count = 0
                for review in reviews:
                    try:
                        if self.post_review(review):
                            success_count += 1
                    except Exception as e:
                        guest = review["guest_name"] or review["booking_id"]
                        logger.error(f"  → {guest}: エラー: {e}")
                        if self.page:
                            self.page.screenshot(path=f"screenshots/insta_error_{review['booking_id']}.png")

                logger.info(f"=== インスタベース完了 ===")
                logger.info(f"  レビュー投稿: {success_count}/{len(reviews)}件 ({mode})")

            except Exception as e:
                logger.error(f"処理中にエラーが発生: {e}")
                if self.page:
                    self.page.screenshot(path="screenshots/insta_fatal_error.png")
                raise
            finally:
                self.close_browser()
