from scrapy.cmdline import execute
from datetime import datetime
if __name__ == '__main__':
    time1 =datetime.now()
    #可以加-s MAX_PAGE=3，意思是只爬取3页
    execute("scrapy crawl xiaoshuos -s COOKIE_MAX_REFRESH=30000 -s JOBDIR=crawls/qidian-1".split())
    time2 = datetime.now()
    print(time2-time1)

