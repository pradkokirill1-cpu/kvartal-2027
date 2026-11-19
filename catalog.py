"""Collect public developer pages; keep each feed isolated and fail closed."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "public" / "snapshot.js"
CURATED = ROOT / "curated.json"
CACHE = ROOT / ".catalog-cache.json"
MIN_DUE = 20264
CUTOFF = 20280
MINSK = ZoneInfo("Europe/Minsk")
ZEL = "https://zelgavan.by/realty-type/cityhouse"
GRAND = "https://grand-village.by/houses/"
NOVA = "https://newbor.by/genplan/"
GRAND_TERMS = "https://www.dolevoe.by/novostroyki/zhk-grand-villadzh.html"
NOVA_TERMS = "https://prometr.by/newbuild/doma-5-6-kvartal-park-v-sostave-zhk-novaya-borovaya/dom-14-4-avia-kvartal_1640/"
ZEL_TERMS = "https://realt.by/sale-flats/object/4274386/"

class SourceRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlparse(req.full_url), urlparse(newurl)
        if new.scheme != "https" or old.netloc != new.netloc:
            raise ValueError("Cross-domain redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def stamp():
    return datetime.now(MINSK).isoformat(timespec="seconds")


def norm(value):
    return " ".join(value.split())


def tx(node, selector=None):
    found = node.select_one(selector) if node is not None and selector else node
    return norm(found.get_text(" ", strip=True)) if found else ""


def soup(url):
    with build_opener(SourceRedirect()).open(Request(url, headers={"User-Agent": "Kvartal2027 catalog (+public listing reference)"}), timeout=9) as response:
        if urlparse(response.url).hostname != urlparse(url).hostname:
            raise ValueError("Cross-domain redirect")
        html = response.read(3_000_001)
        if len(html) > 3_000_000:
            raise ValueError("Page too large")
    return BeautifulSoup(html, "html.parser")


def href(node, base, prefix):
    raw = node.get("href", "") if node else ""
    url = urljoin(base, raw)
    parsed = urlparse(url)
    if (parsed.scheme == "https" and parsed.netloc == urlparse(base).netloc
            and parsed.path.startswith(prefix) and not parsed.query and not parsed.fragment):
        return url
    raise ValueError("Unexpected listing URL")


def due(value):
    match = re.search(r"\b([1-4])\s+квартал\w*\s+(20\d{2})\b", value.lower())
    if not match:
        return None
    return int(match[2]) * 10 + int(match[1])


def eligible(value):
    now = datetime.now(MINSK)
    min_due = max(MIN_DUE, now.year * 10 + (now.month - 1) // 3 + 1)
    return value is not None and min_due <= value < CUTOFF


def number(value):
    return int(re.sub(r"\s", "", value))


def available(value):
    match = re.search(r"(\d+)\s+квартир", value)
    return int(match[1]) if match else None


def record(feed, url, project, name, address, deadline, builder, role, price=None, currency=None, stock=None):
    return dict(id=url, feed=feed, zone="district", project=project, name=name, address=address,
                due=deadline, when=f"{deadline % 10} квартал {deadline // 10}",
                builder=builder, role=role, price=price, currency=currency,
                priceKind="from", stock=stock, rooms=[], area=None, layout=None,
                payment=None, note=None, url=url, sources=[])


def details(url):
    return soup(url)


def extract_layout(row, description):
    description = norm(description)
    room = re.search(r"(?:от\s+)?([1-6])(?:\s*[-–]\s*|\s+до\s+)([1-6])\s+комнат", description, re.I)
    if room and int(room[1]) <= int(room[2]):
        row["rooms"] = list(range(int(room[1]), int(room[2]) + 1))
    elif re.search(r"евро[- ]?двушек.{0,70}пятикомнат", description, re.I):
        row["rooms"] = [2, 3, 4, 5]
    elif re.search(r"однокомнатных.{0,70}четыр[её]хкомнат", description, re.I):
        row["rooms"] = [1, 2, 3, 4]
    area = re.search(r"(?:площад[ьи]\w*\s+)?(?:от\s+)?(\d{2,3}(?:[.,]\d+)?)\s*(?:до|[-–—])\s*(\d{2,3}(?:[.,]\d+)?)\s*(?:м\s*[²2]|кв\.\s*м)", description, re.I)
    if area:
        row["area"] = f"{area[1].replace('.', ',')}–{area[2].replace('.', ',')} м²"
    if row["rooms"] or row["area"]:
        row["layout"] = "Проектный ассортимент. Свободные квартиры и поэтажные планы смотрите в витрине дома."


def parse_zel(page):
    out = []
    cards = page.select("a.b-card-house")
    if not cards or not any(due(tx(x)) for x in cards):
        raise ValueError("Listing structure changed")
    for card in cards:
        fields = {}
        for item in card.select(".b-info-house__item"):
            fields[tx(item, "span:first-child")] = tx(item, "span:last-child")
        deadline = due(fields.get("Дата сдачи:", ""))
        if not eligible(deadline):
            continue
        name = tx(card, ".b-card-house__title")
        if not name:
            raise ValueError("Missing building name")
        url = href(card, ZEL, "/house-type/")
        match = re.search(r"от\s+([\d\s]+)\s*\$", tx(card, ".b-label-title"))
        out.append(record("zel", url, "Зелёная гавань", name,
                          f"аг. Колодищи, {fields.get('Квартал:', 'ЖК «Зелёная гавань»')}", deadline,
                          "ООО «Зеленая гавань» / А-100 Девелопмент", "Юрлицо проекта / девелопер",
                          number(match[1]) if match else None, "USD" if match else None,
                          available(fields.get("Доступно:", ""))))
    return out


def enrich_zel(row):
    page = details(row["url"])
    if re.search(r"\b(?:дом сдан|введ[её]н в эксплуатацию)\b", tx(page, ".b-s-house-info"), re.I):
        return None
    if page:
        extract_layout(row, tx(page, ".b-side-categories-grid__content-inner"))
        if not row["area"]:
            extract_layout(row, (page.select_one('meta[name="description"]') or {}).get("content", ""))
    if row["name"] == "Ситихаус 7.16":
        row.update(rooms=[2, 3, 4], area="35,62–104,14 м²",
                   layout="Евроформат; в проекте есть мансарды, террасы, кабинеты и гардеробные. Доступность конкретных вариантов проверяйте по планам.",
                   payment="Опубликовано: до 6 месяцев при взносе от 70% без удорожания; до конца стройки или до 60 месяцев при взносе от 40%. Уточняйте цену при выбранной схеме.",
                   sources=[["Пример квартиры и рассрочка", ZEL_TERMS]])
    else:
        row["payment"] = "В проекте есть рассрочка и партнёрские кредиты. Условия для конкретной квартиры уточняйте у застройщика."
        row["sources"] = [["Условия покупки в проекте", "https://zelgavan.by/"]]
    return row


GRAND_LAYOUTS = {
    "Дом №2": ([2, 3], "62,49–81,79 м²", "2-комн. 62,49 м²; 3-комн. 81,70–81,79 м²."),
    "Дом №3": ([1, 2, 3], "40,99–81,70 м²", "1-комн. 40,99–43,03 м²; 2-комн. 62,09–63,78 м²; 3-комн. 81,70 м²."),
    "Дом №4": ([2, 3], "62,49–81,79 м²", "2-комн. 62,49 м²; 3-комн. 81,70–81,79 м². В проекте есть варианты с террасами."),
    "Дом №5": ([1, 2], "35–82 м²", "В опубликованной партии: 1-комн. 35 и 40–44 м²; 2-комн. 53–54, 62–64 и 81–82 м² (как указано в публикации)."),
    "Дом №12": ([1, 2, 3], "40,99–81,79 м²", "1-комн. 40,99–43,03 м²; 2-комн. 53,57–63,78 м²; 3-комн. 81,70–81,79 м²."),
}


def parse_grand(page):
    cards = page.select(".houses-sale__item")
    if not cards or not any(due(tx(x)) for x in cards):
        raise ValueError("Listing structure changed")
    out = []
    for card in cards:
        deadline = due(tx(card))
        if not eligible(deadline):
            continue
        url = href(card.select_one("a"), GRAND, "/dom-n")
        name = tx(card, ".houses-sale__info p")
        if not name:
            raise ValueError("Missing building name")
        out.append(record("grand", url, "Гранд Вилладж", name, "д. Тарасово, Минский район",
                          deadline, "ООО «Реторсия Трейд»", "Застройщик"))
    return out


def enrich_grand(row):
    page = details(row["url"])
    if page:
        floors = {a.get("href"): tx(el) for el in page.select(".info-floor")
                  if (a := el.select_one('a[href*="/etazh-"]'))}
        if not floors:
            raise ValueError("Building floor plans missing")
        matches = [number(m[1]) for value in floors.values()
                   if (m := re.search(r"от\s+([\d\s]+)\s+BYN\s+за", value))]
        stocks = [available(value.split("Доступно", 1)[1]) for value in floors.values() if "Доступно" in value]
        if matches:
            row.update(price=min(matches), currency="BYN")
        if stocks and all(x is not None for x in stocks):
            row["stock"] = sum(stocks)
    row["payment"] = "100% оплата; базовая рассрочка: взнос 50%, до 10 месяцев, +200 BYN/м²; партнёрский кредит."
    row["sources"] = [["Планировки и условия покупки", GRAND_TERMS]]
    if row["name"] in GRAND_LAYOUTS:
        row["rooms"], row["area"], layout = GRAND_LAYOUTS[row["name"]]
        row["layout"] = layout + " Это опубликованные примеры, не перечень свободных квартир."
    if row["name"] in ("Дом №2", "Дом №4"):
        row["payment"] += " Для отдельных лотов опубликована акция: 70% при заключении, до 4 месяцев без удорожания."
    if row["name"] in ("Дом №2", "Дом №3"):
        row["note"] = "Для части лотов обязательна покупка машино-места."
    if row["name"] == "Дом №5":
        row["note"] = "В опубликованной партии требовалась покупка машино-места."
        row["sources"].append(["Условия партии дома №5", "https://realt.by/news/article/46592/"])
    return row


def parse_nova(page, base):
    cards = [a for a in page.select("a.main-page__object") if "/dom_" in a.get("href", "")]
    if not cards or not any(due(tx(x)) for x in cards):
        raise ValueError("Listing structure changed")
    out = []
    for card in cards:
        name = tx(card, ".main-page__object_name")
        status = tx(card, ".main-page__object_status").lower()
        deadline = due(tx(card))
        if not eligible(deadline) or re.search(r"\b(?:сдан|сдано|введ[её]н)\b", status):
            continue
        url = href(card, base, "/genplan/")
        out.append(record("nova", url, "Новая Боровая", name,
                          f"д. Копище, {tx(card, '.main-page__object_location') or 'Минский район'}", deadline,
                          "А-100 Девелопмент", "Группа застройщика"))
    return out


def enrich_nova(row):
    page = details(row["url"])
    if page:
        labels = page.select(".banner-house__info-group .banner-house__info-label")
        if not labels:
            raise ValueError("Building details missing")
        if any(re.search(r"\bсдан[оа]?\b", tx(label), re.I) for label in labels[:3]):
            return None
        for label in labels[:3]:
            value = tx(label, "span")
            if "Стоимость" in tx(label) and (m := re.search(r"от\s+([\d\s]+)\s*\$", value)):
                row.update(price=number(m[1]), currency="USD")
            if "В продаже" in tx(label):
                row["stock"] = available(value)
        description = " ".join(tx(x) for x in page.select(".box-tab-slider__text-hide"))
        extract_layout(row, description)
        if not row["area"]:
            for indicator in page.select(".about-block__box-label"):
                if "площадь квартир" in tx(indicator).lower():
                    val = tx(indicator.parent, ".about-block__box-value")
                    if re.fullmatch(r"[\d.,]+\s*[-–]\s*[\d.,]+", val):
                        extract_layout(row, val + " м²")
    if row["name"] == "Дом 14.4":
        row.update(builder="«АСТОДЕВЕЛОПМЕНТ» / А-100 Девелопмент", role="Застройщик по карточке ProMetr",
                   rooms=[2, 3, 4, 5], area="35–115 м²",
                   layout="В проекте: от евродвушек до 5-комнатных. На первом этаже есть варианты с террасами; предусмотрены кладовые.",
                   payment="Рассрочка до конца строительства или до 60 месяцев: взнос от 40%, с увеличением стоимости метра.",
                   sources=[["Параметры дома и рассрочка", NOVA_TERMS],
                            ["Застройщик в карточке квартиры", "https://prometr.by/newbuild/novaya-borovaya/dom-14-4-avia-kvartal_1640/3-komnatnaya-67-64-43474/"]])
    else:
        row["payment"] = "В проекте доступны разные схемы оплаты. Взнос и график уточняйте по выбранной квартире."
    return row


def fetch_group(key):
    if key == "zel":
        rows, enrich = parse_zel(soup(ZEL)), enrich_zel
    elif key == "grand":
        rows, enrich = parse_grand(soup(GRAND)), enrich_grand
    else:
        rows = []
        for sub in ("avia_kvartal/", "art_kvartal/"):
            url = urljoin(NOVA, sub)
            rows += parse_nova(soup(url), url)
        enrich = enrich_nova
    if len(rows) > 30 or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Unexpected listing count or duplicate")
    with ThreadPoolExecutor(max_workers=4) as pool:
        return [r for r in pool.map(enrich, rows) if r is not None]


FEEDS = {"zel": ("Зелёная гавань", ZEL), "grand": ("Гранд Вилладж", GRAND), "nova": ("Новая Боровая", NOVA)}


def seed():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8").removeprefix("window.KVARTAL_SNAPSHOT=").removesuffix(";\n"))


def refresh(previous=None):
    previous = previous or {"rows": [], "feeds": []}
    start = stamp()
    listed = json.loads(CURATED.read_text(encoding="utf-8"))
    old_feeds = {f["id"]: f for f in previous["feeds"]}
    rows, states = list(listed), []
    with ThreadPoolExecutor(max_workers=3) as pool:
        requests = {key: pool.submit(fetch_group, key) for key in FEEDS}
        for key, (name, url) in FEEDS.items():
            old = {r["id"]: r for r in previous["rows"] if r.get("feed") == key}
            try:
                fresh = requests[key].result()
                if not fresh and old and any(eligible(r["due"]) for r in old.values()):
                    raise ValueError("Unverified empty list")
                for row in fresh:
                    row["observed"] = start[:10]
                rows.extend(fresh)
                states.append(dict(id=key, name=name, url=url, status="ok", checked=start, observed=start))
            except Exception as exc:
                print(f"Feed {key}: {type(exc).__name__}: {exc}", flush=True)
                rows.extend(old.values())
                states.append(dict(id=key, name=name, url=url, status="stale", checked=start,
                                   observed=old_feeds.get(key, {}).get("observed")))
    return dict(snapshot="2026-11-19", checked=start, rows=rows, feeds=states)


if __name__ == "__main__":
    import sys
    previous = seed() if SNAPSHOT.exists() else None
    output = refresh(previous)
    if any(f["status"] != "ok" for f in output["feeds"]):
        sys.exit("One or more sources failed; bundled snapshot not changed")
    if "--scheduled" in sys.argv:
        output["scheduled"] = True
    if "--snapshot" in sys.argv:
        SNAPSHOT.write_text("window.KVARTAL_SNAPSHOT=" + json.dumps(output, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print([(f["name"], sum(x.get("feed") == f["id"] for x in output["rows"])) for f in output["feeds"]])
