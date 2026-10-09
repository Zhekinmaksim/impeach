#!/usr/bin/env python3
"""Point the share tags at the deployed address.

Link previews need absolute URLs: most crawlers will not resolve a relative
og:image. Run this once the domain is known, before `vercel --prod`.

    python3 scripts/set_site.py https://impeach.example
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "web", "index.html")


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        print(__doc__)
        return 2
    site = sys.argv[1].rstrip("/")
    html = open(PAGE, encoding="utf-8").read()
    rules = [
        (r'(<link rel="canonical" href=")[^"]*(")', site + "/"),
        (r'(<meta property="og:url" content=")[^"]*(")', site + "/"),
        (r'(<meta property="og:image" content=")[^"]*(")', site + "/assets/og-card.png"),
        (r'(<meta name="twitter:image" content=")[^"]*(")', site + "/assets/og-card.png"),
    ]
    for pattern, value in rules:
        html, n = re.subn(pattern, lambda m: m.group(1) + value + m.group(2), html)
        if n != 1:
            print("tag not found: " + pattern)
            return 1
    open(PAGE, "w", encoding="utf-8").write(html)
    print("share tags now point at " + site)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
