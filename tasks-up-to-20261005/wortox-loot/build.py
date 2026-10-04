# -*- coding: utf-8 -*-
"""
生成「小恶魔（沃托克斯）· 月族偷窃掉落一览」图鉴页面。

数据口径：UM Beta 6.0.2.4（用户指定的第二张参考图）。
设计：羊皮纸手账 / 博物图鉴 —— 刻意避开深色卡头 + 圆角卡片 + 彩色药丸这套
      统计众数，浅色纸面、宋体标题、手绘图标、墨线分隔、概率条用「疏密」编码
      而不是靠颜色装饰。
"""
import base64
import html
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
ICON_DIRS = [ROOT / "icons" / d for d in ("A", "B", "C")]

# ================================================================ 设计令牌
PAPER = "#EDE4D0"
PAPER_HI = "#F5EFE1"
PAPER_LO = "#E3D7BE"
INK = "#2B2721"
INK_MID = "#5B5346"
INK_SOFT = "#8A7E68"
RULE = "#C4B697"
RULE_SOFT = "#D6C9AC"
ACCENT = "#9C3B27"      # 朱砂：致死标记、页眉重点
BRASS = "#7C6224"       # 黄铜：BOSS、版本号

# 生物类别 → 标记色（语义固定：颜色只用来区分生物门类，不做装饰）
TAXON = {
    "hostile": ("#A8402F", "敌对"),
    "plant":   ("#5C7A3C", "植物"),
    "neutral": ("#3F6E82", "中立"),
    "passive": ("#7A5C2E", "被动"),
    "boss":    ("#6B4A8C", "BOSS"),
}
TAXON_ORDER = ["hostile", "boss", "plant", "neutral", "passive"]

# 掉落物 → 象征色（贴合物品本身：蜜黄 / 叶绿 / 矿物蓝 / 皮肉红 / 孢子紫）
ICON_COLOR = {
    "stinger": "#C0862B", "honey": "#E3B341", "twigs": "#8A6B3C", "human-meat": "#B5503F",
    "meat-skewer": "#B5503F", "gold-nugget": "#E3B341", "boards": "#C0862B", "pig-coin": "#E3B341",
    "nightmare-petals": "#8A6BA8", "dark-petals": "#8A6BA8", "green-gem": "#4E8C6A",
    "nightmare-fuel": "#8A6BA8", "scaffolding-blueprint": "#4A7BA7", "orange-gem": "#C0862B",
    "yellow-gem": "#E3B341", "marble": "#8A8C7E", "beefalo-wool": "#C0862B",
    "beefalo-horn": "#8A8C7E", "carrot": "#C0862B", "cupcake": "#E3B341",
    "glow-berry": "#E3B341", "rabbit-pelt": "#8A8C7E", "pinecone": "#C0862B",
    "living-log": "#8FA35A", "honeycomb": "#E3B341", "royal-jelly": "#E3B341",
    "moleworm": "#8A6B3C", "rabbit": "#8A8C7E", "canary": "#E3B341",
    "junk-grass": "#8FA35A", "junk-grass-tuft": "#8FA35A", "junk-rocks": "#8A8C7E",
    "junk-flotsam": "#4A7BA7", "thermal-stone": "#B5503F", "firefly-spores": "#C0862B",
    "nitre": "#8A8C7E", "crow-egg": "#8A8C7E", "floaty-bottle": "#4A7BA7",
    "wood-charcoal": "#5B5346", "gold-coin": "#E3B341", "scrap-wire": "#B5503F",
    "gnome": "#B5503F", "gord-gear": "#8A6B3C", "spider-eggs": "#8A8C7E",
    "moon-glass-axe": "#4A7BA7", "moon-shard": "#4A7BA7", "gem-blue": "#4A7BA7",
    "gem-red": "#B5503F", "crown": "#E3B341", "bearger-fur": "#C0862B",
}

# ================================================================ 纸纹
NOISE = (
    '<svg xmlns="http://www.w3.org/2000/svg" style="position:absolute;width:0;height:0" '
    'aria-hidden="true"><filter id="paperGrain" x="0" y="0" width="100%" height="100%">'
    '<feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="4" stitchTiles="stitch"/>'
    '<feColorMatrix type="saturate" values="0"/>'
    '<feComponentTransfer><feFuncA type="linear" slope="0.5" intercept="0"/></feComponentTransfer>'
    '</filter></svg>'
)

# ================================================================ 通用说明
NOTES_MAIN = [
    ("解锁", "沃托克斯技能树 ·「立场」分支点亮<b>「月之盟誓」</b>后，用月族武器（玻璃刀 / 月光玻璃斧 / 亮茄剑 / 亮茄粉碎者）攻击生物时触发偷窃。"),
    ("效果", "先把目标随身物品偷光（最多尝试 <b>100</b> 次），再按下面各生物的专属掉落表随机偷出物品；同时造成 <b>42.5</b> 点伤害。"),
    ("灵魂判定", "身上需有至少 <b>1</b> 个可用灵魂；首次偷窃前需先灵魂跳跃一次进入判定窗口，之后每次偷窃会顺延窗口 —— 灵魂只是进入回声冷却，<b>并非直接消耗</b>。"),
    ("偷窃次数", "对 BOSS（epic）每次偷窃间隔 <b>10 天</b>（4800 秒）；普通生物和小动物<b>终生只能偷窃一次</b>。"),
]
NOTES_EXTRA = [
    ("无专属掉落表", "改为从其原生掉落表中随机偷取一件，肉类会被过滤掉、不参与随机。地表召唤的<b>「复活的骨架」</b>即属此类。"),
    ("掉落数量", "表中「×n」表示实际输出 n 个；带<b>红字</b>标注的物品偷到后生物会立刻死亡，即死时的额外掉落见红字区标注。"),
]

# ================================================================ 掉落数据
# (生物名, 类别, 附加标记, [(图标key, 显示名, 数量 or None, 概率 or None, 偷到即死)])
ENTRIES = [
    ("蜜蜂", "hostile", "", [
        ("stinger", "蜂刺", None, 83.33, False),
        ("honey", "蜂蜜", None, 16.67, False),
    ]),
    ("食人花", "plant", "", [
        ("twigs", "树枝", None, 99.0, False),
        ("human-meat", "食人肉", None, 1.0, False),
    ]),
    ("猪人守卫", "hostile", "", [
        ("meat-skewer", "肉串", 1, 25.0, False),
        ("gold-nugget", "金块", 3, 25.0, False),
        ("boards", "木板", None, 25.0, False),
        ("pig-coin", "猪鼻铸币", 3, 25.0, False),
    ]),
    ("阿比盖尔", "boss", "crown", [
        ("dark-petals", "深色花瓣", None, 100.0, True),
    ]),
    ("远古守护者", "boss", "crown", [
        ("green-gem", "绿宝石", 1, 14.29, False),
        ("nightmare-fuel", "噩梦燃料", 4, 14.29, False),
        ("scaffolding-blueprint", "石柱脚手架蓝图", None, 14.29, False),
        ("orange-gem", "橙宝石", 1, 14.29, False),
        ("yellow-gem", "黄宝石", 1, 14.29, False),
        ("marble", "锰矿", 4, 28.57, False),
    ]),
    ("皮弗娄牛", "neutral", "", [
        ("beefalo-wool", "牛毛", None, 50.0, False),
        ("beefalo-horn", "牛角", None, 50.0, False),
    ]),
    ("兔人", "neutral", "", [
        ("carrot", "胡萝卜", 1, 22.22, False),
        ("cupcake", "粉末蛋糕", None, 11.11, False),
        ("glow-berry", "发光浆果", None, 11.11, False),
        ("junk-grass-tuft", "干草叉", None, 11.11, False),
        ("rabbit-pelt", "兔子卷", None, 11.11, False),
    ]),
    ("树精守卫", "plant", "", [
        ("pinecone", "松果", 2, 50.0, False),
        ("living-log", "活木", 1, 50.0, False),
    ]),
    ("树精守卫（深色）", "plant", "shade", [
        ("pinecone", "松果", 2, 50.0, False),
        ("living-log", "活木", 1, 50.0, False),
    ]),
    ("熊獾", "boss", "crown", [
        ("honey", "蜂蜜", None, 75.0, False),
        ("bearger-fur", "熊獾毛皮", None, 25.0, False),
    ]),
    ("浣猫", "hostile", "", [
        ("moleworm", "鼹鼠（活体）", None, 30.77, False),
        ("rabbit", "兔子（活体）", None, 15.38, False),
        ("canary", "金丝雀（中毒）", None, 7.692, False),
        ("scrap-wire", "烂电线", None, 15.38, False),
        ("gnome", "地精爷爷", None, 15.38, False),
        ("gord-gear", "高尔迪之结", None, 15.38, False),
    ]),
    ("蚁狮", "boss", "crown", [
        ("thermal-stone", "暖石", None, 8.333, False),
        ("junk-rocks", "尘土块", None, 8.333, False),
        ("nitre", "锰矿", None, 8.333, False),
        ("orange-gem", "橙宝石", None, 66.67, False),
        ("crow-egg", "鸟蛋", None, 8.333, False),
    ]),
    ("蜂王", "boss", "crown", [
        ("honeycomb", "蜂巢", None, 60.0, False),
        ("royal-jelly", "蜂王浆", None, 40.0, False),
    ]),
    ("帝王蟹", "boss", "crown", [
        ("floaty-bottle", "瓶中信", None, 100.0, False),
    ]),
    ("无眼鹿", "passive", "crown", [
        ("wood-charcoal", "木炭", None, 100.0, True),
    ]),
]

LEGEND = [
    ("≥ 70%", "often", "掉得多"),
    ("30–69%", "common", "一般"),
    ("< 30%", "rare", "看脸"),
]

# 展示顺序：左栏「敌对 → 植物 → BOSS」，右栏「中立 → 被动 → BOSS」，
# 每栏自上而下是一条连贯的色阶，而不是红蓝红绿地跳。
ORDER = [
    "蜜蜂", "食人花", "猪人守卫", "树精守卫", "树精守卫（深色）", "阿比盖尔",
    "无眼鹿", "远古守护者", "皮弗娄牛", "兔人", "熊獾", "浣猫", "蚁狮", "蜂王", "帝王蟹",
]


def ordered_entries():
    by_name = {e[0]: e for e in ENTRIES}
    return [by_name[n] for n in ORDER if n in by_name]


# ================================================================ 图标装载
def load_icons():
    icons, missing = {}, []
    for d in ICON_DIRS:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.svg")):
            src = f.read_text(encoding="utf-8").strip()
            src = re.sub(r"<\?xml.*?\?>", "", src, flags=re.S).strip()
            src = re.sub(r"<!--.*?-->", "", src, flags=re.S).strip()
            m = re.search(r'data-icon="([^"]+)"', src)
            key = m.group(1) if m else f.stem
            if not src.startswith("<svg"):
                missing.append(f"{f.name}(格式异常)")
                continue
            src = re.sub(r'\s+(width|height)="[^"]*"', "", src, count=4)
            icons[key] = src
    return icons, missing


def need_keys():
    return {d[0] for _, _, _, drops in ENTRIES for d in drops}


# ================================================================ 渲染辅助
def fmt_pct(p):
    if p is None:
        return ""
    if abs(p - round(p)) < 1e-9:
        return f"{int(round(p))}%"
    return f"{p:g}%"


def bar_cell(p, dead):
    """概率条：长度按立方根压缩（否则 1% 和 7% 在视觉上没差别），
    疏密按原始值分级——颜色只负责分级，不负责好看。"""
    if p is None:
        return '<span class="ev">—</span>'
    ratio = (p / 100.0) ** (1 / 3.0)
    tier = "often" if p >= 70 else ("common" if p >= 30 else "rare")
    if dead:
        tier += " dead"
    w = max(ratio * 100.0, 5.0)
    return (f'<span class="track"><i class="fill {tier}" style="width:{w:.1f}%"></i>'
            f'<b class="pct">{fmt_pct(p)}</b></span>')


def render_drop(key, label, qty, pct, dead, icons):
    icon = icons.get(key, "")
    if not icon:
        icon = f'<svg viewBox="0 0 48 48" data-icon="missing"><circle cx="24" cy="24" r="13" fill="none" stroke="#B8873F" stroke-width="2" stroke-linecap="round"/></svg>'
    color = ICON_COLOR.get(key, "#C0862B")
    q = f'<em class="qty">×{qty}</em>' if qty else ""
    d = '<span class="dead-mark">即死</span>' if dead else ""
    name = html.escape(label)
    return (f'<li class="drop{" is-dead" if dead else ""}">'
            f'<span class="ico" style="--tint:{color}">{icon}</span>'
            f'<span class="nm">{name}{q}</span>'
            f'{bar_cell(pct, dead)}{d}'
            f'</li>')


def render_entry(entry, icons):
    name, taxon, mark, drops = entry
    color, taxon_label = TAXON[taxon]
    crown = icons.get("crown", "") if mark == "crown" else ""
    crown_html = f'<span class="crown">{crown}</span>' if crown else ""
    shade = '<span class="shade-note">深色变体</span>' if mark == "shade" else ""
    kind = '<span class="kind">斩杀</span>' if taxon == "passive" else ""
    rows = "".join(render_drop(*d, icons) for d in drops)
    total = sum(d[3] for d in drops if d[3] is not None)
    note = ""
    if abs(total - 100.0) > 0.05:
        note = f'<span class="sum">合计 {fmt_pct(round(total, 2))}</span>'
    return (f'<section class="entry taxon-{taxon}">'
            f'<header class="creature"><span class="mark" style="--taxon:{color}"></span>'
            f'<h3>{html.escape(name)}</h3>{crown_html}{kind}{shade}'
            f'<span class="taxon-label">{taxon_label}</span></header>'
            f'<ul class="drops">{rows}</ul>{note}</section>')


def estimate_height(entry):
    """粗略估高，用于平衡两栏。"""
    _, _, _, drops = entry
    h = 31.0
    for _, label, _, _, _ in drops:
        h += 21.5 + (21.5 if len(label) > 7 else 0.0)
    return h


def split_columns(entries):
    """按估高找最佳切分点，让左右两栏长度接近（保持原有阅读顺序，只切一刀）。"""
    heights = [estimate_height(e) for e in entries]
    total = sum(heights)
    best, best_cost = None, None
    run = 0.0
    for i in range(1, len(entries)):
        run += heights[i - 1]
        cost = abs(total - 2 * run) + 16.0 * abs(i - len(entries) / 2)
        if best_cost is None or cost < best_cost:
            best, best_cost = i, cost
    if best is None:
        return entries, []
    return entries[:best], entries[best:]


# ================================================================ CSS
def build_css():
    return f"""
:root {{
  --paper: {PAPER}; --paper-hi: {PAPER_HI}; --paper-lo: {PAPER_LO};
  --ink: {INK}; --ink-mid: {INK_MID}; --ink-soft: {INK_SOFT};
  --rule: {RULE}; --rule-soft: {RULE_SOFT};
  --accent: {ACCENT}; --brass: {BRASS};
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  width: 1240px; background: var(--paper);
  color: var(--ink);
  font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif;
  font-size: 13.5px; line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  position: relative;
}}
/* 纸面：中间略亮、四角略沉，再盖一层极淡的纤维颗粒，避免纯平背景的塑料感 */
.grain {{
  position: fixed; inset: 0; pointer-events: none; opacity: .30;
  mix-blend-mode: multiply; filter: url(#paperGrain);
  background: transparent;
}}
.vignette {{
  position: fixed; inset: 0; pointer-events: none;
  background:
    radial-gradient(115% 85% at 42% 22%, rgba(255,252,244,.85) 0%, rgba(255,252,244,0) 58%),
    radial-gradient(130% 110% at 50% 100%, rgba(120,98,60,.13) 0%, rgba(120,98,60,0) 55%);
}}
.page {{ position: relative; padding: 40px 50px 34px; }}

/* ---------------------------------------------------------- 页眉 */
.masthead {{ position: relative; padding-bottom: 14px; }}
.masthead::after {{
  content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 2px;
  background: var(--ink); opacity: .82;
}}
.masthead::before {{
  content: ""; position: absolute; left: 0; bottom: -5px; width: 190px; height: 1px;
  background: var(--ink); opacity: .38;
}}
.kicker {{
  font-family: "Cascadia Mono", Consolas, monospace; font-size: 10.5px;
  letter-spacing: .26em; color: var(--ink-soft); text-transform: uppercase;
  margin: 0 0 6px;
}}
.kicker b {{ color: var(--accent); letter-spacing: .26em; }}
.title {{
  font-family: "Noto Serif SC", "Source Han Serif SC", SimSun, serif;
  font-weight: 900; font-size: 46px; line-height: 1.08; letter-spacing: .012em;
  margin: 0;
}}
.title .sub {{ font-size: 27px; font-weight: 700; color: var(--ink-mid); letter-spacing: .04em; }}
.title .slash {{ color: var(--accent); font-weight: 700; padding: 0 10px; font-size: 30px; }}
.masthead-foot {{
  display: flex; align-items: baseline; justify-content: space-between;
  margin-top: 10px; gap: 24px;
}}
.standfirst {{ margin: 0; color: var(--ink-mid); font-size: 14px; max-width: 760px; }}
.standfirst b {{ color: var(--ink); }}
.stamp {{
  font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px;
  color: var(--brass); border: 1px solid var(--rule); border-radius: 2px;
  padding: 3px 9px; white-space: nowrap; letter-spacing: .04em;
  box-shadow: inset 0 0 0 3px var(--paper);
}}

/* ---------------------------------------------------------- 通用说明 */
.notes {{
  margin-top: 26px; display: grid; grid-template-columns: 250px 1fr 340px;
  gap: 0; border-top: 1px solid var(--rule);
}}
.notes-aside {{
  padding: 18px 22px 20px 0; border-right: 1px solid var(--rule-soft);
}}
.notes-aside h2 {{
  font-family: "Noto Serif SC", SimSun, serif; font-size: 19px; font-weight: 900;
  margin: 0 0 4px; letter-spacing: .06em;
}}
.notes-aside h2 small {{
  display: block; font-family: "Cascadia Mono", Consolas, monospace; font-size: 9.5px;
  font-weight: 400; letter-spacing: .2em; color: var(--ink-soft); margin-top: 5px;
}}
.notes-aside p {{ margin: 12px 0 0; font-size: 12px; color: var(--ink-mid); line-height: 1.65; }}
.notes-aside .ref {{ color: var(--accent); }}
.note-list {{ list-style: none; margin: 0; padding: 16px 26px 16px 24px; }}
.note-list.second {{ border-left: 1px solid var(--rule-soft); padding-right: 0; }}
.note-list li {{ display: grid; grid-template-columns: 66px 1fr; gap: 12px; padding: 7px 0; }}
.note-list li + li {{ border-top: 1px dotted var(--rule); }}
.note-list .tag {{
  font-size: 11.5px; color: var(--ink-soft); letter-spacing: .06em;
  padding-top: 1px; white-space: nowrap;
}}
.note-list .tag::before {{
  content: "▚"; font-size: 8px; margin-right: 5px; color: var(--rule); vertical-align: 1px;
}}
.note-list p {{ margin: 0; font-size: 12.8px; line-height: 1.62; color: var(--ink-mid); }}
.note-list b {{ color: var(--ink); font-weight: 700; }}
.note-list .dead b {{ color: var(--accent); }}

/* ---------------------------------------------------------- 掉落表 */
.ledger {{ margin-top: 30px; }}
.ledger-head {{
  display: flex; align-items: flex-end; justify-content: space-between;
  padding-bottom: 9px; border-bottom: 2px solid var(--ink); gap: 20px;
}}
.ledger-head h2 {{
  font-family: "Noto Serif SC", SimSun, serif; font-size: 25px; font-weight: 900;
  margin: 0; letter-spacing: .05em;
}}
.ledger-head h2 em {{
  font-style: normal; font-size: 13px; font-weight: 400; color: var(--ink-soft);
  letter-spacing: .04em; margin-left: 12px;
}}
.legend {{ display: flex; gap: 13px; align-items: center; }}
.legend span {{
  font-family: "Cascadia Mono", Consolas, monospace; font-size: 10px;
  color: var(--ink-mid); display: flex; align-items: center; gap: 5px; white-space: nowrap;
}}
.legend i {{ display: block; width: 34px; height: 9px; border: 1px solid var(--rule); }}
.legend i.often {{ background: var(--ink); opacity: .86; }}
.legend i.common {{ background: repeating-linear-gradient(45deg, var(--ink) 0 1.6px, transparent 1.6px 3.4px); opacity: .80; }}
.legend i.rare {{ background: repeating-linear-gradient(45deg, var(--ink) 0 1px, transparent 1px 4.6px); opacity: .58; }}
.legend i.dead {{ background: var(--accent); opacity: .88; }}
.taxon-strip {{
  display: flex; gap: 18px; padding: 9px 0 0; flex-wrap: wrap;
  border-bottom: 1px solid var(--rule); padding-bottom: 9px;
}}
.taxon-strip span {{
  display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--ink-mid);
}}
.taxon-strip i {{ width: 11px; height: 4px; border-radius: 1px; display: block; }}

.columns {{ display: flex; gap: 40px; margin-top: 4px; }}
.col {{ flex: 1 1 0; min-width: 0; }}

.entry {{
  padding: 11px 0 12px; position: relative;
  border-bottom: 1px solid var(--rule-soft);
  break-inside: avoid;
}}
.creature {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 5px; }}
.creature .mark {{
  width: 4px; height: 13px; border-radius: 1px; background: var(--taxon);
  align-self: center; flex: none; transform: translateY(1px);
}}
.creature h3 {{
  font-family: "Noto Serif SC", SimSun, serif; font-size: 16.5px; font-weight: 900;
  margin: 0; letter-spacing: .03em; white-space: nowrap;
}}
.creature .crown {{ display: inline-flex; width: 17px; height: 17px; align-self: center; }}
.creature .crown svg {{ width: 100%; height: 100%; }}
.creature .kind {{
  font-size: 10px; color: var(--accent); border: 1px solid var(--accent);
  padding: 0 3px; letter-spacing: .08em; border-radius: 1px; align-self: center;
  opacity: .9;
}}
.creature .shade-note, .creature .taxon-label {{
  font-size: 10.5px; color: var(--ink-soft); letter-spacing: .05em; align-self: center;
}}
.creature .taxon-label {{ margin-left: auto; }}

.drops {{ list-style: none; margin: 0; padding: 0 0 0 13px; }}
.drop {{
  display: grid; grid-template-columns: 22px minmax(0, 1fr) 52px 46px 34px;
  align-items: center; gap: 12px; padding: 2.5px 0;
}}
.drop .ico {{
  width: 21px; height: 21px; display: block; border-radius: 50%;
  background: color-mix(in srgb, var(--tint) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--tint) 26%, transparent);
}}
.drop .ico svg {{ width: 100%; height: 100%; display: block; }}
.drop .nm {{
  font-size: 12.5px; color: var(--ink); overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; letter-spacing: .01em;
}}
.drop .qty {{
  font-style: normal; font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 11px; color: var(--brass); margin-left: 4px;
}}
.track {{
  position: relative; display: block; height: 10px; border: 1px solid var(--rule);
  background: rgba(255,255,255,.45);
}}
.fill {{ display: block; height: 100%; }}
.fill.often  {{ background: var(--ink); opacity: .86; }}
.fill.common {{ background: repeating-linear-gradient(45deg, var(--ink) 0 1.6px, transparent 1.6px 3.4px); opacity: .80; }}
.fill.rare   {{ background: repeating-linear-gradient(45deg, var(--ink) 0 1px, transparent 1px 4.6px); opacity: .58; }}
.fill.dead   {{ background: var(--accent); opacity: .9; }}
.fill.often.dead, .fill.common.dead, .fill.rare.dead {{ background: var(--accent); opacity: .88; }}
.pct {{
  font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px;
  font-weight: 400; color: var(--ink-mid); letter-spacing: -.01em; text-align: right;
  padding-right: 13px; font-variant-numeric: tabular-nums; white-space: nowrap;
}}
.is-dead .pct {{ color: var(--accent); font-weight: 700; }}
.dead-mark {{
  font-size: 9.5px; letter-spacing: .06em; color: var(--accent); white-space: nowrap;
  border: 1px solid var(--accent); border-radius: 1px; padding: 0 3px; text-align: center;
  opacity: .85; transform: rotate(-2deg); justify-self: end;
}}
.drop:not(.is-dead)::after {{ content: ""; }}
.sum {{
  display: block; margin: 4px 0 0 12px; font-size: 10.5px; color: var(--ink-soft);
  font-family: "Cascadia Mono", Consolas, monospace;
}}
.ev {{ color: var(--ink-soft); font-size: 11px; }}

/* ---------------------------------------------------------- 页脚 */
.colophon {{
  margin-top: 26px; padding-top: 12px; border-top: 2px solid var(--ink);
  display: flex; justify-content: space-between; align-items: flex-end; gap: 30px;
}}
.colophon p {{ margin: 0; font-size: 11.5px; color: var(--ink-soft); line-height: 1.7; }}
.colophon b {{ color: var(--ink-mid); }}
.colophon .sig {{
  font-family: "Noto Serif SC", SimSun, serif; font-size: 13px; color: var(--ink-mid);
  letter-spacing: .1em; white-space: nowrap;
}}
"""


# ================================================================ HTML
def build_html(icons):
    entries = ordered_entries()
    left, right = split_columns(entries)
    notes_a = "".join(
        f'<li class="{"dead" if k == "掉落数量" else ""}"><span class="tag">{k}</span><p>{v}</p></li>'
        for k, v in NOTES_MAIN)
    notes_b = "".join(f'<li><span class="tag">{k}</span><p>{v}</p></li>' for k, v in NOTES_EXTRA)
    legend = "".join(
        f'<span><i class="{cls}"></i>{rng} · {txt}</span>'
        for rng, cls, txt in LEGEND)
    taxon_keys = "".join(
        f'<span><i style="background:{TAXON[t][0]}"></i>{TAXON[t][1]}</span>'
        for t in TAXON_ORDER)
    col_a = "".join(render_entry(e, icons) for e in left)
    col_b = "".join(render_entry(e, icons) for e in right)
    n_creature = len(ENTRIES)
    n_items = len({d[0] for _, _, _, drops in ENTRIES for d in drops})

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>小恶魔（沃托克斯）· 月族偷窃掉落一览</title>
<style>{build_css()}</style></head>
<body>
{NOISE}
<div class="vignette"></div>
<div class="grain"></div>
<div class="page">

  <header class="masthead">
    <p class="kicker">Don't Starve Together · Mod Field Notes · <b>Wortox</b></p>
    <h1 class="title">小恶魔<span class="slash">/</span>月族偷窃掉落一览<span class="sub"></span></h1>
    <div class="masthead-foot">
      <p class="standfirst">技能树「<b>月之盟誓</b>」改写了沃托克斯的偷窃逻辑：不再是常规掉落，而是先掏空随身物品，
      再从各生物的专属表里随机摸一件。下面是把 {n_creature} 个条目、{n_items} 类掉落物逐个拆开的结果。</p>
      <span class="stamp">数据口径 UM Beta 6.0.2.4</span>
    </div>
  </header>

  <section class="notes">
    <div class="notes-aside">
      <h2>通用说明<small>BEFORE YOU START</small></h2>
      <p>技能树「月之盟誓」修改偷窃效果。掉落表取自模组文件，<span class="ref">概率即权重</span>。</p>
    </div>
    <ul class="note-list">{notes_a}</ul>
    <ul class="note-list second">{notes_b}</ul>
  </section>

  <section class="ledger">
    <div class="ledger-head">
      <h2>偷窃掉落列表<em>普通生物 · 专属掉落表</em></h2>
      <div class="legend">{legend}</div>
    </div>
    <div class="taxon-strip">{taxon_keys}<span style="margin-left:auto;color:#8A7E68">条带疏密 = 概率高低</span></div>
    <div class="columns">
      <div class="col">{col_a}</div>
      <div class="col">{col_b}</div>
    </div>
  </section>

  <footer class="colophon">
    <p><b>读表提示</b>　概率条按立方根压缩长度，否则 1% 与 7% 在肉眼上没差别；条带的疏密保留真实分级。<br>
    无专属掉落表的生物（如地表召唤的「复活的骨架」）走原生掉落表随机，肉类已过滤。</p>
    <span class="sig">月之盟誓 · 偷窃结算一览</span>
  </footer>

</div></body></html>
"""


def main():
    icons, missing = load_icons()
    need = need_keys()
    print(f"icons loaded: {len(icons)}")
    miss = sorted(need - set(icons))
    if miss:
        print(f"MISSING ({len(miss)}): " + ", ".join(miss))
    if missing:
        print("BAD FILES: " + ", ".join(missing))
    entries = ordered_entries()
    left, right = split_columns(entries)
    hl = sum(estimate_height(e) for e in left)
    hr = sum(estimate_height(e) for e in right)
    print(f"column balance: left {hl:.0f}px ({len(left)}) / right {hr:.0f}px ({len(right)})")
    print("  L: " + "、".join(e[0] for e in left))
    print("  R: " + "、".join(e[0] for e in right))
    out = ROOT / "index.html"
    out.write_text(build_html(icons), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
