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


def test_playlists_are_rejected():
    from extractors.media import is_playlist, process

    assert is_playlist(b"#EXTM3U\n#EXT-X-VERSION:3\nfile:///proc/self/environ")
    assert is_playlist(b"ffconcat version 1.0\nfile /etc/passwd")
    assert not is_playlist(b"\x00\x00\x00\x18ftypmp42")
    result = process(b"#EXTM3U\nhttp://example.com/x.ts", "video")
    assert result.items == [] and "playlist" in result.errors[0]


def test_ffmpeg_only_reads_local_files():
    import inspect

    from extractors import media

    source = inspect.getsource(media)
    assert source.count("-protocol_whitelist") == 3
