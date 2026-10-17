# -*- coding: utf-8 -*-
"""生成「小猪帮助」指令总览图。只依赖 Pillow，使用 rollpig 自带字体。"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

SERVICE_DIR = Path(os.environ.get("ROLLPIG_SERVICE_DIR", "/opt/qq-agent/rollpig-service"))
MEDIA_BASE = Path(os.environ.get("QQA_MEDIA_DIR", "/opt/qq-agent/media"))

try:
    import nonebot_plugin_rollpig_plus as _rollpig

    BASE = Path(_rollpig.__file__).resolve().parent / "resource" / "fonts"
except Exception:
    BASE = SERVICE_DIR / "nonebot_plugin_rollpig_plus" / "resource" / "fonts"

OUT_DIR = MEDIA_BASE / "rollpig" / "help"
OUT = OUT_DIR / "rollpig-help.png"

W = 1080
BG = (255, 248, 238)
INK = (58, 42, 26)
MUTED = (138, 122, 106)
ORANGE = (224, 122, 46)
ORANGE_DARK = (176, 82, 24)
CREAM = (255, 241, 220)
WHITE = (255, 255, 255)
GREEN = (86, 140, 96)
BLUE = (76, 116, 156)
PINK = (196, 96, 112)

SECTIONS = [
    ("每日小猪", ORANGE, [
        ("今日小猪  /  今天是什么小猪", "看今天属于你的小猪"),
        ("昨日小猪", "回看 / 补签昨天的小猪"),
        ("明日小猪", "预告明天的小猪"),
        ("随机小猪 [1-10]", "随机抽 1~10 只小猪"),
        ("找猪 关键词  /  搜猪 关键词", "按关键词找猪"),
        ("我的猪圈  /  我的小猪", "查看自己的收藏"),
        ("本周小猪", "生成本周小猪长图"),
    ]),
    ("图鉴与投稿", GREEN, [
        ("小猪图鉴 [页码]", "查看完整图鉴，可带页码"),
        ("小猪投稿  /  投稿小猪", "投稿你的小猪"),
        ("猪圈日报", "查看猪圈日报"),
    ]),
    ("烤猪玩法", PINK, [
        ("今日烤猪", "看看今天谁被烤"),
        ("烤群友 @某人", "烤指定群友，可加“强行点火”"),
        ("随机烤猪  /  随机烤群友", "随机选一位群友烤"),
        ("加急生火 @某人", "给烤猪加急"),
        ("烤箱续火  /  烤箱补货", "发起烤箱补货投票"),
        ("重置烤猪次数  /  恢复烧烤配额", "恢复烧烤次数"),
        ("申请烤箱补给  /  重置烧烤次数", "申请补货 / 重置"),
        ("加入  /  加入预约  /  加入烤猪", "回复预约通知时使用"),
    ]),
    ("群管理与帮助", BLUE, [
        ("小猪日报 开启 / 关闭 / 状态", "群管理员设置日报"),
        ("同步小猪资源  /  刷新小猪图鉴", "超级用户同步资源"),
        ("小猪帮助", "随时查看这张指令图"),
    ]),
]

FONT_TITLE = ImageFont.truetype(os.path.join(BASE, "ZCOOLKuaiLe-Regular.ttf"), 74)
FONT_SUB = ImageFont.truetype(os.path.join(BASE, "SourceHanSansSC-Medium.otf"), 28)
FONT_SECTION = ImageFont.truetype(os.path.join(BASE, "SourceHanSansSC-Medium.otf"), 34)
FONT_CMD = ImageFont.truetype(os.path.join(BASE, "SourceHanSansSC-Medium.otf"), 27)
FONT_DESC = ImageFont.truetype(os.path.join(BASE, "SourceHanSansSC-Medium.otf"), 22)
FONT_FOOT = ImageFont.truetype(os.path.join(BASE, "SourceHanSansSC-Medium.otf"), 21)


def text_w(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_header(img, draw):
    # 顶部暖色块
    draw.rectangle([0, 0, W, 236], fill=(247, 170, 92))
    overlay = Image.new("RGBA", (W, 236), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse([-90, -120, 300, 270], fill=(255, 255, 255, 38))
    od.ellipse([760, -150, 1180, 270], fill=(255, 255, 255, 30))
    od.ellipse([880, 130, 1040, 290], fill=(255, 255, 255, 24))
    img.alpha_composite(overlay, (0, 0))

    draw.text((64, 44), "小猪帮助", font=FONT_TITLE, fill=WHITE)
    draw.text((70, 142), "RollPig 指令一览 · 直接发送文字即可，不需要加斜杠", font=FONT_SUB, fill=(255, 250, 242))

    # 右侧小猪脸
    cx, cy = 930, 118
    draw.ellipse([cx - 78, cy - 62, cx + 78, cy + 78], fill=(255, 226, 208))
    draw.polygon([(cx - 70, cy - 50), (cx - 108, cy - 106), (cx - 34, cy - 78)], fill=(255, 210, 188))
    draw.polygon([(cx + 70, cy - 50), (cx + 108, cy - 106), (cx + 34, cy - 78)], fill=(255, 210, 188))
    draw.ellipse([cx - 44, cy - 22, cx - 22, cy + 2], fill=(90, 58, 42))
    draw.ellipse([cx + 22, cy - 22, cx + 44, cy + 2], fill=(90, 58, 42))
    draw.ellipse([cx - 38, cy + 22, cx + 38, cy + 58], fill=(255, 184, 166))
    draw.ellipse([cx - 15, cy + 32, cx - 5, cy + 44], fill=(190, 100, 92))
    draw.ellipse([cx + 5, cy + 32, cx + 15, cy + 44], fill=(190, 100, 92))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # 先算高度
    row_h = 58
    sec_pad_top = 24
    sec_title_h = 52
    sec_pad_bottom = 22
    gap = 22
    body_top = 278
    body_bottom = 56
    total = body_top + body_bottom
    for _, _, rows in SECTIONS:
        total += sec_pad_top + sec_title_h + len(rows) * row_h + sec_pad_bottom + gap
    total -= gap
    H = max(1980, total + 40)

    img = Image.new("RGBA", (W, H), BG + (255,))
    draw = ImageDraw.Draw(img)
    draw_header(img, draw)

    y = body_top
    for title, color, rows in SECTIONS:
        card_h = sec_pad_top + sec_title_h + len(rows) * row_h + sec_pad_bottom
        # 卡片阴影
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rounded_rectangle([54, y + 6, W - 54, y + card_h + 6], radius=30, fill=(120, 80, 40, 26))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        img.alpha_composite(shadow, (0, 0))
        draw = ImageDraw.Draw(img)

        rounded(draw, [48, y, W - 48, y + card_h], 30, WHITE, (244, 230, 212), 1)
        # 左侧色条
        rounded(draw, [48, y, 62, y + card_h], 7, color)

        # 标题胶囊
        tw = text_w(draw, title, FONT_SECTION)
        rounded(draw, [78, y + 20, 78 + tw + 36, y + 20 + 42], 21, tuple(min(255, c + 18) for c in color))
        draw.text((96, y + 24), title, font=FONT_SECTION, fill=WHITE)

        ry = y + sec_pad_top + sec_title_h
        for cmd, desc in rows:
            # 指令前的圆点
            draw.ellipse([82, ry + 15, 94, ry + 27], fill=color)
            draw.text((110, ry + 4), cmd, font=FONT_CMD, fill=INK)
            draw.text((110, ry + 34), desc, font=FONT_DESC, fill=MUTED)
            ry += row_h

        y += card_h + gap

    # 底部提示
    foot = "提示：@ 某人 时请真的 @ 对方；带 [ ] 的为可选参数。  RollPig v0.14.4"
    fw = text_w(draw, foot, FONT_FOOT)
    draw.text(((W - fw) / 2, H - 42), foot, font=FONT_FOOT, fill=(166, 146, 126))

    img.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"written {OUT} {os.path.getsize(OUT)} bytes {W}x{H}")


if __name__ == "__main__":
    main()
