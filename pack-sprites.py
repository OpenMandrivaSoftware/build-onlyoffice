#!/usr/bin/python
# Pack OnlyOffice toolbar sprites without grunt or network access.
#
# web-apps stores one PNG per toolbar icon and compiles the sprite stylesheets
# in the browser from less files that upstream generates with grunt-spritesmith.
# This writes the same PNG sheets and less files. A wipe of the web-apps
# checkout removes the output; install.sh runs this script again.
#
# Layout matches web-apps/build/sprites/Gruntfile.js: top-down, no padding,
# editor icons then common icons, each directory sorted by filename.

import os
import re
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
APPS = os.path.join(ROOT, "web-apps", "apps")
COMMON_RES = os.path.join(APPS, "common", "main", "resources")

EDITORS = (
    "documenteditor",
    "spreadsheeteditor",
    "presentationeditor",
    "pdfeditor",
    "visioeditor",
)
SCALES = ("1x", "1.25x", "1.5x", "1.75x", "2x")
SCALE_ID = {"1x": "100", "1.25x": "125", "1.5x": "150", "1.75x": "175", "2x": "200"}
SIZES = (
    ("small", "iconssmall", ""),
    ("big", "iconsbig", "big"),
    ("huge", "iconshuge", "huge"),
)

TOKEN = re.compile(r"\{\{!--.*?--\}\}|\{\{\{\s*([^}]+?)\s*\}\}\}|\{\{\s*([^}]+?)\s*\}\}", re.S)
LANG_RE = re.compile(r"^(.+)\((\S+)\)$")


def px(n):
    return "%dpx" % n


def rel_url(png_path, less_path):
    rel = os.path.relpath(png_path, os.path.dirname(less_path))
    return rel.replace(os.sep, "/")


def list_pngs(directory):
    if not os.path.isdir(directory):
        return []
    names = [name for name in os.listdir(directory) if name.endswith(".png")]
    names.sort()
    return [os.path.join(directory, name) for name in names]


def render(template, sheet, sprites, helpers):
    def lookup(expr, sprite):
        expr = expr.strip()
        if expr == "escaped_image":
            return sheet["escaped_image"]
        if expr == "name":
            return sprite["name"] if sprite else ""
        if expr == "px.offset_x":
            return sprite["offset_x"]
        if expr == "px.offset_y":
            return sprite["offset_y"]
        if expr in helpers and not expr.startswith("#") and not expr.startswith("/"):
            return helpers[expr]()
        raise RuntimeError("unknown sprite template expression: %s" % expr)

    def render_range(text, sprite):
        out = []
        pos = 0
        while pos < len(text):
            match = TOKEN.search(text, pos)
            if not match:
                out.append(text[pos:])
                break
            out.append(text[pos:match.start()])
            pos = match.end()
            raw = match.group(0)
            if raw.startswith("{{!--"):
                continue
            if raw.startswith("{{{"):
                out.append(lookup(match.group(1), sprite))
                continue
            body = match.group(2).strip()
            if body.startswith("#") or body.startswith("/"):
                raise RuntimeError("block tag reached the variable renderer: %s" % body)
            if body.startswith("{"):
                raise RuntimeError("unparsed tag %s" % raw)
            value = lookup(body, sprite)
            out.append("" if value is None else str(value))
        return "".join(out)

    def find_end(text, start, name):
        depth = 1
        pos = start
        open_re = re.compile(r"\{\{#\s*" + re.escape(name) + r"\b")
        close_re = re.compile(r"\{\{/\s*" + re.escape(name) + r"\s*\}\}")
        while pos < len(text):
            nxt_open = open_re.search(text, pos)
            nxt_close = close_re.search(text, pos)
            if not nxt_close:
                raise RuntimeError("unclosed {{#%s}}" % name)
            if nxt_open and nxt_open.start() < nxt_close.start():
                depth += 1
                pos = nxt_open.end()
                continue
            depth -= 1
            if depth == 0:
                return nxt_close.start(), nxt_close.end()
            pos = nxt_close.end()
        raise RuntimeError("unclosed {{#%s}}" % name)

    def render_blocks(text, sprite):
        out = []
        pos = 0
        while pos < len(text):
            match = re.search(r"\{\{#\s*(\w+)([^}]*)\}\}", text[pos:])
            if not match:
                out.append(render_range(text[pos:], sprite))
                break
            out.append(render_range(text[pos:pos + match.start()], sprite))
            name = match.group(1)
            args = match.group(2).strip()
            block_start = pos + match.end()
            block_end, after = find_end(text, block_start, name)
            # find_end searches absolute indices if we pass text[block_start:]
            inner_end, inner_after = find_end(text[block_start:], 0, name)
            inner = text[block_start:block_start + inner_end]
            pos = block_start + inner_after
            if name == "spritesheet":
                out.append(render_blocks(inner, None))
            elif name == "sprites":
                for item in sprites:
                    out.append(render_blocks(inner, item))
            elif name == "if":
                cond = args
                if cond == "(iesupport)":
                    ok = helpers["iesupport"]()
                elif cond == "(xpsupport)":
                    ok = helpers["xpsupport"]()
                else:
                    raise RuntimeError("unsupported if: %s" % args)
                if ok:
                    out.append(render_blocks(inner, sprite))
            elif name == "extracls":
                out.append(helpers["extracls"]())
            elif name == "spritepostfix":
                out.append(helpers["spritepostfix"]())
            elif name == "parselang":
                sprite_name = sprite["name"] if sprite else ""
                lang = LANG_RE.match(sprite_name)
                if lang:
                    shown = dict(sprite)
                    shown["name"] = lang.group(1)
                    out.append("[applang=%s] %s" % (lang.group(2), render_blocks(inner, shown)))
                else:
                    out.append(render_blocks(inner, sprite))
            else:
                raise RuntimeError("unsupported block {{#%s}}" % name)
        return "".join(out)

    return render_blocks(template, None)


def pack(paths):
    images = []
    for path in paths:
        im = Image.open(path).convert("RGBA")
        images.append((os.path.splitext(os.path.basename(path))[0], im))
    width = max(im.width for _, im in images)
    height = sum(im.height for _, im in images)
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sprites = []
    y = 0
    for name, im in images:
        if im.width != width:
            raise RuntimeError("%s width %s != %s" % (name, im.width, width))
        sheet.paste(im, (0, y))
        sprites.append({
            "name": name,
            "offset_x": px(0),
            "offset_y": px(-y),
        })
        y += im.height
    return sheet, sprites


def source_dirs(editor, scale, ext, mod2):
    mod = "v2/" if mod2 else ""
    sub = scale if not ext else os.path.join(scale, ext)
    editor_dir = os.path.join(APPS, editor, "main", "resources", "img", "toolbar", mod, sub)
    common_dir = os.path.join(COMMON_RES, "img", "toolbar", mod, sub)
    return editor_dir, common_dir


def outputs(editor, scale, sprite_name, mod2):
    res = os.path.join(APPS, editor, "main", "resources")
    mod = "v2/" if mod2 else ""
    png_name = sprite_name + ".png" if scale == "1x" else "%s@%s.png" % (sprite_name, scale)
    less_name = "%s@%s%s.less" % (sprite_name, scale, ".mod2" if mod2 else "")
    png_path = os.path.join(res, "img", mod, png_name)
    less_path = os.path.join(res, "less", "sprites", less_name)
    return png_path, less_path


def template_path(scale, ext):
    sub = scale if not ext else os.path.join(scale, ext)
    return os.path.join(COMMON_RES, "img", "toolbar", sub, ".css.handlebars")


def build_one(editor, scale, kind, sprite_name, ext, mod2):
    editor_dir, common_dir = source_dirs(editor, scale, ext, mod2)
    paths = list_pngs(editor_dir) + list_pngs(common_dir)
    png_path, less_path = outputs(editor, scale, sprite_name, mod2)
    os.makedirs(os.path.dirname(less_path), exist_ok=True)
    if not paths:
        # The editor less file imports this sheet. An empty file lets the
        # compile finish when this editor has no icons of that size.
        if not os.path.exists(less_path) or os.path.getsize(less_path) == 0:
            with open(less_path, "w") as fh:
                fh.write("\n")
        return 0

    tpl = template_path(scale, ext)
    if not os.path.isfile(tpl):
        print("missing template %s" % tpl, file=sys.stderr)
        return 0

    sheet, sprites = pack(paths)
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    sheet.save(png_path, "PNG")
    escaped = rel_url(png_path, less_path)
    helpers = {
        "iesupport": lambda: not mod2,
        "xpsupport": lambda: not mod2,
        "extracls": lambda: ".theme-icons-cls-mod2 " if mod2 else "",
        "spritepostfix": lambda: "%s-%s" % (ext or "small", SCALE_ID[scale]),
    }
    with open(tpl) as fh:
        template = fh.read()
    text = render(template, {"escaped_image": escaped}, sprites, helpers)
    with open(less_path, "w") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")
    return len(paths)


def main():
    total = 0
    sheets = 0
    for editor in EDITORS:
        for mod2 in (False, True):
            for scale in SCALES:
                for kind, sprite_name, ext in SIZES:
                    count = build_one(editor, scale, kind, sprite_name, ext, mod2)
                    if count:
                        sheets += 1
                        total += count
                        print("%s %s %s mod2=%s icons=%d" % (editor, scale, kind, mod2, count))
    print("sheets=%d icons=%d" % (sheets, total))


if __name__ == "__main__":
    main()
