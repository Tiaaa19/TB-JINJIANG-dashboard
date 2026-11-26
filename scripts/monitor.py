#!/usr/bin/env python3
"""Public-web monitoring for the TB JINJIANG incident and its impact on CULines."""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INDEX = ROOT / "index.html"
STATE = DATA / "latest.json"

QUERIES = [
    '"TB JINJIANG" (CULines OR "China United Lines" OR 中联航运)',
    '"TB JINJIANG" (collision OR PHOTINI OR "general average" OR 共同海损)',
    '"TB JINJIANG" (delay OR cargo OR release OR 延误 OR 放货)',
    'site:mp.weixin.qq.com "TB JINJIANG"',
    'site:mp.weixin.qq.com "TB JINJIANG" (中联航运 OR CULines OR 共同海损)',
]

BASELINE = [
    {
        "date": "11-26", "level": "橙", "topic": "共同海损", "platform": "船东文件",
        "source": "GENERAL AVERAGE DECLARATION", "channel": "一级信源",
        "summary": "船东确认 10 月 13 日与 PHOTINI 碰撞、载有约 10,440 MT 集装箱货物、部分集装箱落水、11 月 21 日签署 Wreckhire 救助合同，并宣布共同海损及委任 RHL。",
        "lang": "英文", "sentiment": "负面", "evidenceType": "船东正式声明",
        "verification": "已核验｜事实基线", "url": "",
        "action": "所有对外事实表述以声明及后续权威更新为准", "owner": "PR/法务"
    },
    {
        "date": "11-26", "level": "橙", "topic": "公司品牌关联", "platform": "MagicPort",
        "source": "TB JINJIANG 船舶资料页", "channel": "船舶数据库",
        "summary": "公开页面直接列示 CHINA UNITED LINES LTD 为 TB JINJIANG 的商业管理方，已形成“事故船舶—CULines”可检索关联；同时确认登记船东为 MACAU JINQIN INTERNATIONAL，平台显示船舶当前未被制裁。",
        "lang": "英文", "sentiment": "中性", "evidenceType": "公司关联证据",
        "verification": "已核验｜直接关联 CULines", "url": "https://magicport.ai/vessels/container/tb-jinjiang-mmsi-636024184",
        "action": "持续监测媒体或公众号是否引用该关系并转化为公司责任叙事", "owner": "PR/合规"
    },
    {
        "date": "11-26", "level": "蓝", "topic": "责任与次生风险", "platform": "Steamship Mutual",
        "source": "TB JINJIANG Vessel Search", "channel": "机构船舶资料",
        "summary": "确认 IMO、登记船东、全集装箱船、蒙罗维亚注册、总吨 17,613，以及 2026-02-20 至 2027-02-20 的在保及证书信息。",
        "lang": "英文", "sentiment": "中性", "evidenceType": "P&I 机构公开资料",
        "verification": "已核验｜非事故报道", "url": "https://www.steamshipmutual.com/tb-jinjiang",
        "action": "作为主体与保险关系核验资料留档", "owner": "保险/法务"
    },
    {
        "date": "11-26", "level": "蓝", "topic": "事故与救助", "platform": "明日数航",
        "source": "TB JINJIANG 船舶定位", "channel": "AIS 船舶动态",
        "summary": "页面更新船舶静态资料及达曼至杰贝阿里申报航次，但未发布碰撞或共同海损报道；ETA 等字段可能未及时更新。",
        "lang": "中文", "sentiment": "中性", "evidenceType": "AIS 聚合页面",
        "verification": "已核验｜动态字段有时延", "url": "https://www.hangyun365.com/vessel/tb-jinjiang-636024184.html",
        "action": "不以申报 ETA 单独判断卸货或修理进度", "owner": "运营"
    },
    {
        "date": "11-24", "level": "黄", "topic": "事故与救助", "platform": "Voyage Radar",
        "source": "AIS Vessel Tracker", "channel": "AIS 船舶动态",
        "summary": "最后可见位置为 25.4667°N、54.7238°E，状态为锚泊、航速 0，申报目的港 Mina Jabal Ali；位置更新时间 11 月 24 日 17:59 UTC。",
        "lang": "英文", "sentiment": "中性", "evidenceType": "AIS 聚合数据",
        "verification": "已核验｜位置非实时结论", "url": "https://aisvesseltracker.com/vessel/tb-jinjiang-mmsi-636024184-imo-9143116",
        "action": "结合港口、船东及救助方信息交叉确认实际状态", "owner": "运营"
    },
    {
        "date": "10-23", "level": "橙", "topic": "客户与索赔", "platform": "LinkedIn",
        "source": "SynMax Maritime", "channel": "专业社交平台",
        "summary": "基于遇险信号、AIS 与 Sentinel 图像分析事故；评论中已有货方表示该事故解释了其集装箱延误，构成对 CULines 客户服务、交付预期和后续放货沟通的直接影响信号。",
        "lang": "英文", "sentiment": "负面", "evidenceType": "公开客户影响信号",
        "verification": "已核验评论｜责任未定", "url": "https://www.linkedin.com/posts/synmax-maritime_collision-persiangulf-tbjinjiang-activity-7519414128067751937-DegE",
        "action": "跟进延误、放货和 GA 担保相关公开投诉，准备统一客户解释口径", "owner": "PR/客服/商务"
    },
    {
        "date": "10-23", "level": "橙", "topic": "责任与次生风险", "platform": "LinkedIn",
        "source": "SynMax Maritime", "channel": "专业社交平台",
        "summary": "帖文称 crew-input draft data 推测两船碰撞时均为空载；该说法与船东声明“TB JINJIANG 载有约 10,440 MT 集装箱货物”冲突。",
        "lang": "英文", "sentiment": "负面", "evidenceType": "第三方数据推断",
        "verification": "冲突信息｜不采纳为空载事实", "url": "https://www.linkedin.com/posts/synmax-maritime_collision-persiangulf-tbjinjiang-activity-7519414128067751937-DegE",
        "action": "如出现转载，应以船东声明纠正空载推断", "owner": "PR/法务"
    }
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TB-JINJIANG-Monitor/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def is_relevant(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    return "tb jinjiang" in text and any(term in text for term in (
        "culines", "china united lines", "中联航运", "photini", "collision",
        "general average", "共同海损", "delay", "cargo", "延误", "放货"
    ))


def classify(url: str, title: str, description: str, published: str) -> dict:
    text = f"{title} {description}".lower()
    is_wechat = "mp.weixin.qq.com" in url
    company = any(x in text for x in ("culines", "china united lines", "中联航运"))
    customer = any(x in text for x in ("delay", "cargo release", "延误", "放货", "货主", "客户"))
    topic = "公司品牌关联" if company else "客户与索赔" if customer else "事故与救助"
    level = "橙" if company or customer else "黄"
    sentiment = "负面" if any(x in text for x in ("collision", "delay", "事故", "碰撞", "延误", "损失")) else "中性"
    platform = "微信公众号" if is_wechat else urllib.parse.urlparse(url).netloc.removeprefix("www.")
    return {
        "date": published,
        "level": level,
        "topic": topic,
        "platform": platform,
        "source": clean(title)[:100],
        "channel": "微信公众号（搜狗/Bing公开索引）" if is_wechat else "公开网页索引",
        "summary": clean(description)[:260] or clean(title),
        "lang": "中文" if re.search(r"[\u4e00-\u9fff]", title + description) else "英文",
        "sentiment": sentiment,
        "evidenceType": "公开索引新记录",
        "verification": "机器初筛｜需人工复核正文",
        "url": url,
        "action": "复核原文与公司关联程度；必要时纳入人工研判",
        "owner": "PR/客服"
    }


def bing_rss(query: str) -> list[dict]:
    url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote(query)
    root = ET.fromstring(fetch(url))
    items = []
    for item in root.findall("./channel/item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        desc = item.findtext("description", "")
        pub = item.findtext("pubDate", "")
        if not link or not is_relevant(title, desc):
            continue
        date = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%m-%d")
        if pub:
            try:
                date = dt.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").strftime("%m-%d")
            except ValueError:
                pass
        items.append(classify(link, title, desc, date))
    return items


def sogou_probe() -> dict:
    url = "https://weixin.sogou.com/weixin?type=2&query=" + urllib.parse.quote("TB JINJIANG 中联航运")
    try:
        body = fetch(url).decode("utf-8", "ignore")
        blocked = not body.strip() or "验证码" in body or "antispider" in body.lower()
        return {"status": "blocked" if blocked else "reachable", "url": url}
    except Exception as exc:  # network status is recorded, not fatal
        return {"status": "error", "url": url, "detail": type(exc).__name__}


def inject(records: list[dict], updated: str) -> None:
    page = INDEX.read_text(encoding="utf-8")
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    page, count = re.subn(r"const records=\[[\s\S]*?\];\nconst trend=", f"const records={payload};\nconst trend=", page, count=1)
    if count != 1:
        raise RuntimeError("Could not locate records block in index.html")
    page = re.sub(r"数据更新 \d{4}-\d{2}-\d{2} \d{2}:\d{2}", f"数据更新 {updated}", page)
    INDEX.write_text(page, encoding="utf-8")


def main() -> None:
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    records = list(BASELINE)
    existing = {item["url"] + "|" + item["source"] for item in records}
    errors = []
    for query in QUERIES:
        try:
            for item in bing_rss(query):
                key = item["url"] + "|" + item["source"]
                if key not in existing:
                    records.append(item)
                    existing.add(key)
        except Exception as exc:
            errors.append({"query": query, "error": type(exc).__name__})

    result = {
        "updatedAt": now.isoformat(timespec="seconds"),
        "scheduleTimezone": "Asia/Shanghai",
        "queries": QUERIES,
        "sogouWeixin": sogou_probe(),
        "errors": errors,
        "records": records,
    }
    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    history = DATA / f"run-{now.strftime('%Y%m%d-%H%M')}.json"
    history.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    inject(records, now.strftime("%Y-%m-%d %H:%M"))
    print(json.dumps({"records": len(records), "new": len(records) - len(BASELINE), "sogou": result["sogouWeixin"]["status"], "errors": len(errors)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
