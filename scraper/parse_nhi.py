"""健保署網頁解析器。

解析 www.nhi.gov.tw 的三種頁面：
- lp-*.html 列表頁（如 lp-3258 法規公告）：表格列出主旨/發文字號/發文日期/刊登日期/刊登期限
- cp-*.html 內容頁：內文 + 「檔案下載」附件區（section.fileDownload）
- np-*.html 節點頁：子頁連結列表

同時支援 Wayback Machine 存檔頁（自動還原 /web/<timestamp>/ 前綴的原始網址）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from bs4 import BeautifulSoup

BASE_URL = "https://www.nhi.gov.tw"

_WAYBACK_RE = re.compile(r"^(?:https?://web\.archive\.org)?/web/(\d{4,17})(?:im_|if_|js_|cs_)?/(https?://.*)$")


def normalize_url(href: str, base: str = BASE_URL + "/ch/") -> str:
    """還原 Wayback 前綴並把相對路徑轉為 nhi.gov.tw 絕對網址。"""
    href = (href or "").strip()
    if not href:
        return ""
    m = _WAYBACK_RE.match(href)
    if m:
        return m.group(2)
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return base + href


def roc_date_to_iso(text: str) -> str | None:
    """民國日期（115-07-15、114.12.01、113/04/03）轉 ISO 西元日期。"""
    if not text:
        return None
    m = re.search(r"(\d{2,3})[-./](\d{1,2})[-./](\d{1,2})", text)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 200:  # 民國年
        y += 1911
    try:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    except ValueError:
        return None


@dataclass
class Announcement:
    """法規公告列表中的一筆公告。"""

    title: str
    url: str
    doc_no: str  # 發文字號
    issued_date: str | None  # 發文日期 (ISO)
    published_date: str | None  # 刊登日期 (ISO)
    expiry_date: str | None  # 刊登期限 (ISO)
    issued_date_roc: str = ""  # 原始民國日期字串
    source: str = "live"  # live 或 wayback:<timestamp>

    def key(self) -> str:
        """去重用鍵值：優先用內容頁網址，其次發文字號。"""
        m = re.search(r"/ch/(cp-\d+-[0-9a-f]+-\d+-\d+)\.html", self.url)
        if m:
            return m.group(1)
        return re.sub(r"[。\s]", "", self.doc_no) or self.title


@dataclass
class AttachmentFile:
    file_type: str  # pdf / doc / docx / odt / xls ...
    url: str
    title: str = ""
    size: str = ""


@dataclass
class DownloadItem:
    """「檔案下載」區的一個項目（例如一個章節或一個年度版本）。"""

    name: str
    files: list[AttachmentFile] = field(default_factory=list)


def parse_list_page(html: str, source: str = "live") -> tuple[list[Announcement], dict]:
    """解析 lp- 列表頁，回傳 (公告列表, 分頁資訊)。"""
    soup = BeautifulSoup(html, "html.parser")
    results: list[Announcement] = []

    table = soup.select_one("section.list table")
    if table is not None:
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            link = cells[1].find("a")
            title = link.get_text(strip=True) if link else cells[1].get_text(strip=True)
            url = normalize_url(link.get("href", "")) if link else ""
            doc_no = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            issued_roc = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            published_roc = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            expiry_roc = cells[5].get_text(strip=True) if len(cells) > 5 else ""
            results.append(
                Announcement(
                    title=title,
                    url=url,
                    doc_no=doc_no,
                    issued_date=roc_date_to_iso(issued_roc),
                    published_date=roc_date_to_iso(published_roc),
                    expiry_date=roc_date_to_iso(expiry_roc),
                    issued_date_roc=issued_roc,
                    source=source,
                )
            )

    pagination: dict = {}
    total = soup.select_one("section.pagination .total")
    if total:
        m = re.search(r"共\s*(\d+)\s*筆", total.get_text())
        if m:
            pagination["total_items"] = int(m.group(1))
        m = re.search(r"第\s*(\d+)\s*/\s*(\d+)\s*頁", total.get_text())
        if m:
            pagination["page"] = int(m.group(1))
            pagination["total_pages"] = int(m.group(2))
    return results, pagination


def parse_download_sections(html: str) -> list[DownloadItem]:
    """解析 cp- 內容頁的「檔案下載」區（章節附件、歷史檔等）。"""
    soup = BeautifulSoup(html, "html.parser")
    items: list[DownloadItem] = []
    for section in soup.select("section.fileDownload"):
        for li in section.select(":scope > ul > li"):
            name_el = li.select_one("span.fileName")
            if name_el is None:
                continue
            item = DownloadItem(name=name_el.get_text(strip=True))
            for file_li in li.select("ol.downloadFiles > li"):
                a = file_li.find("a")
                if a is None:
                    continue
                ftype_el = file_li.select_one("span.fileType")
                size_el = file_li.select_one("div.fileSize")
                item.files.append(
                    AttachmentFile(
                        file_type=(ftype_el.get_text(strip=True) if ftype_el else "").lower(),
                        url=normalize_url(a.get("href", "")),
                        title=a.get("title", ""),
                        size=size_el.get_text(strip=True) if size_el else "",
                    )
                )
            items.append(item)
    return items


def parse_content_page(html: str) -> dict:
    """解析 cp- 內容頁：標題、發布/更新日期、內文、附件。"""
    soup = BeautifulSoup(html, "html.parser")
    header = soup.select_one(".pageHeader h2")
    article = soup.select_one("article.cpArticle")

    dates = {}
    for label in ("發布日期", "更新日期", "發布單位"):
        el = soup.find(string=re.compile(label))
        if el:
            value = el.find_parent().get_text(strip=True).replace(label, "").strip("：: ")
            dates[label] = value

    return {
        "title": header.get_text(strip=True) if header else "",
        "meta": dates,
        "body_text": article.get_text("\n", strip=True) if article else "",
        "downloads": [asdict(d) for d in parse_download_sections(html)],
    }


def parse_node_page(html: str) -> list[dict]:
    """解析 np- 節點頁的子頁連結。"""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select(".contentbox section.np a, .contentbox section a"):
        href = a.get("href", "")
        if "javascript:" in href:
            continue
        links.append({"title": a.get_text(strip=True), "url": normalize_url(href)})
    return links


def is_drug_rule_announcement(title: str) -> bool:
    """判斷公告是否與藥品給付規定相關。"""
    keywords = ("藥品給付規定", "給付規定", "暫予支付", "藥物給付項目及支付標準")
    return any(k in title for k in keywords)
