import re
from pathlib import Path

from itemadapter import ItemAdapter


# 项目根目录（pipelines.py 在 qidian2/ 下，所以取上两级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Windows 文件名非法字符
INVALID_CHARS = r'[\\/:*?"<>|\r\n\t]'
# 单个文件/文件夹名的最大长度，给完整路径留足余量（Windows 上限 260）
MAX_NAME_LEN = 80


def safe_name(name: str, default: str) -> str:
    """把书名/章节名清理成合法的 Windows 文件名。"""
    name = re.sub(INVALID_CHARS, "_", str(name or "")).strip()
    name = re.sub(r"\s+", " ", name)
    # Windows 不允许文件或文件夹名以空格或点结尾
    name = name.strip(" .")
    name = name[:MAX_NAME_LEN].strip(" .")
    return name or default


class Qidian2Pipeline:
    """每本书建一个文件夹（书名为名），每章存成一个 txt（章节名为名）。"""

    def __init__(self, store: str):
        path = Path(store)
        self.store = path if path.is_absolute() else PROJECT_ROOT / path
        self.saved = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("BOOKS_STORE", "books"))

    def open_spider(self, spider):
        self.store.mkdir(parents=True, exist_ok=True)
        spider.logger.info(f"小说保存目录：{self.store}")

    def close_spider(self, spider):
        spider.logger.info(f"共保存 {self.saved} 个章节 txt，目录：{self.store}")

    def process_item(self, item, spider):
        a = ItemAdapter(item)

        book = safe_name(a.get("book"), "未命名")
        chapter = safe_name(a.get("chapter"), "无标题")
        content = a.get("content") or ""

        book_dir = self.store / book
        book_dir.mkdir(parents=True, exist_ok=True)

        # 章节重名时加序号，避免互相覆盖
        path = book_dir / f"{chapter}.txt"
        if path.exists():
            i = 2
            while True:
                candidate = book_dir / f"{chapter}({i}).txt"
                if not candidate.exists():
                    path = candidate
                    break
                i += 1

        path.write_text(content, encoding="utf-8")
        self.saved += 1
        return item
