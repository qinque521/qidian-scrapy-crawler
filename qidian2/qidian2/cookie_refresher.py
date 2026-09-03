"""用本机浏览器打开起点，让 WAF 的 JS 挑战自然跑完，取回可用的 cookie。

背景：起点 WAF 拦截时返回一段 probe.js，要求客户端执行 JS 才能拿到合法 cookie。
requests / Scrapy 不执行 JS，所以永远过不去；真浏览器可以。取到 cookie 后再交给
Scrapy 用，被封的会话就换成了新的。

支持 Chrome 与 Edge（同为 Chromium 内核，参数通用），browser="auto" 时依次尝试。
"""

import os
import time
from pathlib import Path
from typing import List

COOKIE_FILE = Path(__file__).resolve().parent / "cookie.txt"
LIST_URL = "https://www.qidian.com/free/all/"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

# 手动下载的 msedgedriver 位置；不存在或留空则交给 Selenium Manager 自动解析
DEFAULT_EDGEDRIVER = r"./edgedriver_win64 (1)/msedgedriver.exe"  #需要替换成你自己浏览器对应的edgedriver版本
#edgedriver下载地址：https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/?form=MA13LH&cs=3114783079
BROWSER_ALIASES = {
    "chrome": "chrome", "google chrome": "chrome", "google": "chrome",
    "edge": "edge", "microsoft edge": "edge", "msedge": "edge",
}


def normalize_browser(name) -> str:
    """把浏览器名归一化成 chrome / edge / auto；auto 表示依次尝试。"""
    key = (name or "auto").strip().lower()
    if key in ("auto", ""):
        return "auto"
    if key in BROWSER_ALIASES:
        return BROWSER_ALIASES[key]
    raise ValueError(f"不支持的浏览器 {name!r}，可选：auto / chrome / edge")


def _build_options(headful: bool, browser: str):
    if browser == "edge":
        from selenium.webdriver.edge.options import Options
    else:
        from selenium.webdriver.chrome.options import Options

    opts = Options()
    if not headful:
        opts.add_argument("--headless=new")
    opts.add_argument(f"--user-agent={UA}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1440,900")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return opts


def _open_driver(browser: str, headful: bool, edgedriver=None):
    from selenium import webdriver

    opts = _build_options(headful, browser)
    if browser != "edge":
        return webdriver.Chrome(options=opts)

    path = edgedriver or os.environ.get("EDGEDRIVER_PATH") or DEFAULT_EDGEDRIVER
    if path and Path(path).exists():
        from selenium.webdriver.edge.service import Service
        return webdriver.Edge(options=opts, service=Service(path))
    # 没指定驱动就让 Selenium Manager 自己找，前提是它所在环境能联网下载
    return webdriver.Edge(options=opts)


def _grab_cookies(driver, timeout: int) -> list:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    # 抹掉最容易被识别的 navigator.webdriver 标记
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    })
    driver.get(LIST_URL)

    # 关键是等「真正的书列表」出现，而不是拿到空壳页就返回
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "li[data-rid]"))
    )
    books = driver.find_elements(By.CSS_SELECTOR, "li[data-rid]")
    print(f"页面已正常加载，检测到 {len(books)} 本书")
    time.sleep(2)  # 给 probe.js 一点时间把 cookie 全部写完
    return driver.get_cookies()


def fetch_cookie(headful: bool = False, timeout: int = 40,
                 browser: str = "auto", edgedriver=None) -> str:
    """启动本机浏览器，等书籍列表真正渲染出来后导出 cookie 字符串。

    browser: "auto"（先 Chrome 后 Edge）/ "chrome" / "edge"，
             也可由 settings.py 的 COOKIE_BROWSER 指定。
    headful: False 时用 --headless=new；无头被识别成机器人时改 True。
    edgedriver: msedgedriver.exe 的路径，不传则用 DEFAULT_EDGEDRIVER，
                再找不到就让 Selenium Manager 自动解析。
    """
    wanted = normalize_browser(browser)
    order = ["chrome", "edge"] if wanted == "auto" else [wanted]
    errors = []

    for name in order:
        driver = None
        try:
            driver = _open_driver(name, headful, edgedriver)
            cookies = _grab_cookies(driver, timeout)
            print(f"已用 {name} 取到 cookie（{len(cookies)} 条）")
            return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {str(exc).splitlines()[0][:160]}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    raise RuntimeError("自动刷新 cookie 失败 → " + " ｜ ".join(errors))


def load_cookie_str(path: Path = COOKIE_FILE) -> str:
    """读取现有的 cookie 字符串；文件不存在或为空时返回空串，交给自动刷新兜底。"""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return ""


def save_cookie_str(raw: str, path: Path = COOKIE_FILE) -> None:
    """把 cookie 字符串写回文件，便于人工查看和下次启动复用。"""
    path.write_text(raw, encoding="utf-8")


def cookie_dicts(raw: str) -> List[dict]:
    """把 cookie 字符串转成 Scrapy 需要的、带 domain 的 dict 列表。

    必须带 domain，否则 http.cookiejar 会以「无内嵌点的非本地域」为由静默丢弃。
    """
    out = []
    for part in raw.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out.append({"name": k.strip(), "value": v.strip(),
                    "domain": ".qidian.com", "path": "/"})
    return out
