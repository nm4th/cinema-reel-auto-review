"""テスト用: 特定のゲストスレッドに対してレビューを投稿する

使い方:
  python test_single_review.py THREAD_ID [--no-dry-run]
  例: python test_single_review.py 5275641
"""

import argparse
import logging
import os

from playwright.sync_api import sync_playwright

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def post_review_to_thread(thread_id: str, dry_run: bool = True):
    """特定のスレッドに対してレビューを投稿する"""
    mode = "ドライラン" if dry_run else "本番"
    thread_url = f"{config.BASE_URL}/sop_geaeuhcrx1dr/inbox/{thread_id}"

    logger.info(f"=== 単一スレッド レビュー投稿テスト ({mode}モード) ===")
    logger.info(f"対象スレッド: {thread_url}")

    os.makedirs("screenshots", exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
        )
        page = context.new_page()

        try:
            # Step 1: ログイン
            logger.info("Step 1: ログイン中...")
            page.goto(config.LOGIN_URL, wait_until="networkidle")
            page.wait_for_timeout(3000)
            page.screenshot(path="screenshots/01_login_page.png")

            # ログインページのHTML構造をダンプ（デバッグ用）
            login_html = page.content()
            with open("screenshots/01_login_page.html", "w", encoding="utf-8") as f:
                f.write(login_html)
            logger.info(f"  ログインページURL: {page.url}")

            # ページ内のinput要素とbutton要素を全て列挙
            inputs = page.query_selector_all("input")
            for inp in inputs:
                inp_type = inp.get_attribute("type") or ""
                inp_name = inp.get_attribute("name") or ""
                inp_placeholder = inp.get_attribute("placeholder") or ""
                logger.info(f"  INPUT: type={inp_type} name={inp_name} placeholder={inp_placeholder}")

            buttons = page.query_selector_all("button, a[role='button'], input[type='submit'], [class*='btn'], [class*='Button']")
            for btn in buttons:
                tag = btn.evaluate("el => el.tagName")
                text = btn.inner_text().strip()[:50] if tag != "INPUT" else ""
                btn_type = btn.get_attribute("type") or ""
                logger.info(f"  BUTTON: <{tag}> type={btn_type} text='{text}'")

            # メールアドレス入力 - 複数のセレクタを試す
            email_filled = False
            for selector in [
                'input[name="email"]',
                'input[type="email"]',
                'input[placeholder*="メール"]',
                'input[placeholder*="mail"]',
                'input[placeholder*="Mail"]',
                'input[placeholder*="Email"]',
                'input[autocomplete="email"]',
                'input[id*="email"]',
                'input[id*="Email"]',
            ]:
                el = page.query_selector(selector)
                if el:
                    el.fill(config.SPACEMARKET_EMAIL)
                    email_filled = True
                    logger.info(f"  メール入力: {selector}")
                    break

            if not email_filled:
                # 最終手段: 1番目のテキスト/email input
                text_inputs = page.query_selector_all('input[type="text"], input[type="email"], input:not([type])')
                if text_inputs:
                    text_inputs[0].fill(config.SPACEMARKET_EMAIL)
                    email_filled = True
                    logger.info("  メール入力: 最初のテキストinput")

            # パスワード入力
            pw_filled = False
            for selector in [
                'input[name="password"]',
                'input[type="password"]',
                'input[autocomplete="current-password"]',
                'input[id*="password"]',
                'input[id*="Password"]',
            ]:
                el = page.query_selector(selector)
                if el:
                    el.fill(config.SPACEMARKET_PASSWORD)
                    pw_filled = True
                    logger.info(f"  パスワード入力: {selector}")
                    break

            page.screenshot(path="screenshots/02_login_filled.png")

            if not email_filled or not pw_filled:
                logger.error(f"  ログインフォームが見つかりません (email={email_filled}, pw={pw_filled})")
                return False

            # ログインボタンをクリック - 複数のセレクタを試す
            login_clicked = False
            for selector in [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("ログイン")',
                'a:has-text("ログイン")',
                'button:has-text("Log in")',
                'button:has-text("Sign in")',
                '[class*="login"] button',
                '[class*="Login"] button',
                'form button',
            ]:
                btn = page.query_selector(selector)
                if btn:
                    btn.click()
                    login_clicked = True
                    logger.info(f"  ログインボタンクリック: {selector}")
                    break

            if not login_clicked:
                # 最終手段: Enterキーを送信
                logger.info("  ログインボタンが見つからないため、Enterキーを送信")
                page.keyboard.press("Enter")

            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)
            page.screenshot(path="screenshots/03_after_login.png")
            logger.info(f"  ログイン後URL: {page.url}")

            # ログイン後のページHTMLもダンプ
            after_login_html = page.content()
            with open("screenshots/03_after_login.html", "w", encoding="utf-8") as f:
                f.write(after_login_html)

            # Step 2: スレッドページに移動
            logger.info(f"Step 2: スレッドに移動中... ({thread_url})")
            page.goto(thread_url, wait_until="networkidle")
            page.wait_for_timeout(3000)
            page.screenshot(path="screenshots/04_thread_page.png")
            logger.info(f"  スレッドページURL: {page.url}")

            # ページの内容をログに出力（デバッグ用）
            page_text = page.inner_text("body")
            logger.info(f"  ページテキスト (先頭500文字): {page_text[:500]}")

            # Step 3: 「レビューの投稿」ボタンを探してクリック
            logger.info("Step 3: レビューの投稿ボタンを検索中...")

            # ボタンの候補を順番に試す
            review_btn = None
            for selector in [
                'a:has-text("レビューの投稿")',
                'button:has-text("レビューの投稿")',
                'text=レビューの投稿',
                '[href*="review"]',
            ]:
                review_btn = page.query_selector(selector)
                if review_btn:
                    logger.info(f"  レビューボタン発見: {selector}")
                    break

            if not review_btn:
                logger.error("  レビューの投稿ボタンが見つかりません")
                page.screenshot(path="screenshots/05_review_btn_not_found.png")
                # ページ内のリンクやボタンを全て出力
                all_buttons = page.query_selector_all("a, button")
                for btn in all_buttons:
                    text = btn.inner_text().strip()
                    href = btn.get_attribute("href") or ""
                    if text:
                        logger.info(f"    要素: [{btn.evaluate('el => el.tagName')}] text='{text}' href='{href}'")
                return False

            review_btn.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)
            page.screenshot(path="screenshots/05_review_form.png")
            logger.info(f"  レビューフォームURL: {page.url}")

            # Step 4: 星5をクリック
            logger.info("Step 4: 星5を選択中...")

            # スクリーンショットの星の形から、星はSVGまたはクリッカブルな要素の可能性
            star_clicked = False

            # 方法1: 星の候補セレクタを広く試す
            star_selectors = [
                '[class*="star"]',
                '[class*="Star"]',
                '[class*="rating"]',
                '[class*="Rating"]',
                'svg',
                '[role="radio"]',
                '[data-value]',
                'label',
            ]

            for sel in star_selectors:
                stars = page.query_selector_all(sel)
                if stars and len(stars) >= 5:
                    logger.info(f"  星要素発見: {sel} ({len(stars)}個)")
                    # 5番目（インデックス4）をクリック
                    stars[4].click()
                    page.wait_for_timeout(500)
                    page.screenshot(path="screenshots/06_stars_clicked.png")
                    star_clicked = True
                    break

            if not star_clicked:
                # 方法2: テキスト「星をクリックして評価」の近くの要素を探す
                logger.info("  星要素を座標クリックで試行...")
                rating_header = page.query_selector('text=星をクリックして評価')
                if rating_header:
                    box = rating_header.bounding_box()
                    if box:
                        # 星は「星をクリックして評価」の下に横並びで表示される
                        # 5番目の星は右端付近
                        star5_x = box["x"] + 140  # 5番目の星のおおよそのX座標
                        star5_y = box["y"] + box["height"] + 20  # テキストの下
                        page.mouse.click(star5_x, star5_y)
                        page.wait_for_timeout(500)
                        page.screenshot(path="screenshots/06_stars_clicked_coord.png")
                        star_clicked = True
                        logger.info(f"  座標クリック: ({star5_x}, {star5_y})")

            if not star_clicked:
                logger.error("  星を選択できませんでした")
                page.screenshot(path="screenshots/06_star_failed.png")
                return False

            # Step 5: メッセージ入力
            logger.info(f"Step 5: メッセージ入力: {config.REVIEW_MESSAGE}")
            textarea = page.query_selector("textarea")
            if textarea:
                textarea.fill(config.REVIEW_MESSAGE)
                page.wait_for_timeout(500)
                page.screenshot(path="screenshots/07_message_filled.png")
                logger.info("  メッセージ入力完了")
            else:
                logger.error("  テキストエリアが見つかりません")
                page.screenshot(path="screenshots/07_textarea_not_found.png")
                return False

            # Step 6: 投稿
            if dry_run:
                logger.info("Step 6: [ドライラン] 投稿をスキップします")
                page.screenshot(path="screenshots/08_dryrun_final.png")
                logger.info("=== ドライラン完了 - スクリーンショットを確認してください ===")
                return True

            logger.info("Step 6: レビューを投稿中...")
            submit_btn = None
            for selector in [
                'button:has-text("レビューの投稿")',
                'button[type="submit"]',
                'input[type="submit"]',
            ]:
                submit_btn = page.query_selector(selector)
                if submit_btn:
                    text = submit_btn.inner_text().strip() if submit_btn.evaluate('el => el.tagName') != 'INPUT' else ''
                    logger.info(f"  送信ボタン発見: {selector} text='{text}'")
                    break

            if submit_btn:
                submit_btn.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(3000)
                page.screenshot(path="screenshots/08_after_submit.png")
                logger.info(f"  投稿後URL: {page.url}")
                logger.info("=== レビュー投稿完了！ ===")
                return True
            else:
                logger.error("  送信ボタンが見つかりません")
                page.screenshot(path="screenshots/08_submit_not_found.png")
                return False

        except Exception as e:
            logger.error(f"エラー: {e}")
            page.screenshot(path="screenshots/error.png")
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="単一スレッドへのレビュー投稿テスト")
    parser.add_argument("thread_id", help="対象スレッドID (例: 5275641)")
    parser.add_argument("--no-dry-run", action="store_true", help="本番モード")
    args = parser.parse_args()

    dry_run = not args.no_dry_run
    post_review_to_thread(args.thread_id, dry_run=dry_run)
