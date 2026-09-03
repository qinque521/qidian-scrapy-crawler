"""手动刷新起点的 cookie（爬虫也会自动调用同一套逻辑，这个脚本用于手动/排障）。

用法：
    python refresh_cookie.py                 # 无头模式（默认，已验证可用）
    python refresh_cookie.py --headful       # 有头模式，无头被识别成机器人时改用
    python refresh_cookie.py --check         # 取完立刻发一次请求验证是否真的解封
"""

import argparse
import sys

from qidian2.cookie_refresher import COOKIE_FILE, LIST_URL, UA
from qidian2.cookie_refresher import fetch_cookie, save_cookie_str


def check() -> bool:
    """用刚拿到的 cookie 请求一次列表页，确认真的能用。"""
    import requests
    from lxml import etree

    raw = COOKIE_FILE.read_text(encoding="utf-8").strip()
    jar = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            jar[k.strip()] = v.strip()

    r = requests.get(LIST_URL, cookies=jar, headers={"user-agent": UA}, timeout=20)
    n = len(etree.HTML(r.text).xpath('//li[@data-rid]'))
    print(f"验证请求：status={r.status_code} len={len(r.text)} 书籍数={n}")
    return n > 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headful", action="store_true", help="有头模式，无头被识别成机器人时改用")
    ap.add_argument("--timeout", type=int, default=40, help="等待页面渲染的秒数")
    ap.add_argument("--check", action="store_true", help="取完 cookie 后立刻验证是否可用")
    ap.add_argument("--browser", default="edge",
                    help="用哪个浏览器取 cookie：edge（默认）/ chrome / auto")
    ap.add_argument("--edgedriver", default=None,
                    help="msedgedriver.exe 的路径，不指定则用 cookie_refresher 里的默认位置")
    args = ap.parse_args()

    raw = fetch_cookie(args.headful, args.timeout, args.browser, args.edgedriver)
    if not raw:
        print("未取到任何 cookie", file=sys.stderr)
        return 1

    save_cookie_str(raw)
    print(f"已写入 {COOKIE_FILE}（{len(raw)} 字符）")

    if args.check:
        ok = check()
        print("通过" if ok else "失败：新 cookie 仍然被拦截，试试 --headful")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
