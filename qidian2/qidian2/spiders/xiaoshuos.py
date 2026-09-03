import os
from pathlib import Path

import scrapy
from lxml import etree
from scrapy.exceptions import CloseSpider

COOKIE_FILE = Path(__file__).resolve().parent.parent / "cookie.txt"


def load_cookie() -> list:
    """读取 cookie.txt 里的原始 Cookie 字符串，转成 Scrapy 需要的格式。

    一般不需要手工维护这个文件：爬虫被 WAF 拦截时会由 QidianCookieMiddleware
    自动开 Chrome 取一张新 cookie 写回来。需要手工干预时，用
    `python refresh_cookie.py` 或浏览器复制后覆盖写入。也可以设环境变量
    QIDIAN_COOKIE 覆盖。

    注意：必须返回「带 domain 的 dict 列表」，不能返回 {name: value} 字典。
    Scrapy 底层用 http.cookiejar，纯字典形式的 cookie 没有 domain 字段，
    会被判定为「无内嵌点的非本地域」而静默丢弃，导致后续请求不带 cookie，
    起点 WAF 随即返回 202 人机校验页（正文为空，xpath 全部匹配不到）。
    """
    try:
        file_cookie = COOKIE_FILE.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        file_cookie = ""  # 没有 cookie 文件也没关系，中间件会自动开浏览器取一张

    raw = os.environ.get("QIDIAN_COOKIE") or file_cookie

    cookies = []
    for part in raw.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)  # 只切第一个等号，cookie 值里常带 = 和 /
        cookies.append({
            "name": k.strip(),
            "value": v.strip(),
            "domain": ".qidian.com",
            "path": "/",
        })
    return cookies


def is_blocked(response) -> bool:
    """判断响应是否是起点 WAF 的拦截页（而不是正常内容页）。

    实测到的三种形态，共同点是「几乎没有正文」：
    1) HTTP 202 + 209 字节空页面，内含 /C2WF946J0/probe.js（JS 挑战，最常见）
    2) HTTP 200 + 约 1.7KB 空页面，内含 seqid ... __captcha（腾讯验证码）
    3) 其它被折叠的短页面
    正常页面一般 40KB 以上（列表页约 95KB、书籍页约 50KB、章节页约 47KB）。
    """
    head = response.text[:2000]
    return (
        response.status == 202
        or "probe.js" in head
        or "__captcha" in head
        or len(response.text) < 10000
    )


class XiaoshuosSpider(scrapy.Spider):
    name = "xiaoshuos"
    allowed_domains = ["qidian.com"]

    # 起点免费榜列表页基础地址；第 1 页无 page 后缀，第 2 页起为 page{N}
    BASE_URL = "https://www.qidian.com/free/all/"
    start_urls = [BASE_URL]

    BLOCK_RETRY_KEY = "block_retries"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.blocked_total = 0

    def _setting(self, key, default):
        """读取设置；离线直接实例化 spider 时 self.settings 不存在，用默认值兜底。"""
        settings = getattr(self, "settings", None)
        return settings.getint(key, default) if settings else default

    def on_blocked(self, response, what):
        """被 WAF 拦截时的统一处理：有限重试，累计过多就安全停爬。

        Scrapy 的 download_delay 在 slot 创建时就固定了，没法按请求做退避，
        所以这里靠「低优先级重排到队尾 + 限制重试次数」避免雪上加霜。
        短时间内大量被拦通常意味着已触发 IP 限流，继续硬请求只会让封禁更久，
        不如直接停爬保住 JOBDIR 进度，换个时段再续跑。
        """
        self.blocked_total += 1
        retries = response.meta.get(self.BLOCK_RETRY_KEY, 0)
        max_retries = self._setting("BLOCK_RETRY_TIMES", 2)
        abort_limit = self._setting("BLOCK_ABORT_LIMIT", 10)

        if retries < max_retries:
            self.logger.warning(
                f"{what}被 WAF 拦截，安排第 {retries + 1}/{max_retries} 次重试：{response.url}"
            )
            req = response.request.replace(
                dont_filter=True,
                meta={**response.meta, self.BLOCK_RETRY_KEY: retries + 1},
            )
            req.priority = -100  # 排到队尾，把带宽让给其它请求
            return req

        self.logger.error(f"{what}被 WAF 拦截且重试已用尽，放弃：{response.url}")
        if self.blocked_total >= abort_limit:
            raise CloseSpider(
                f"累计 {self.blocked_total} 次被 WAF 拦截，已安全停止。"
                f"请换时段用同一条命令续跑："
                f"scrapy crawl xiaoshuos -s JOBDIR=crawls/qidian-1"
            )
        return None

    def start_requests(self):
        cookies = load_cookie()

        # 总页数上限，可在 settings.py 里用 MAX_PAGE 调整，
        # 也可以命令行临时覆盖：-s MAX_PAGE=10
        max_page = self.settings.getint("MAX_PAGE", 50)
        print(f"开始抓取列表页，共 {max_page} 页")

        for page in range(1, max_page + 1):
            url = self.BASE_URL if page == 1 else f"{self.BASE_URL}page{page}/"
            yield scrapy.Request(
                url=url,
                cookies=cookies,
                meta={"page": page, "max_page": max_page},
            )

    def parse(self, response):
        page = response.meta.get("page", 1)
        max_page = response.meta.get("max_page", 1)

        if is_blocked(response):
            req = self.on_blocked(response, f"列表页第 {page} 页")
            if req:
                yield req
            return

        html = etree.HTML(response.text)

        # 直接定位到每本书的 li（data-rid 是每本书的序号）
        books = html.xpath('//li[@data-rid]')
        print(f"第 {page}/{max_page} 页：共找到 {len(books)} 本书")

        for book in books:
            book_title = book.xpath('.//h2/a/text()')
            book_title = book_title[0].strip() if book_title else "无标题"

            image_ = book.xpath('.//div[@class="book-img-box"]//img/@src')
            image_src = 'https:' + image_[0] if image_ else ""

            author = book.xpath('.//p[@class="author"]/a[@class="name"]/text()')
            author = author[0].strip() if author else "未知作者"

            book_url = book.xpath('.//div[@class="book-img-box"]/a/@href')
            if not book_url:
                self.logger.warning(f"跳过《{book_title}》：未取到书籍链接")
                continue
            book_url = 'https:' + book_url[0].strip()

            yield scrapy.Request(
                url=book_url,
                callback=self.get_chapter,
                headers={"Referer": response.url},
                meta={"book_title": book_title, "author": author},
            )

    def get_chapter(self, response):
        if is_blocked(response):
            req = self.on_blocked(response, f"《{response.meta.get('book_title')}》目录页")
            if req:
                yield req
            return

        a = etree.HTML(response.text)

        # 关键修正：ul[@class="volume-chapters"] 是「卷」，不是「章」。
        # 原写法拿到的是卷的列表，再取 [0] 就每卷只剩第一章。
        # 正确做法：直接取所有卷下 li.chapter-item 里的章节链接。
        chapter_links = a.xpath(
            '//ul[contains(@class, "volume-chapters")]/li[contains(@class, "chapter-item")]'
            '//a[contains(@class, "chapter-name")]'
        )
        print(f"《{response.meta['book_title']}》共找到 {len(chapter_links)} 章")

        for link in chapter_links:
            chapter_title = (link.xpath('string()').strip() or "无标题")

            chapter_href = link.xpath('./@href')
            if not chapter_href:
                continue
            chapter_url = 'https:' + chapter_href[0].strip()

            yield scrapy.Request(
                url=chapter_url,
                headers={"Referer": response.url},
                callback=self.chapter_parse,
                meta={
                    "book_title": response.meta["book_title"],
                    "author": response.meta["author"],
                    "chapter_title": chapter_title,  # 原来传的是 list，这里改回 str
                },
            )

    def chapter_parse(self, response):
        if is_blocked(response):
            req = self.on_blocked(response, f"章节《{response.meta.get('chapter_title')}》")
            if req:
                yield req
            return

        content = response.css("main").xpath("string()").get() or ""
        content = content.strip()

        yield {
            "book": response.meta["book_title"],
            "author": response.meta["author"],
            "chapter": response.meta["chapter_title"],
            "url": response.url,
            "content": content,
        }
