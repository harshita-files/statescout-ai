"""Style pandoc's raw.docx like the svproc PDF and add the title block.

usage: build.py raw.docx ../main.tex out.docx
Requires python-docx (run through `uv run --with python-docx`).
"""
import copy
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

RAW, TEX, OUT = sys.argv[1:4]
tex = open(TEX).read()

FONT = "Times New Roman"
MONO = "Courier New"

TITLE = "StateScout: Auditing What a User Interface Must Not Contain, and What It Must"
RUNNING_TITLE = "StateScout: Policy-Aware Auditing of Web UIs"
DEPT = ("Department of Computer Science and Engineering, Amrita School of Computing "
        "Coimbatore, Amrita Vishwa Vidyapeetham, India")
PEOPLE = [
    ("Kavinraj S", "cb.sc.u4cse23329@cb.students.amrita.edu"),
    ("Harshita R", "cb.sc.u4cse23028@cb.students.amrita.edu"),
    ("Sanjay A R", "cb.sc.u4cse23052@cb.students.amrita.edu"),
    ("Jai Subiksha T", "cb.sc.u4cse23327@cb.students.amrita.edu"),
    ("Sathiya R R", "rr_sathiya@cb.amrita.edu"),
]

# ---- abstract and keywords straight from main.tex -----------------------------------
def clean(s):
    s = re.sub(r"%.*", "", s)
    s = s.replace("\\sys{}", "\x00SC\x00").replace("\\sys", "\x00SC\x00")
    s = s.replace("~", "\u00a0").replace("---", "\u2014").replace("--", "\u2013")
    s = re.sub(r"``", "\u201c", s)
    s = re.sub(r"''", "\u201d", s)
    return re.sub(r"\s+", " ", s).strip()

abstract = clean(re.search(r"\\begin\{abstract\}(.*?)\\keywords", tex, re.S).group(1))
keywords = clean(re.search(r"\\keywords\{(.*?)\}\s*\\end\{abstract\}", tex, re.S).group(1))

doc = Document(RAW)

# ---- page setup (the PDF text block, on US Letter) ------------------------------------
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.left_margin = sec.right_margin = Inches(1.85)
sec.top_margin, sec.bottom_margin = Inches(1.3), Inches(1.5)
sec.header_distance = Inches(0.8)

# ---- styles ----------------------------------------------------------------------------
def setfont(style, size=None, bold=None, italic=None, name=FONT, color=True):
    f = style.font
    f.name = name
    rpr = style.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.append(rf)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(a), name)
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        if rf.get(qn(a)) is not None:
            del rf.attrib[qn(a)]
    if size:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    if color:
        f.color.rgb = RGBColor(0, 0, 0)

st = doc.styles
for name in ("Normal", "Body Text", "First Paragraph", "Compact", "Table Caption",
             "Block Text", "Bibliography", "Footnote Text"):
    if name in [s.name for s in st]:
        setfont(st[name], size=10)

def para_fmt(style, align=None, first=None, before=0, after=0, line=None, left=None):
    pf = style.paragraph_format
    if align is not None:
        pf.alignment = align
    if first is not None:
        pf.first_line_indent = Inches(first)
    if left is not None:
        pf.left_indent = Inches(left)
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    if line:
        pf.line_spacing = Pt(line)

J = WD_ALIGN_PARAGRAPH.JUSTIFY
para_fmt(st["Normal"], J, line=12)
para_fmt(st["Body Text"], J, first=0.17, line=12)
para_fmt(st["First Paragraph"], J, first=0, line=12)
para_fmt(st["Compact"], WD_ALIGN_PARAGRAPH.LEFT, first=0, left=0, line=11, before=0, after=0)
setfont(st["Compact"], size=8)
para_fmt(st["Table Caption"], J, first=0, before=6, after=4, line=11)
setfont(st["Table Caption"], size=9, italic=False)

for lvl, size, before, after in ((1, 12, 18, 8), (2, 10, 12, 6), (3, 10, 8, 4)):
    h = st[f"Heading {lvl}"]
    setfont(h, size=size, bold=True, italic=False)
    para_fmt(h, WD_ALIGN_PARAGRAPH.LEFT, first=0, before=before, after=after, line=None)
    h.paragraph_format.keep_with_next = True

for cs in ("Verbatim Char",):
    if cs in [s.name for s in st]:
        setfont(st[cs], size=9, name=MONO, color=False)

# ---- bibliography paragraphs (the last block) and list items ------------------------------
in_refs = False
for p in doc.paragraphs:
    if p.style.name == "Heading 1" and p.text.strip() == "References":
        in_refs = True
        continue
    if in_refs:
        p.paragraph_format.first_line_indent = Inches(-0.3)
        p.paragraph_format.left_indent = Inches(0.3)
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for r in p.runs:
            r.font.size = Pt(8)
            r.font.name = FONT

# ---- tables: booktabs style, small text, caption above ------------------------------------
def set_borders(tbl):
    tblPr = tbl._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    b = OxmlElement("w:tblBorders")
    for edge, sz in (("top", 12), ("bottom", 12)):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), str(sz))
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "000000")
        b.append(e)
    tblPr.append(b)
    # rule under the header row
    for cell in tbl.rows[0].cells:
        tcPr = cell._tc.get_or_add_tcPr()
        tb = OxmlElement("w:tcBorders")
        bt = OxmlElement("w:bottom")
        bt.set(qn("w:val"), "single")
        bt.set(qn("w:sz"), "6")
        bt.set(qn("w:space"), "0")
        bt.set(qn("w:color"), "000000")
        tb.append(bt)
        tcPr.append(tb)

TEXT_WIDTH = 4.8  # inches, the PDF's text block


def set_widths(tbl):
    """Fixed layout. Each column gets at least its longest word; spare width goes to
    columns whose cells are long text, in proportion to how much more they want."""
    CH, PAD = 0.085, 0.34          # inches per character at 8 pt, cell padding
    ncol = len(tbl.columns)
    need, prefer = [], []
    for ci in range(ncol):
        longest_word, longest_cell = 0, 0
        for row in tbl.rows:
            text = row.cells[ci].text.strip()
            longest_cell = max(longest_cell, len(text))
            longest_word = max([longest_word] + [len(w) for w in text.split()])
        need.append(longest_word * CH + PAD)
        prefer.append(min(longest_cell, 34) * CH + PAD)
    widths = need[:]
    spare = TEXT_WIDTH - sum(widths)
    if spare < 0:                  # scale down proportionally
        widths = [w * TEXT_WIDTH / sum(widths) for w in widths]
    else:
        gap = [max(p - n, 0) for p, n in zip(prefer, need)]
        tot = sum(gap)
        if tot:
            give = min(spare, tot)
            widths = [n + give * g / tot for n, g in zip(need, gap)]
        extra = TEXT_WIDTH - sum(widths)
        if extra > 0.01:           # table is narrower than the text block: centre it
            pass
    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    for old in tblPr.findall(qn("w:tblW")):
        tblPr.remove(old)
    tw = OxmlElement("w:tblW")
    tw.set(qn("w:w"), str(int(sum(widths) * 1440)))
    tw.set(qn("w:type"), "dxa")
    tblPr.append(tw)
    for old in tblPr.findall(qn("w:tblLayout")):
        tblPr.remove(old)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    grid = tbl._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths):
        gc.set(qn("w:w"), str(int(w * 1440)))
    for row in tbl.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = Inches(w)


for tbl in doc.tables:
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_widths(tbl)
    set_borders(tbl)
    for row in tbl.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(1)
                for r in p.runs:
                    r.font.size = Pt(8)
                    r.font.name = FONT if "Verbatim" not in (r.style.name if r.style else "") else MONO
    for cell in tbl.rows[0].cells:
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.bold = True

# ---- title block, inserted before the first body paragraph ---------------------------------
body_first = doc.paragraphs[0]

def new_par(text="", size=10, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER,
            before=0, after=0, left=None, right=None, style="Normal"):
    p = body_first.insert_paragraph_before("", style=style)
    p.paragraph_format.alignment = align
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(before), Pt(after)
    p.paragraph_format.first_line_indent = Inches(0)
    if left is not None:
        p.paragraph_format.left_indent = Inches(left)
    if right is not None:
        p.paragraph_format.right_indent = Inches(right)
    if text:
        add_runs(p, text, size, bold)
    return p

def add_runs(p, text, size, bold=False, italic=False):
    for i, part in enumerate(text.split("\x00SC\x00")):
        if i:
            r = p.add_run("StateScout")
            r.font.small_caps = True
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.name = FONT
        if part:
            r = p.add_run(part)
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.italic = italic
            r.font.name = FONT

# title: "StateScout" in small caps
t = new_par(size=14, bold=True, before=0, after=14)
add_runs(t, "\x00SC\x00: Auditing What a User Interface Must Not Contain, and What It Must", 14, True)

# authors with superscript institute numbers
a = new_par(before=0, after=8)
for i, (name, _) in enumerate(PEOPLE):
    r = a.add_run(name)
    r.font.size = Pt(10)
    r.font.name = FONT
    s = a.add_run(str(i + 1))
    s.font.superscript = True
    s.font.size = Pt(10)
    s.font.name = FONT
    sep = ", and " if i == len(PEOPLE) - 2 else (", " if i < len(PEOPLE) - 2 else "")
    if sep:
        x = a.add_run(sep)
        x.font.size = Pt(10)
        x.font.name = FONT

# one institute line per author: Name / Department / mail
for i, (name, mail) in enumerate(PEOPLE):
    p = new_par(before=3, after=0)
    n = p.add_run(str(i + 1))
    n.font.superscript = True
    n.font.size = Pt(9)
    n.font.name = FONT
    r = p.add_run(" " + DEPT)
    r.font.size = Pt(9)
    r.font.name = FONT
    m = new_par(mail, size=9, before=0, after=0)
    for r in m.runs:
        r.font.name = MONO
        r.font.size = Pt(8.5)

# abstract and keywords, inset like the template
ab = new_par(before=22, after=0, align=J, left=0.4, right=0.4)
r = ab.add_run("Abstract. ")
r.font.bold = True
r.font.size = Pt(9)
r.font.name = FONT
add_runs(ab, abstract, 9)
ab.paragraph_format.line_spacing = Pt(11)
kw = new_par(before=8, after=14, align=J, left=0.4, right=0.4)
r = kw.add_run("Keywords: ")
r.font.bold = True
r.font.size = Pt(9)
r.font.name = FONT
add_runs(kw, keywords, 9)
kw.paragraph_format.line_spacing = Pt(11)

# ---- small caps for the product name in the body --------------------------------------------
for p in doc.paragraphs:
    for r in list(p.runs):
        if "StateScout" in r.text and r.text.strip() != "StateScout" and not r.font.small_caps:
            pass  # left as plain text; the macro was expanded before this step

# ---- running headers: odd = short title + page, even = page; none on page 1 ----------------
def add_field(par, code):
    run = par.add_run()
    for kind, txt in (("begin", None), (None, code), ("end", None)):
        if kind:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            run._r.append(fc)
        else:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = txt
            run._r.append(it)
    run.font.size = Pt(9)
    run.font.name = FONT

sec.different_first_page_header_footer = True
settings = doc.settings.element
if settings.find(qn("w:evenAndOddHeaders")) is None:
    settings.append(OxmlElement("w:evenAndOddHeaders"))

def tabbed(par, left_text, right_text, right_pos=Inches(4.8)):
    pPr = par._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "right")
    tab.set(qn("w:pos"), str(int(right_pos.twips)))
    tabs.append(tab)
    pPr.append(tabs)

hdr_odd = sec.header
hp = hdr_odd.paragraphs[0]
hp.text = ""
tabbed(hp, "", "")
r = hp.add_run(RUNNING_TITLE + "\t")
r.font.size = Pt(9)
r.font.name = FONT
add_field(hp, "PAGE")

hdr_even = sec.even_page_header
ep = hdr_even.paragraphs[0]
ep.text = ""
add_field(ep, "PAGE")

doc.core_properties.title = TITLE
doc.core_properties.author = ", ".join(n for n, _ in PEOPLE)
doc.save(OUT)
print("saved", OUT)
