"""Export the bundled data in a readable standalone Markdown reference."""
import argparse
from pathlib import Path

from catalog import seed


def ru_num(value):
    return f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")


def price(row):
    if row.get("price") is None:
        return row.get("priceText", "Не опубликована")
    lo = ru_num(row["price"])
    hi = "–" + ru_num(row["priceMax"]) if row.get("priceMax") is not None else ""
    kind = row.get("priceKind")
    tag = {"example": " (пример)", "archived": " (архивная цена)"}.get(kind, "")
    return f"{'от ' if kind == 'from' else ''}{lo}{hi} {row['currency']}/м²{tag}"


def fmt(val):
    return str(val or "Не опубликовано").replace("|", "\\|").replace("\n", "<br>")


def reference(row):
    links = [["Карточка / публикация", row["url"]], *row.get("sources", [])]
    return "; ".join(f"[{title}]({url})" for title, url in links)


def report(data):
    rows = data["rows"]
    city = [r for r in rows if r["zone"] == "city"]
    district = [r for r in rows if r["zone"] == "district"]
    out = [
        "# Новостройки Минска и Минского района до 2028 года",
        "",
        f"Срез на 19 ноября 2026 года. Всего в списке: {len(rows)}, в том числе {len(city)} в Минске и {len(district)} в Минском районе. Позиция может включать два дома с общим сроком и условиями.",
        "Критерий включения: опубликованный плановый ввод до 1 января 2028 года. Это выборка открытых источников, не официальный реестр и не подтверждение наличия квартир.",
        "",
        "## Как пользоваться списком",
        "",
        "- **Цена**: BYN, USD и EUR указаны как в соответствующих источниках. USD и EUR приведены в справочном эквиваленте; условия договора уточняйте у застройщика.",
        "- **Площади и планы**: проектный диапазон и опубликованная партия не равны фактическим остаткам. Для чертежей и свежего наличия используйте ссылки по каждой позиции.",
        "- **Заказчик**: когда источник называет только застройщика, строительную организацию или группу, это отмечено явно. Размер взноса и график лучше сверять с действующей декларацией.",
        "",
    ]
    for heading, items in (("Минск", city), ("Минский район", district)):
        out += [f"## {heading}", "", "| Дом и адрес | Плановая сдача | Цена за м² | Заказчик / застройщик | Планировки и площади | Условия оплаты и оговорки | Источники |",
                "|---|---|---|---|---|---|---|"]
        for row in sorted(items, key=lambda r: (r["due"] + (5 if r["due"] % 10 == 0 else 0), r.get("project", ""), r["name"])):
            title = (row.get("project", "") + " · " if row.get("project") else "") + row["name"]
            summary = [row.get("area"), ", ".join(str(x) for x in row.get("rooms", [])) + " комн." if row.get("rooms") else None, row.get("layout")]
            if isinstance(row.get("stock"), int):
                summary.append(f"В витрине: {row['stock']} кв. на дату проверки.")
            cells = [f"**{title}**<br>{row['address']}", row["when"], price(row),
                     f"{row['builder']}<br>{row['role']}", " ".join(filter(None, summary)),
                     " ".join(filter(None, (row.get("payment"),row.get("note")))),reference(row)]
            out.append("| " + " | ".join(map(fmt,cells)) + " |")
        out.append("")
    out += ["## Что не включено", "",
            "- **Лошица-10**: разбивка по конкретным корпусам со сдачей в 2027 году не подтверждена; опубликован диапазон 2027–2028 ([Мингорисполком в сообщении БЕЛТА](https://belta.by/amp/regions/view/uks-mingorispolkoma-ozvuchil-plany-zastrojki-stolitsy-i-smolevichej-811117-2026/)).",
            "- **Левада**: дом 12.2 уже введён, а для дома 12.1 застройщик указывает январь 2028 года ([дом 12.2](https://www.airon.by/dom/223), [дом 12.1](https://www.airon.by/dom/226)).",
            "- **STONE**: объект находится в Смолевичском, а не в Минском районе ([адрес в карточке квартиры](https://realt.by/sale-flats/object/4271260/)).",
            "- **Минск-Мир**: общий срок комплекса не является датой ввода квартиры; многофункциональные помещения в список не включены. Сверяйте тип «Квартира», стадию «Строится» и год в [официальной витрине](https://minskworld.by/search-by-parameters/).",
            ""]
    return "\n".join(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    args.path.write_text(report(seed()), encoding="utf-8")
