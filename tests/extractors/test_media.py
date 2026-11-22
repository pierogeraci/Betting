from PIL import Image, ImageDraw

from extractors.media import Frame, dedupe


def picture(color, shape):
    img = Image.new("RGB", (320, 240), color)
    draw = ImageDraw.Draw(img)
    if shape == "cerchio":
        draw.ellipse((80, 40, 240, 200), fill="white")
    elif shape == "barre":
        for x in range(0, 320, 40):
            draw.rectangle((x, 0, x + 20, 240), fill="black")
    return img


def test_dedupe_removes_near_duplicates():
    frames = [
        Frame(0, picture("red", "cerchio")),
        Frame(500, picture("red", "cerchio")),
        Frame(1000, picture("blue", "barre")),
    ]
    kept = dedupe(frames)
    assert [f.time_ms for f in kept] == [0, 1000]
