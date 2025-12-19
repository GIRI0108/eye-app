"""
Generate 40 vision test images + Excel question file.
Run:
    python generate_vision_questions.py

Outputs:
 - static/games/questions/q01.png ... q40.png
 - static/games/vision_questions_40.xlsx
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, random
import pandas as pd
from pathlib import Path

# Output paths
BASE = Path(__file__).parent.resolve()
OUT_IMG_DIR = BASE / "static" / "games" / "questions"
OUT_IMG_DIR.mkdir(parents=True, exist_ok=True)

EXCEL_PATH = BASE / "static" / "games" / "vision_questions_40.xlsx"

# Load font safely
def get_font(size):
    possible = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for p in possible:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    return ImageFont.load_default()

FONT_LG = get_font(160)
FONT_MD = get_font(120)
FONT_SM = get_font(40)

questions = []

def text_center(draw, text, font, w, h):
    """Center text using textbbox() --> Pillow 10 compatible."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    return (w - tw) // 2, (h - th) // 2

# ---------------------------------------------------------
# 1–10: Ishihara-like color plates
# ---------------------------------------------------------
numbers = ["12","6","29","8","5","3","15","7","2","10"]

for i in range(1, 11):
    fname = f"q{i:02d}.png"
    im = Image.new("RGB", (512,512), (255,255,255))
    draw = ImageDraw.Draw(im)

    # Scatter colored dots
    for _ in range(700):
        x, y = random.randint(0,511), random.randint(0,511)
        r = random.randint(3,12)
        color = (
            random.randint(80,200),
            random.randint(90,210),
            random.randint(90,220)
        )
        draw.ellipse((x-r,y-r,x+r,y+r), fill=color)

    number = numbers[(i-1) % len(numbers)]
    tx, ty = text_center(draw, number, FONT_MD, 512, 512)
    draw.text((tx, ty), number, font=FONT_MD, fill=(20,20,20))

    im.save(OUT_IMG_DIR / fname)

    # Options
    correct = number
    distract = {correct, str(int(correct)+1), str(int(correct)-1), str(int(correct)+2)}
    opts = list(distract)
    random.shuffle(opts)

    questions.append({
        "id": i,
        "image": f"questions/{fname}",
        "option1": opts[0],
        "option2": opts[1],
        "option3": opts[2],
        "option4": opts[3],
        "answer": correct
    })

# ---------------------------------------------------------
# 11–20: Blur test
# ---------------------------------------------------------
blur_words = ["CENTER","LEFT","RIGHT","CIRCLE","STAR","HOUSE","TREE","SNAKE","CLOUD","RIVER"]

for idx, txt in enumerate(blur_words, start=11):
    fname = f"q{idx:02d}.png"

    base = Image.new("RGB", (512,512), (245,245,250))
    draw = ImageDraw.Draw(base)

    tx, ty = text_center(draw, txt, FONT_MD, 512, 512)
    draw.text((tx, ty), txt, font=FONT_MD, fill=(10,10,10))

    blur_amount = random.randint(0,5)
    im = base.filter(ImageFilter.GaussianBlur(radius=blur_amount))
    im.save(OUT_IMG_DIR / fname)

    options = ["Clear", "Slightly Blurry", "Very Blurry", "Cannot See"]

    if blur_amount <= 1:
        ans = "Clear"
    elif blur_amount <= 3:
        ans = "Slightly Blurry"
    else:
        ans = "Very Blurry"

    questions.append({
        "id": idx,
        "image": f"questions/{fname}",
        "option1": options[0],
        "option2": options[1],
        "option3": options[2],
        "option4": options[3],
        "answer": ans
    })

# ---------------------------------------------------------
# 21–28: Peripheral vision test
# ---------------------------------------------------------
dirs = ["Left","Right","Top","Bottom","Left","Right","Top","Bottom"]

for j, d in enumerate(dirs, start=21):
    fname = f"q{j:02d}.png"
    im = Image.new("RGB", (512,512), (255,255,255))
    draw = ImageDraw.Draw(im)

    # dim grid
    for x in range(0,512,32):
        draw.line([(x,0),(x,512)], fill=(230,230,230))

    if d=="Left":      pos = (60,256)
    elif d=="Right":   pos = (452,256)
    elif d=="Top":     pos = (256,60)
    else:              pos = (256,452)

    draw.ellipse((pos[0]-15,pos[1]-15,pos[0]+15,pos[1]+15), fill=(0,140,0))
    im.save(OUT_IMG_DIR / fname)

    questions.append({
        "id": j,
        "image": f"questions/{fname}",
        "option1": "Left",
        "option2": "Right",
        "option3": "Top",
        "option4": "Bottom",
        "answer": d
    })

# ---------------------------------------------------------
# 29–34: E-chart orientation
# ---------------------------------------------------------
orientations = ["Up","Down","Left","Right","Up","Left"]

for k, ori in enumerate(orientations, start=29):
    fname = f"q{k:02d}.png"
    im = Image.new("RGBA", (512,512), (255,255,255,255))
    draw = ImageDraw.Draw(im)

    e_img = Image.new("RGBA", (200,200), (0,0,0,0))
    ed = ImageDraw.Draw(e_img)
    ed.text((10,10), "E", font=FONT_LG, fill=(20,20,20))

    rot = {"Up":0,"Right":270,"Left":90,"Down":180}[ori]
    e_img = e_img.rotate(rot, expand=True)

    ex, ey = e_img.size
    im.paste(e_img, ((512-ex)//2, (512-ey)//2), e_img)
    im = im.convert("RGB")

    im.save(OUT_IMG_DIR / fname)

    questions.append({
        "id": k,
        "image": f"questions/{fname}",
        "option1": "Up",
        "option2": "Down",
        "option3": "Left",
        "option4": "Right",
        "answer": ori
    })

# ---------------------------------------------------------
# 35–40: Shape test
# ---------------------------------------------------------
shapes = ["Circle","Square","Triangle","Star","Hexagon","Diamond"]

for m in range(35, 41):
    fname = f"q{m:02d}.png"
    im = Image.new("RGB", (512,512), (240,245,255))
    draw = ImageDraw.Draw(im)

    shape = shapes[(m-35) % len(shapes)]
    cx, cy = 256, 256

    draw.rectangle([80,120,432,392], fill=(225,230,245))

    if shape == "Circle":
        draw.ellipse([cx-80,cy-80,cx+80,cy+80], fill=(40,110,200))
    elif shape == "Square":
        draw.rectangle([cx-80,cy-80,cx+80,cy+80], fill=(40,110,200))
    elif shape == "Triangle":
        draw.polygon([(cx,cy-90),(cx-90,cy+70),(cx+90,cy+70)], fill=(40,110,200))
    elif shape == "Star":
        draw.polygon([
            (cx,cy-90),(cx+25,cy-10),(cx+90,cy-10),(cx+40,cy+30),
            (cx+55,cy+90),(cx,cy+45),(cx-55,cy+90),(cx-40,cy+30),
            (cx-90,cy-10),(cx-25,cy-10)
        ], fill=(40,110,200))
    elif shape == "Hexagon":
        draw.polygon([
            (cx-60,cy-30),(cx-30,cy-70),(cx+30,cy-70),
            (cx+60,cy-30),(cx+30,cy+30),(cx-30,cy+30)
        ], fill=(40,110,200))
    else:  # Diamond
        draw.polygon([(cx,cy-80),(cx+60,cy),(cx,cy+80),(cx-60,cy)], fill=(40,110,200))

    im.save(OUT_IMG_DIR / fname)

    opts = shapes.copy()
    random.shuffle(opts)

    questions.append({
        "id": m,
        "image": f"questions/{fname}",
        "option1": opts[0],
        "option2": opts[1],
        "option3": opts[2],
        "option4": opts[3],
        "answer": shape
    })

# ---------------------------------------------------------
# Save Excel
# ---------------------------------------------------------
df = pd.DataFrame(questions)
df.to_excel(EXCEL_PATH, index=False)

print("✔ Images saved to:", OUT_IMG_DIR)
print("✔ Excel saved to:", EXCEL_PATH)
