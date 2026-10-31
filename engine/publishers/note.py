"""note に下書き保存（公式APIが無いので Playwright）。
初回だけ `python -m engine note-login` でログイン状態を data/note_state.json に保存。
※ note の画面変更でセレクタが変わったらここだけ直す。"""
import asyncio
from pathlib import Path

STATE = Path("data/note_state.json")


async def _login():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)
        ctx = await b.new_context()
        page = await ctx.new_page()
        await page.goto("https://note.com/login")
        await asyncio.to_thread(input, "ブラウザで note にログインしたら Enter: ")
        await ctx.storage_state(path=str(STATE))
        await b.close()
    print(f"保存: {STATE}")


async def _draft(post, headless=True):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=headless)
        ctx = await b.new_context(storage_state=str(STATE))
        page = await ctx.new_page()
        await page.goto("https://note.com/notes/new", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        await page.locator("textarea[placeholder*='タイトル'], [placeholder*='タイトル']").first.fill(post["title"])
        editor = page.locator(".ProseMirror, [contenteditable='true']").first
        await editor.click()
        # Markdown は note エディタが一部自動変換する。見出し記号はそのまま貼る
        await page.keyboard.insert_text(post["body"])
        await page.wait_for_timeout(1500)
        btn = page.get_by_role("button", name="下書き保存")
        if await btn.count():
            await btn.first.click()
        await page.wait_for_timeout(3000)
        url = page.url
        await b.close()
        return url


def login():
    asyncio.run(_login())


def publish(post, cfg):
    if not STATE.exists():
        raise RuntimeError("先に python -m engine note-login")
    return asyncio.run(_draft(post, headless=cfg.get("note_headless", True)))
