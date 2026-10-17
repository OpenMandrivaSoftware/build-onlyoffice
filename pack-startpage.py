#!/usr/bin/python
# Build the desktop start page without grunt or network access.
#
# DesktopEditors loads <install>/index.html as the OnlyOffice tab. Upstream
# produces that file with grunt (less, svg sprites, concatenation). This
# writes the symbol sprites the page expects, builds the 1.25/1.5/1.75 PNG
# sprite stylesheets the sidebar uses, and installs index.html so its relative URLs
# point at the loginpage tree. It also writes the blank docx/xlsx/pptx files
# CreateLocalFile converts when the start page asks for a new document.
#
# A wipe of desktop-apps removes the generated sprites. install.sh runs this
# script again.

import base64
import glob
import os
import subprocess
import sys
import zipfile

from lxml import etree
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
LOGIN = os.path.join(ROOT, "desktop-apps", "common", "loginpage")
IMG = os.path.join(LOGIN, "res", "img")
GENERATED = os.path.join(IMG, "generated")
CSS = os.path.join(LOGIN, "src", "css")
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Same groups as loginpage/build/sprites/sprites.js. The id of each symbol
# is the file name, which is what the page's <use href="#..."> looks up.
SPRITES = (
    ("connect.svg", "connect*.svg"),
    ("welcome.svg", "welcome*.svg"),
    ("formats.svg", "formats-svg/*.svg"),
    ("common.svg", "common-svg/*.svg"),
    ("update_status.svg", "update_status/*.svg"),
    ("logo.svg", "idx-logo*.svg"),
    ("templatetype.svg", "template-type/*.svg"),
    ("toolicons.svg", "toolicons/1x/*.svg"),
    ("toolicons20.svg", "toolicons20/1x/*.svg"),
)

# At devicePixelRatio 1.25, 1.5 and 1.75 the page hides the SVG symbols and
# paints these PNG sheets instead (htmlutils.js adds pixel-ratio__* on body).
# Xft.dpi 144 is 1.5, which is this machine. An empty sheet leaves the
# sidebar icon boxes blank.
RASTER_SETS = (
    # (png directory, less file stem, icon class, rule that carries the image)
    ("toolicons", "toolicons", "tool-icon", ".tool-icon, .menu__icon"),
    ("toolicons20", "toolicons20", "tool-icon__20", ".tool-icon__20"),
)
RASTER_SCALES = (1.25, 1.5, 1.75)

SKIP_ATTRS = {"width", "height", "id"}


def sprite(pattern, dest):
    files = sorted(glob.glob(os.path.join(IMG, pattern)))
    files = [f for f in files if os.path.isfile(f) and not f.startswith(GENERATED + os.sep)]
    if not files:
        raise SystemExit("no icons for %s" % pattern)
    nsmap = {None: SVG_NS, "xlink": XLINK_NS}
    root = etree.Element("{%s}svg" % SVG_NS, nsmap=nsmap)
    root.set("style", "position:absolute;width:0;height:0")
    seen = set()
    parser = etree.XMLParser(recover=False, remove_blank_text=False)
    for path in files:
        doc = etree.parse(path, parser)
        svg = doc.getroot()
        symbol_id = os.path.splitext(os.path.basename(path))[0]
        if symbol_id in seen:
            raise SystemExit("duplicate symbol id %s" % symbol_id)
        seen.add(symbol_id)
        symbol = etree.Element("{%s}symbol" % SVG_NS)
        symbol.set("id", symbol_id)
        for key, value in svg.attrib.items():
            local = key.rsplit("}", 1)[-1]
            if local in SKIP_ATTRS or local.startswith("xmlns"):
                continue
            symbol.set(key, value)
        if "viewBox" not in symbol.attrib and not any(k.endswith("viewBox") for k in symbol.attrib):
            symbol.set("viewBox", "0 0 24 24")
        for child in list(svg):
            symbol.append(child)
        root.append(symbol)
    os.makedirs(GENERATED, exist_ok=True)
    etree.ElementTree(root).write(dest, xml_declaration=True, encoding="utf-8")
    return len(seen)


def _px(value):
    rounded = round(value)
    if abs(value - rounded) < 1e-6:
        return str(int(rounded))
    return ("%.4f" % value).rstrip("0").rstrip(".")


def write_raster_sprites():
    # grunt-spritesmith is not available offline. Stack the per-icon PNGs the
    # same way (top-down, no padding) and write the less it would write.
    # offset_y in that template is already negative; background-position-y
    # then selects the row. Positions stay inside the pixel-ratio block so a
    # 1.75 sheet cannot override the 1.5 one.
    os.makedirs(GENERATED, exist_ok=True)
    os.makedirs(CSS, exist_ok=True)
    for dirname, less_stem, icon_class, image_selectors in RASTER_SETS:
        for scale in RASTER_SCALES:
            folder = os.path.join(IMG, dirname, "%sx" % _px(scale))
            names = sorted(
                name for name in os.listdir(folder) if name.endswith(".png")
            )
            if not names:
                raise SystemExit("no png icons in %s" % folder)
            icons = []
            for name in names:
                image = Image.open(os.path.join(folder, name)).convert("RGBA")
                icons.append((os.path.splitext(name)[0], image))
            width = max(image.width for _name, image in icons)
            height = sum(image.height for _name, image in icons)
            sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            rows = []
            y = 0
            for name, image in icons:
                sheet.paste(image, (0, y))
                rows.append((name, -y / scale))
                y += image.height
            sprite_name = "%s@%sx.png" % (less_stem, _px(scale))
            sprite_path = os.path.join(GENERATED, sprite_name)
            sheet.save(sprite_path, "PNG")
            with open(sprite_path, "rb") as handle:
                encoded = base64.b64encode(handle.read()).decode("ascii")
            ratio = "pixel-ratio__%s" % _px(scale).replace(".", "_")
            lines = [
                ".%s {" % ratio,
                "    %s {" % image_selectors,
                '        background-image: url("data:image/png;base64,%s");' % encoded,
                "        background-repeat: no-repeat;",
                "        background-size: %spx auto;" % _px(width / scale),
                "    }",
            ]
            for name, offset in rows:
                lines.append("    .%s.%s {" % (icon_class, name))
                lines.append("        background-position-y: %spx;" % _px(offset))
                lines.append("    }")
            lines.append("}")
            # styles.less shifts the dark theme with a positive
            # background-position-x. That moves a 2-up sheet out of the
            # icon box, so the sidebar glyphs disappear on the dark theme.
            # The white glyph is the right half; pull the sheet left by one
            # icon. theme-type-dark and pixel-ratio are both on body, so the
            # ratio class has to be compound with the theme, not a descendant.
            half = width / scale / 2
            prefixed = ", ".join(
                ".%s.theme-type-dark %s" % (ratio, selector.strip())
                for selector in image_selectors.split(",")
                if selector.strip()
            )
            lines.append("%s {" % prefixed)
            lines.append("    background-position-x: -%spx;" % _px(half))
            lines.append("}")
            lines.append("")
            less_name = "%s@%sx.less" % (less_stem, _px(scale))
            with open(os.path.join(CSS, less_name), "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))


def check_less():
    styles = os.path.join(CSS, "styles.less")
    # The shipped less.js is the browser build. Stub the DOM and file XHR
    # so the same compiler the page uses can be checked from install.sh.
    script = r"""
const fs = require("fs");
global.window = global;
global.less = { onReady: false };
const scriptTag = { dataset: {} };
global.document = {
  currentScript: scriptTag,
  getElementsByTagName() { return [scriptTag]; },
  getElementById() { return null; },
  createElement() { return { styleSheet: null, setAttribute() {}, appendChild() {}, childNodes: [] }; },
  createTextNode(text) { return { nodeValue: text }; },
  head: { appendChild() {}, removeChild() {} }
};
global.navigator = { userAgent: "node" };
global.location = { protocol: "file:", href: "file:///index.html", hostname: "", port: "", hash: "" };
function XMLHttpRequest() {}
XMLHttpRequest.prototype.open = function(_method, url, async) {
  this._url = url;
  this._async = async !== false;
};
XMLHttpRequest.prototype.setRequestHeader = function() {};
XMLHttpRequest.prototype.overrideMimeType = function() {};
XMLHttpRequest.prototype.getAllResponseHeaders = function() { return ""; };
XMLHttpRequest.prototype.getResponseHeader = function() { return null; };
XMLHttpRequest.prototype.send = function() {
  let path = String(this._url || "").replace(/^file:\/\//, "");
  try {
    this.responseText = fs.readFileSync(path, "utf8");
    this.status = 200;
    this.statusText = "OK";
  } catch (err) {
    this.status = 404;
    this.statusText = "missing";
    this.responseText = "";
    console.error("missing", this._url);
  }
  this.readyState = 4;
  const fire = () => {
    if (this.onreadystatechange) this.onreadystatechange();
    if (this.onload) this.onload();
  };
  if (this._async === false) fire();
  else process.nextTick(fire);
};
global.XMLHttpRequest = XMLHttpRequest;
const less = require(process.argv[1]);
const file = process.argv[2];
less.render(fs.readFileSync(file, "utf8"), {filename: file, javascriptEnabled: false})
  .then(out => { if (!out.css || out.css.length < 1000) process.exit(2); })
  .catch(err => { console.error(err); process.exit(1); });
"""
    less_js = os.path.join(LOGIN, "vendor", "less", "dist", "less.js")
    result = subprocess.run(
        ["node", "-e", script, less_js, styles],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit("start page less failed to compile")


def rewrite_index():
    src = os.path.join(LOGIN, "src", "index.html")
    with open(src, encoding="utf-8") as handle:
        html = handle.read()
    html = html.replace('href="css/', 'href="loginpage/src/css/')
    html = html.replace('href="../', 'href="loginpage/')
    html = html.replace('src="./', 'src="loginpage/src/')
    html = html.replace('src="../', 'src="loginpage/')

    out = []
    for line in html.splitlines(keepends=True):
        if 'src="' in line and "loginpage/" not in line and "src=\"data:" not in line:
            line = line.replace('src="', 'src="loginpage/src/', 1)
        out.append(line)
    html = "".join(out)
    # index.html lives in the install root. providers/ is linked there, so
    # the debug page's ".." (which pointed at loginpage/) would leave the
    # install directory. panelconnect.js sets "." on Linux and this line
    # runs after it, so it has to agree.
    html = html.replace("window.relpath = '..'", "window.relpath = '.'")
    return html


def write_zip(path, parts):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            text = body.strip() + "\n"
            archive.writestr(name, text)


def docx_parts():
    return {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        "word/_rels/document.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
</Relationships>""",
        "word/document.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t></w:t></w:r></w:p>
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>""",
        "word/styles.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr>
      <w:rFonts w:ascii="Liberation Serif" w:hAnsi="Liberation Serif" w:cs="Liberation Serif"/>
      <w:sz w:val="24"/><w:szCs w:val="24"/>
    </w:rPr></w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
</w:styles>""",
        "word/settings.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:zoom w:percent="100"/></w:settings>""",
        "docProps/core.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title></dc:title></cp:coreProperties>""",
        "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>OnlyOffice</Application></Properties>""",
    }


def xlsx_parts():
    return {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
        "xl/worksheets/sheet1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>""",
        "xl/styles.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>""",
        "docProps/core.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title></dc:title></cp:coreProperties>""",
        "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>OnlyOffice</Application></Properties>""",
    }


def pptx_parts():
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    tree = (
        "<p:spTree>"
        "<p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
        "<p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/>"
        "<a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>"
        "</p:spTree>"
    )
    return {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>
  <Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>
  <Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        "ppt/presentation.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>""" % (a, r, p),
        "ppt/_rels/presentation.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/>
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/>
</Relationships>""",
        "ppt/slideMasters/slideMaster1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">
  <p:cSld>%s</p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
</p:sldMaster>""" % (a, r, p, tree),
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>""",
        "ppt/slideLayouts/slideLayout1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="%s" xmlns:r="%s" xmlns:p="%s" type="blank" preserve="1">
  <p:cSld name="Blank">%s</p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>""" % (a, r, p, tree),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>""",
        "ppt/slides/slide1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">
  <p:cSld>%s</p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>""" % (a, r, p, tree),
        "ppt/slides/_rels/slide1.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>""",
        "ppt/theme/theme1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="%s" name="Office">
  <a:themeElements>
    <a:clrScheme name="Office">
      <a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
      <a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="44546A"/></a:dk2>
      <a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>
      <a:accent1><a:srgbClr val="4472C4"/></a:accent1>
      <a:accent2><a:srgbClr val="ED7D31"/></a:accent2>
      <a:accent3><a:srgbClr val="A9D08E"/></a:accent3>
      <a:accent4><a:srgbClr val="FFC000"/></a:accent4>
      <a:accent5><a:srgbClr val="5B9BD5"/></a:accent5>
      <a:accent6><a:srgbClr val="70AD47"/></a:accent6>
      <a:hlink><a:srgbClr val="0563C1"/></a:hlink>
      <a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Office">
      <a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
      <a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Office">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>""" % a,
        "ppt/presProps.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentationPr xmlns:p="%s"/>""" % p,
        "ppt/viewProps.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:viewPr xmlns:a="%s" xmlns:p="%s"><p:normalViewPr><p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/></p:normalViewPr><p:slideViewPr><p:cSldViewPr><p:cViewPr varScale="1"><p:scale><a:sx n="100" d="100"/><a:sy n="100" d="100"/></p:scale><p:origin x="0" y="0"/></p:cViewPr></p:cSldViewPr></p:slideViewPr></p:viewPr>""" % (a, p),
        "ppt/tableStyles.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:tblStyleLst xmlns:a="%s" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>""" % a,
        "docProps/core.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title></dc:title></cp:coreProperties>""",
        "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>OnlyOffice</Application></Properties>""",
    }


def write_templates(instdir):
    empty = os.path.join(instdir, "converter", "empty")
    folders = (empty, os.path.join(empty, "en-US"))
    parts = {
        "new.docx": docx_parts(),
        "new.xlsx": xlsx_parts(),
        "new.pptx": pptx_parts(),
    }
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        for name, body in parts.items():
            write_zip(os.path.join(folder, name), body)


def install(instdir):
    os.makedirs(instdir, exist_ok=True)
    link = os.path.join(instdir, "loginpage")
    if os.path.islink(link) or os.path.exists(link):
        if os.path.islink(link) or not os.path.isdir(link):
            os.remove(link)
        else:
            raise SystemExit("%s exists and is not a symlink" % link)
    os.symlink(LOGIN, link)
    index = os.path.join(instdir, "index.html")
    with open(index, "w", encoding="utf-8") as handle:
        handle.write(rewrite_index())
    write_templates(instdir)


def main():
    instdir = None
    args = sys.argv[1:]
    if "--instdir" in args:
        instdir = args[args.index("--instdir") + 1]
    total = 0
    for name, pattern in SPRITES:
        count = sprite(pattern, os.path.join(GENERATED, name))
        total += count
        print("%s %d" % (name, count))
    write_raster_sprites()
    check_less()
    print("less ok, symbols %d" % total)
    if instdir:
        install(instdir)
        print("start page installed in %s" % instdir)


if __name__ == "__main__":
    main()
