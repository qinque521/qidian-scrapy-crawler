# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

import threading
import time

from scrapy import signals
from scrapy.exceptions import NotConfigured
from twisted.internet import threads

# useful for handling different item types with a single interface
from itemadapter import is_item, ItemAdapter

from qidian2.cookie_refresher import fetch_cookie, load_cookie_str, save_cookie_str
from qidian2.spiders.xiaoshuos import is_blocked


class Qidian2SpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    def process_start_requests(self, start_requests, spider):
        # Called with the start requests of the spider, and works
        # similarly to the process_spider_output() method, except
        # that it doesn’t have a response associated.

        # Must return only requests (not items).
        for r in start_requests:
            yield r

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class Qidian2DownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class QidianCookieMiddleware:
    """自动管理起点 cookie：请求时注入，被 WAF 拦截时自动开 Chrome 换一张。

    为什么绕开 Scrapy 自带的 cookiejar：CookiesMiddleware 处理 cookies= 传入的
    cookie 时，构造出的 cookie 没有 domain，会被 http.cookiejar 以「无内嵌点的
    非本地域」为由静默丢弃（这就是之前"共找到 0 章"的根因）。这里改为直接写
    Cookie 请求头，并把 order 排在 CookiesMiddleware(700) 之后，同时置
    dont_merge_cookies，确保我们写好的头不会被覆盖。
    """

    RETRY_KEY = "cookie_refresh_retries"

    def __init__(self, max_refresh, headful, timeout, min_interval,
                 browser="auto", edgedriver=None):
        self.max_refresh = max_refresh
        self.headful = headful
        self.timeout = timeout
        self.min_interval = min_interval
        self.browser = browser
        self.edgedriver = edgedriver or None

        self.cookie_raw = load_cookie_str()
        self.refresh_count = 0
        self._refreshing = False
        self._last_refresh = 0.0
        self._lock = threading.Lock()

    @classmethod
    def from_crawler(cls, crawler):
        s = crawler.settings
        if not s.getbool("COOKIE_AUTO_REFRESH", True):
            raise NotConfigured
        return cls(
            max_refresh=s.getint("COOKIE_MAX_REFRESH", 10),
            headful=s.getbool("COOKIE_HEADFUL", False),
            timeout=s.getint("COOKIE_REFRESH_TIMEOUT", 40),
            min_interval=s.getfloat("COOKIE_REFRESH_INTERVAL", 60),
            browser=s.get("COOKIE_BROWSER", "auto"),
            edgedriver=s.get("COOKIE_EDGEDRIVER") or None,
        )

    def _is_qidian(self, request):
        return "qidian.com" in request.url

    def process_request(self, request, spider):
        if not self._is_qidian(request):
            return
        # cookie 由本中间件统一管理，别让 CookiesMiddleware 插手
        request.meta["dont_merge_cookies"] = True
        if self.cookie_raw:
            request.headers["Cookie"] = self.cookie_raw

    def process_response(self, request, response, spider):
        if not self._is_qidian(request) or not is_blocked(response):
            return response

        # Selenium 会阻塞，必须丢到线程池，否则卡死 Twisted 的 reactor
        d = threads.deferToThread(self._wait_and_refresh, spider)
        d.addCallback(lambda ok: self._decide(request, response, spider, ok))
        return d

    def _decide(self, request, response, spider, refreshed):
        """决定是否用新 cookie 重试这个请求。"""
        if not refreshed:
            return response  # 刷新失败或已达上限，交回 spider 的放弃逻辑

        retries = request.meta.get(self.RETRY_KEY, 0)
        if retries >= 2:
            spider.logger.error(f"换过 cookie 仍被拦截，放弃：{request.url}")
            return response

        spider.logger.warning(f"已换到新 cookie，重试第 {retries + 1} 次：{request.url}")
        return request.replace(
            dont_filter=True,
            meta={**request.meta, self.RETRY_KEY: retries + 1},
        )

    def _wait_and_refresh(self, spider):
        """刷新 cookie。若其它线程正在刷新、或距上次刷新太近，先等一会儿。"""
        deadline = time.time() + self.timeout + 120

        while True:
            with self._lock:
                if not self._refreshing:
                    if self.refresh_count >= self.max_refresh:
                        spider.logger.error(
                            f"cookie 刷新已达上限 {self.max_refresh} 次，停止自动续命"
                        )
                        return False
                    wait = self.min_interval - (time.time() - self._last_refresh)
                    if wait <= 0:
                        self._refreshing = True
                        break
                else:
                    wait = 1.0

            if time.time() + wait > deadline:
                spider.logger.error("等待刷新 cookie 超时")
                return False
            time.sleep(min(max(wait, 0.5), 5))

        try:
            spider.logger.warning(
                f"检测到 WAF 拦截，启动 Chrome 刷新 cookie"
                f"（第 {self.refresh_count + 1}/{self.max_refresh} 次）"
            )
            raw = fetch_cookie(self.headful, self.timeout, self.browser, self.edgedriver)
            if not raw:
                return False

            with self._lock:
                self.cookie_raw = raw
                self.refresh_count += 1
                self._last_refresh = time.time()
            save_cookie_str(raw)
            spider.logger.warning("cookie 刷新完成，继续爬取")
            return True
        except Exception as exc:
            spider.logger.error(
                f"刷新 cookie 失败（Selenium 或本机 Chrome 不可用？）：{exc}"
            )
            return False
        finally:
            with self._lock:
                self._refreshing = False
