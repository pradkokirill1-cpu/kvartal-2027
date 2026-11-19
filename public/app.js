"use strict";
const $ = id => document.getElementById(id);
const node = (tag, cls, value) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (value !== undefined) n.textContent = value;
  return n;
};
const format = new Intl.NumberFormat("ru-BY", {maximumFractionDigits: 2});
const date = value => value ? value.slice(0,10).split("-").reverse().join(".") : "не указана";
const title = r => r.project ? `${r.project} · ${r.name}` : r.name;
const price = r => r.price == null ? "Не опубликована" : `${r.priceKind === "from" ? "от " : ""}${format.format(r.price)}${r.priceMax == null ? "" : "–" + format.format(r.priceMax)}`;
const amount = r => r.price == null ? (r.priceText || "Не опубликована") : `${price(r)} ${r.currency}/м²`;
const rooms = r => (r.rooms || []).join(", ");
const compact = r => r.rooms?.length ? `${rooms(r)} комн.` : "";
const normalize = s => s.toLowerCase().replaceAll("ё","е").replace(/[«»№.,–-]/g, " ").replace(/\s+/g," ").trim();
const confirmed = r => Number.isInteger(r.due);
let data = window.KVARTAL_SNAPSHOT, zone = "", selection = [], expanded = new Set();

function link(label, url) {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:") return null;
    const a = node("a", "", label + " ↗");
    a.href = u.href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  } catch { return null; }
}

function line(parent, label, value) {
  const div = node("div");
  div.append(node("h3", "", label), node("p", "", value || "Не опубликовано. Уточняйте у застройщика."));
  parent.append(div);
}

function entry(r) {
  const d = node("details","item");
  d.open = expanded.has(r.id);
  d.addEventListener("toggle", () => d.open ? expanded.add(r.id) : expanded.delete(r.id));
  const sum = node("summary", "row-grid");
  const home = node("span","home");
  home.append(node("span","item-title",title(r)), node("span","item-address",r.address));
  const due = node("span","due",r.when);
  const cost = node("span","price",r.price == null ? amount(r) : price(r));
  if (r.price != null) cost.append(" ", node("small","",`${r.currency}/м²`));
  if (r.priceKind === "example" || r.priceKind === "archived")
    cost.append(node("span","secondary",r.priceKind === "example" ? "Пример" : "Архивная цена"));
  const apt = node("span","apt");
  apt.append(node("span","",r.area || "Площадь не указана"));
  if (compact(r)) apt.append(node("span","secondary",compact(r)));
  const icon = node("span","arrow","+");
  icon.setAttribute("aria-hidden","true");
  sum.append(home,due,cost,apt,icon);
  const body = node("div","body-detail");
  line(body,"Заказчик / застройщик",r.builder ? `${r.builder}\n${r.role || ""}` : null);
  line(body,"Планировки и наличие",[r.layout, Number.isInteger(r.stock) ? `В витрине: ${r.stock} кв. на дату проверки.` : "", !r.layout && !Number.isInteger(r.stock) ? "См. поэтажные планы и доступные лоты в источнике." : ""].filter(Boolean).join("\n"));
  line(body,"Условия оплаты",r.payment);
  line(body,"Примечания и дата", [r.note, `Проверено: ${date(r.observed || data.snapshot)}. ${r.feed ? "Витрина застройщика; условия сделки могут отличаться." : "Карточка проверяется вручную."}`].filter(Boolean).join("\n"));
  const links = node("div","detail-links");
  const items = [[r.feed ? "Карточка застройщика и планы" : "Основной источник",r.url],...(r.sources || [])];
  for (const [label,url] of items) {
    const a = link(label,url);
    if (a) links.append(a);
  }
  body.append(links);
  d.append(sum,body);
  return d;
}

function render() {
  if (!data?.rows) return;
  const search = normalize($("search").value).split(" ").filter(Boolean);
  const year = $("year").value;
  const room = +$("rooms").value;
  const order = $("sort").value;
  selection = data.rows.filter(r =>
    (!zone || r.zone === zone) &&
    (!year || (year === "watch" ? !confirmed(r) : confirmed(r) && Math.floor(r.due / 10) === +year)) &&
    (!room || (r.rooms || []).some(n => room === 4 ? n >= room : n === room)) &&
    search.every(term => normalize([title(r),r.address,r.builder,r.role].filter(Boolean).join(" ")).split(" ").some(word => word.startsWith(term)))
  ).sort((a,b) => {
    const val = r => r.currency?.toLowerCase() === order ? r.price ?? Infinity : Infinity;
    const byDue = r => !confirmed(r) ? 99999 : r.due % 10 ? r.due : r.due + 5;
    return (order !== "due" ? (val(a) - val(b)) || 0 : 0) || byDue(a)-byDue(b) || title(a).localeCompare(title(b),"ru",{numeric:true});
  });
  $("result").textContent = `Показано ${selection.length} из ${data.rows.length} позиций`;
  $("export").disabled = !selection.length;
  if (!selection.length) {
    const block = node("div","empty","По этим фильтрам ничего не найдено. Попробуйте другой адрес или сбросьте условия.");
    const reset = node("button","","Сбросить фильтры");
    reset.onclick = () => {
      $("search").value = $("year").value = $("rooms").value = "";
      $("sort").value = "due";
      document.querySelector('[data-zone=""]').click();
      $("search").focus();
    };
    block.append(reset);
    $("list").replaceChildren(block);
    return;
  }
  const head = node("div","column-head row-grid");
  for (const text of ["Жилой комплекс / дом","Плановая сдача","Цена за метр","Квартиры",""]) head.append(node("span","",text));
  const dated = selection.filter(confirmed), watch = selection.filter(r => !confirmed(r));
  const watchHeading = node("div","watch-heading");
  watchHeading.id = "watchlist";
  watchHeading.append(node("h3","","На контроле"), node("p","","Нет подтверждённой даты ввода до 1 января 2028 года. Эти объекты не входят в выборку по году сдачи."));
  $("list").replaceChildren(...(dated.length ? [head,...dated.map(entry)] : []),
    ...(watch.length ? [watchHeading,...watch.map(entry)] : []));
}

function status(mode) {
  const good = (data.feeds || []).filter(x => x.status === "ok").length;
  const stamp = date(data.checked || data.snapshot);
  const verified = mode === "live" || mode === "scheduled";
  $("status-dot").className = verified && good === data.feeds.length ? "good" : "warn";
  $("status").textContent = mode === "scheduled" ? `Срез автообновления от ${stamp}` :
    mode === "live" ? `Витрины: ${good} из ${data.feeds.length} · ${stamp}` :
    mode === "loading" ? `Срез от ${stamp} · проверяем витрины` : `Срез от ${stamp} · без онлайн-проверки`;
  $("feeds").replaceChildren(...(data.feeds || []).map(f => {
    const li = node("li");
    const a = link(f.name,f.url);
    if (a) li.append(a);
    li.append(`: ${verified && f.status === "ok" ? "проверено" : "сохранённый срез"} ${date(f.observed)}.`);
    return li;
  }));
}

for (const b of document.querySelectorAll("[data-zone]")) b.onclick = () => {
  zone = b.dataset.zone;
  for (const item of document.querySelectorAll("[data-zone]")) item.setAttribute("aria-pressed", String(b === item));
  render();
};
$("search").addEventListener("input", render);
for (const id of ["year","rooms","sort"]) $(id).addEventListener("change", render);

$("export").onclick = () => {
  const clean = value => {
    let val = String(value ?? "");
    if (/^[=+@\-\t\r]/.test(val)) val = "'" + val;
    return `"${val.replaceAll('"','""')}"`;
  };
  const rows = [["Объект","Территория","Адрес","Плановая сдача","Цена за м²","Заказчик или застройщик","Роль","Комнаты","Площадь","Планировки","Квартир в витрине","Оплата","Оговорки","Дата проверки","Источник","Доп. источники","Статус срока"],
    ...selection.map(r => [title(r), r.zone === "city" ? "Минск" : "Минский район",r.address,r.when,amount(r),r.builder,r.role,rooms(r),r.area,r.layout,r.stock,r.payment,r.note,r.observed || data.snapshot,r.url,(r.sources || []).map(s=>s[1]).join(" | "),confirmed(r) ? "Плановый срок опубликован" : "На контроле"])];
  const file = new Blob(["\ufeff", rows.map(r => r.map(clean).join(";")).join("\r\n")],{type:"text/csv;charset=utf-8"});
  const a = node("a");
  const url = URL.createObjectURL(file);
  a.href = url;
  a.download = "novostroyki-minsk-do-2028.csv";
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

const local = location.hostname === "localhost" || location.hostname === "127.0.0.1";
const rawApi = window.KVARTAL_API;
const runtime = local ? "/api/catalog" : rawApi && !rawApi.startsWith("__PORT_") ? `${rawApi.replace(/\/$/,"")}/api/catalog` : null;
async function sync(attempt = 0) {
  try {
    if (data?.scheduled && !runtime) {
      status("scheduled");
      return;
    }
    if (!runtime) throw Error("Offline");
    const response = await fetch(runtime, {cache:"no-store",credentials:"same-origin",signal:AbortSignal.timeout(5500)});
    if (!response.ok) throw Error("Unavailable");
    const result = await response.json();
    if (!Array.isArray(result.rows) || !Array.isArray(result.feeds)) throw Error("Invalid catalog");
    if (!result.refreshing || attempt === 0) {
      data = result;
      render();
    }
    status(result.refreshing ? "loading" : "live");
    if (result.refreshing && attempt < 9) setTimeout(() => sync(attempt + 1), 4000);
    else if (result.refreshing) status("offline");
  } catch {
    if (data) status("offline");
  }
}
if (data) {
  render();
  status("loading");
}
sync();
