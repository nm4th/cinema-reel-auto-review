"""スペースマーケット ゲストレビュー自動投稿モジュール"""

import logging
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

        # メールアドレス入力 - 複数のセレクタを試す
        email_selectors = [
            'input[name="email"]', 'input[type="email"]',
            'input[placeholder*="メール"]', 'input[placeholder*="mail"]',
            'input[autocomplete="email"]', 'input[id*="email"]',
        ]
        for selector in email_selectors:
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
        pw_selectors = [
            'input[name="password"]', 'input[type="password"]',
            'input[autocomplete="current-password"]',
        ]
        for selector in pw_selectors:
            el = self.page.query_selector(selector)
            if el:
                el.fill(config.SPACEMARKET_PASSWORD)
                logger.info(f"  パスワード入力: {selector}")
                break

        # ログインボタンクリック - 複数のセレクタを試す
        login_selectors = [
            'button[type="submit"]', 'input[type="submit"]',
            'button:has-text("ログイン")', 'a:has-text("ログイン")',
            'button:has-text("Log in")', 'form button',
        ]
        for selector in login_selectors:
            btn = self.page.query_selector(selector)
            if btn:
                btn.click()
                logger.info(f"  ログインボタン: {selector}")
                break
        else:
            self.page.keyboard.press("Enter")

        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(5000)
        logger.info("ログイン完了")

    def navigate_to_inbox(self):
        """受信トレイに移動する"""
        logger.info("受信トレイに移動中...")
        self.page.goto(config.INBOX_URL_PREFIX, wait_until="networkidle")
        self.page.wait_for_timeout(2000)
        logger.info("受信トレイ表示完了")

    def get_today_completed_reservations(self) -> list[dict]:
        """今日利用完了したゲストの予約一覧を取得する

        受信トレイから「利用完了」ステータスのメッセージスレッドを探し、
        その中でレビュー未投稿のものを返す。
        """
        today = date.today()
        logger.info(f"本日({today})の利用完了ゲストを検索中...")

        reservations = []

        # 受信トレイのメッセージスレッド一覧を取得
        # スペースマーケットの受信トレイはメッセージスレッド形式
        thread_links = self.page.query_selector_all('a[href*="/inbox/"]')

        for link in thread_links:
            href = link.get_attribute("href")
            if not href or "/inbox/" not in href:
                continue

            thread_text = link.inner_text()

            # 利用完了のスレッドを対象にする
            if "利用完了" in thread_text:
                thread_id = href.split("/inbox/")[-1].split("/")[0].split("?")[0]
                reservations.append({
                    "thread_id": thread_id,
                    "url": href if href.startswith("http") else f"{config.BASE_URL}{href}",
                    "text": thread_text.strip()[:80],
                })

        logger.info(f"利用完了ゲスト数: {len(reservations)}件")
        return reservations

    def check_review_available(self) -> bool:
        """現在のスレッドでレビュー投稿が可能かチェックする"""
        # 「レビューの投稿」ボタンが存在するかチェック
        review_button = self.page.query_selector(
            'text=レビューの投稿, a:has-text("レビューの投稿"), button:has-text("レビューの投稿")'
        )
        return review_button is not None

    def post_review_for_thread(self, reservation: dict) -> bool:
        """指定のスレッドに対してレビューを投稿する

        Args:
            reservation: 予約情報（thread_id, urlを含む）

        Returns:
            投稿成功ならTrue
        """
        thread_url = reservation["url"]
        logger.info(f"スレッドに移動: {reservation['text']}")

        # スレッドページに移動
        self.page.goto(thread_url, wait_until="networkidle")
        self.page.wait_for_timeout(2000)

        # レビュー投稿ボタンがあるか確認
        if not self.check_review_available():
            logger.info("  → レビュー投稿ボタンなし（投稿済みまたは対象外）スキップ")
            return False

        # 「レビューの投稿」ボタンをクリック
        logger.info("  → レビューの投稿ボタンをクリック")
        self.page.click('text=レビューの投稿, a:has-text("レビューの投稿"), button:has-text("レビューの投稿")')
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(2000)

        # 星5をクリック（5番目の星をクリック）
        logger.info(f"  → 星{config.REVIEW_STARS}を選択")
        stars = self.page.query_selector_all('[class*="star"], [data-rating], svg[class*="star"], label[for*="star"]')

        if stars and len(stars) >= config.REVIEW_STARS:
            stars[config.REVIEW_STARS - 1].click()
        else:
            # 代替: 星の要素が見つからない場合、nth-child セレクタを試す
            logger.info("  → 星セレクタを代替方法で検索中...")
            star_container = self.page.query_selector('[class*="rating"], [class*="star"]')
            if star_container:
                clickable_stars = star_container.query_selector_all("svg, span, label, i")
                if clickable_stars and len(clickable_stars) >= config.REVIEW_STARS:
                    clickable_stars[config.REVIEW_STARS - 1].click()
                else:
                    logger.warning("  → 星要素が見つかりません。スクリーンショットを保存します。")
                    self.page.screenshot(path="screenshots/star_not_found.png")
                    return False
            else:
                logger.warning("  → 星コンテナが見つかりません。スクリーンショットを保存します。")
                self.page.screenshot(path="screenshots/star_container_not_found.png")
                return False

        self.page.wait_for_timeout(500)

        # レビューメッセージを入力
        logger.info(f"  → メッセージ入力: {config.REVIEW_MESSAGE}")
        textarea = self.page.query_selector("textarea")
        if textarea:
            textarea.fill(config.REVIEW_MESSAGE)
        else:
            logger.warning("  → テキストエリアが見つかりません")
            self.page.screenshot(path="screenshots/textarea_not_found.png")
            return False

        self.page.wait_for_timeout(500)

        # ドライランチェック
        if self.dry_run:
            logger.info("  → [ドライラン] 投稿をスキップしました（実際には送信しません）")
            self.page.screenshot(path=f"screenshots/dryrun_{reservation['thread_id']}.png")
            return True

        # 投稿ボタンをクリック
        logger.info("  → レビューを送信中...")
        submit_button = self.page.query_selector(
            'button:has-text("投稿"), button[type="submit"]:has-text("投稿"), input[type="submit"]'
        )
        if submit_button:
            submit_button.click()
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(2000)
            logger.info("  → レビュー投稿完了！")
            return True
        else:
            logger.warning("  → 送信ボタンが見つかりません")
            self.page.screenshot(path="screenshots/submit_not_found.png")
            return False

    def run(self):
        """メイン処理: 今日の利用完了ゲスト全員にレビューを投稿する"""
        mode = "ドライラン" if self.dry_run else "本番"
        logger.info(f"=== スペースマーケット レビュー自動投稿 開始 ({mode}モード) ===")

        with sync_playwright() as playwright:
            try:
                self.start_browser(playwright)
                self.login()
                self.navigate_to_inbox()

                reservations = self.get_today_completed_reservations()

                if not reservations:
                    logger.info("本日のレビュー対象ゲストはいません。")
                    return

                success_count = 0
                for reservation in reservations:
                    try:
                        if self.post_review_for_thread(reservation):
                            success_count += 1
                    except Exception as e:
                        logger.error(f"  → レビュー投稿エラー: {e}")
                        self.page.screenshot(
                            path=f"screenshots/error_{reservation['thread_id']}.png"
                        )

                    # 受信トレイに戻る
                    self.navigate_to_inbox()

                logger.info(
                    f"=== 完了: {success_count}/{len(reservations)}件 レビュー投稿 ({mode}モード) ==="
                )

            except Exception as e:
                logger.error(f"処理中にエラーが発生: {e}")
                if self.page:
                    self.page.screenshot(path="screenshots/fatal_error.png")
                raise
            finally:
                self.close_browser()
