# Scrapy settings for qidian2 project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "qidian2"

SPIDER_MODULES = ["qidian2.spiders"]
NEWSPIDER_MODULE = "qidian2.spiders"


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "qidian2 (+http://www.yourdomain.com)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = False
LOG_LEVEL = "WARNING"
# Configure maximum concurrent requests performed by Scrapy (default: 16)
#CONCURRENT_REQUESTS = 32

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
#DOWNLOAD_DELAY = 3
# The download delay setting will honor only one of:
#CONCURRENT_REQUESTS_PER_DOMAIN = 16
#CONCURRENT_REQUESTS_PER_IP = 16

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
# ---------- 全量抓取（50 页）相关配置 ----------

# 免费榜总页数；命令行可临时覆盖：-s MAX_PAGE=10
MAX_PAGE = 50

# 全量 50 页 ≈ 1000 本书 ≈ 4 万个请求，DOWNLOAD_DELAY 是吞吐的瓶颈
#（实测 delay=2 时约 0.45 req/s，跑完要 25 小时）。
# 这里用「自动限速」代替固定延时：站点响应变慢会自动退让，比写死延时更安全。
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 4
DOWNLOAD_DELAY = 0.3
RANDOMIZE_DOWNLOAD_DELAY = True

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 20
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

# 被 WAF 拦截后的重试与停爬阈值（见 spider 的 on_blocked）
BLOCK_RETRY_TIMES = 2
BLOCK_ABORT_LIMIT = 10

# 断点续爬：把请求队列存盘，中断后用完全相同的命令即可接着跑
#   scrapy crawl xiaoshuos -s JOBDIR=crawls/qidian-1
# 注意：同一个 JOBDIR 不能用于中途更换参数的重跑，换参数请换目录名。

DEFAULT_REQUEST_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "connection": "keep-alive",
    "referer": "https://www.qidian.com/free/",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0"
}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "qidian2.middlewares.Qidian2SpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
# 750 必须大于 CookiesMiddleware 的 700，保证我们写的 Cookie 头最后生效
DOWNLOADER_MIDDLEWARES = {
    "qidian2.middlewares.QidianCookieMiddleware": 750,
}

# ---------- cookie 自动续命 ----------
# 被 WAF 拦截时自动启动本机 Chrome 换一张 cookie（由 Selenium 跑完 probe.js）
COOKIE_AUTO_REFRESH = True      # 关掉则退回「只用 cookie.txt 里的静态 cookie」
COOKIE_MAX_REFRESH = 10         # 一次爬取最多自动刷新几次
COOKIE_REFRESH_INTERVAL = 60    # 两次刷新之间的最小间隔（秒）
COOKIE_REFRESH_TIMEOUT = 40     # 等待 Chrome 页面渲染的秒数
COOKIE_HEADFUL = False          # 无头被识别成机器人时改成 True

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
   "qidian2.pipelines.Qidian2Pipeline": 300,
}

# 小说保存目录（相对路径基于项目根目录；绝对路径则直接使用）
BOOKS_STORE = "books"

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
