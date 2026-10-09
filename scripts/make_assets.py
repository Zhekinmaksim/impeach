#!/usr/bin/env python3
"""Render the share card and the icons from their sources.

    pip install playwright pillow && playwright install chromium
    python3 scripts/make_assets.py

design/og.html   -> web/assets/og-card.png          1200 x 630
web/favicon.svg  -> web/assets/favicon-{32,180,512}.png, web/favicon.ico
web/assets/logo{,-dark}.svg -> logo{,-dark}.png      1600 wide, transparent

The logo SVGs themselves come from scripts/make_logo.py.

The outputs are committed. This only needs running when a source changes.
"""

import asyncio
import os

from PIL import Image
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "web", "assets")


async def main() -> None:
    svg = open(os.path.join(ROOT, "web", "favicon.svg"), encoding="utf-8").read()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 630})
        await page.goto("file://" + os.path.join(ROOT, "design", "og.html"))
        await page.evaluate("document.fonts.ready")
        await page.wait_for_timeout(300)
        await page.screenshot(path=os.path.join(ASSETS, "og-card.png"))
        for size in (32, 180, 512):
            icon = await browser.new_page(viewport={"width": size, "height": size})
            await icon.set_content(
                "<style>html,body{margin:0;background:transparent}svg{display:block;width:100vw;height:100vh}</style>" + svg
            )
            await icon.screenshot(path=os.path.join(ASSETS, "favicon-%d.png" % size), omit_background=True)
        for name, bg in (("logo", None), ("logo-dark", None)):
            logo = open(os.path.join(ASSETS, name + ".svg"), encoding="utf-8").read()
            shot = await browser.new_page(viewport={"width": 1600, "height": 407})
            await shot.set_content(
                "<style>html,body{margin:0;background:transparent}svg{display:block;width:1600px}</style>" + logo
            )
            await shot.locator("svg").screenshot(path=os.path.join(ASSETS, name + ".png"), omit_background=True)
        await browser.close()
    big = Image.open(os.path.join(ASSETS, "favicon-512.png"))
    big.save(os.path.join(ROOT, "web", "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    print("og-card.png, favicon-32/180/512.png, favicon.ico, logo.png, logo-dark.png")


if __name__ == "__main__":
    asyncio.run(main())
