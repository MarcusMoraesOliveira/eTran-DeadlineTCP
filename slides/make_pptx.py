"""Builds DeadlineTCP_Fase5.pptx with the same content as deck.html.
Everything is native PowerPoint shapes / tables, so it is editable.
Coordinates are written in the HTML deck's 1280x720 px space (1 px = 9525 EMU)."""
import math
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.dml import MSO_LINE
from pptx.oxml.ns import qn
from lxml import etree

PX = 9525
SANS, MONO = "Calibri", "Consolas"
C = dict(ink="12161C", ink2="4C5563", ink3="7C8594", rule="E2E5EA", box="D5D9E0", soft="F2F4F7",
         a="2A78D6", asoft="E6F0FB", aline="9CC0EC", b="EB6834", bsoft="FDEEE7", good="1F7A3F",
         bad="B3261E", white="FFFFFF", slot="E6E9EE", grid="ECEEF2")
TOTAL = 8
ox, oy = 0, 0  # origin of the current figure (set per slide)


def X(v):
    return ox + v


def Y(v):
    return oy + v


def E(v):
    return Emu(int(round(v * PX)))


def rgb(h):
    return RGBColor.from_string(h)


prs = Presentation()
prs.slide_width, prs.slide_height = E(1280), E(720)
BLANK = prs.slide_layouts[6]


def text(s, x, y, w, h, runs, size=20, color="ink2", bold=False, font=SANS, align="l", anchor="t", lsp=None):
    """runs: str or list of paragraphs; a paragraph is str or list of (text, {opts})."""
    tb = s.shapes.add_textbox(E(x), E(y), E(w), E(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
        if lsp:
            p.line_spacing = lsp
        parts = para if isinstance(para, list) else [(para, {})]
        for t, o in parts:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size) * 0.75)
            f.bold = o.get("bold", bold)
            f.color.rgb = rgb(C.get(o.get("color", color), o.get("color", color)))
    return tb


def svgtext(s, x, y, t, size=16, color="ink2", bold=False, anchor="start", w=520, font=SANS):
    """Place text like SVG <text>: y is the baseline."""
    top = y - size * 0.95
    left = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
    align = {"start": "l", "middle": "c", "end": "r"}[anchor]
    return text(s, left, top, w, size * 1.35, t, size, color, bold, font, align)


def rect(s, x, y, w, h, fill=None, line=None, radius=0, lw=1.2, dash=False):
    shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, E(x), E(y), E(w), E(h))
    if radius:
        shp.adjustments[0] = min(0.5, radius / min(w, h))
    if fill:
        shp.fill.solid(); shp.fill.fore_color.rgb = rgb(C.get(fill, fill))
    else:
        shp.fill.background()
    if line:
        shp.line.color.rgb = rgb(C.get(line, line)); shp.line.width = Pt(lw * 0.75)
        if dash: shp.line.dash_style = MSO_LINE.DASH
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    shp.text_frame.text = ""
    return shp


def arrow(s, x1, y1, x2, y2, color="ink2", w=2, dash=False, head=True):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, E(x1), E(y1), E(x2), E(y2))
    c.line.color.rgb = rgb(C.get(color, color))
    c.line.width = Pt(w * 0.75)
    if dash:
        c.line.dash_style = MSO_LINE.DASH
    if head:
        ln = c.line._get_or_add_ln()
        te = etree.SubElement(ln, qn("a:tailEnd"))
        te.set("type", "triangle"); te.set("w", "med"); te.set("len", "med")
    return c


def poly(s, pts, fill):
    fb = s.shapes.build_freeform(int(pts[0][0] * PX), int(pts[0][1] * PX), scale=1.0)
    fb.add_line_segments([(int(x * PX), int(y * PX)) for x, y in pts[1:]], close=True)
    shp = fb.convert_to_shape()
    shp.fill.solid(); shp.fill.fore_color.rgb = rgb(C.get(fill, fill))
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def header(s, kicker, title, tsize=40):
    text(s, 80, 50, 1120, 24, kicker.upper(), 15, "a", font=MONO)
    text(s, 80, 80, 1120, 110, title, tsize, "ink", True, lsp=1.0)


def footer(s, n, left):
    text(s, 80, 686, 900, 20, left, 13, "ink3", font=MONO)
    text(s, 1000, 686, 200, 20, f"{n} / {TOTAL}", 13, "ink3", font=MONO, align="r")


def new_slide():
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid(); s.background.fill.fore_color.rgb = rgb(C["white"])
    return s


# ---------------- 1. Title ----------------
s = new_slide()
text(s, 80, 278, 1120, 24, "DEADLINETCP NO ETRAN · FASE 5", 15, "a", font=MONO)
text(s, 80, 310, 1120, 70, "DeadlineTCP", 52, "ink", True)
text(s, 80, 392, 1000, 40, "Pacing guiado por deadline na pilha TCP AF_XDP / eBPF do eTran.", 26, "ink2")
footer(s, 1, "DeadlineTCP")

# ---------------- 2. Design ----------------
s = new_slide()
header(s, "Projeto", "Cada fluxo conhece seu prazo e tamanho e ajusta seu ritmo para cumpri-lo")
for i, (f, d) in enumerate([("R_req = bytes restantes / tempo restante", "Taxa necessária para terminar exatamente no prazo"),
                            ("urgência = tempo restante / tempo necessário", "Tempo necessário à taxa disponível. Abaixo de 1, o fluxo já está atrasado")]):
    x = 80 + i * 569
    rect(s, x, 200, 551, 88, "soft", radius=8)
    text(s, x + 20, 214, 515, 26, f, 18, "ink", font=MONO)
    text(s, x + 20, 246, 515, 40, d, 16, "ink2")
modes = [
    ("urgência < 1", "Urgente", "Atrasado. Envia acima da taxa disponível para recuperar o atraso.", "R_available × ganho (≤ 1,5)", False),
    ("folga < 1 RTT", "Moderado", "No prazo, sem margem. Mantém pelo menos a taxa necessária.", "max(taxa CC, 1,25 × R_req)", False),
    ("muita folga", "Normal: ceder", "Adiantado. Envia só o que o prazo exige e deixa o resto do enlace para os outros.", "min(taxa CC, 1,15 × taxa para terminar 10% antes)", True),
]
for i, (when, h, p, r, new) in enumerate(modes):
    x, y, w, hh = 80 + i * 379, 310, 361, 340
    rect(s, x, y, w, hh, "white", "a" if new else "rule", radius=8, lw=2 if new else 1)
    text(s, x + 22, y + 20, w - 44, 22, when, 16, "ink3", font=MONO)
    text(s, x + 22, y + 48, w - 44, 36, h, 26, "ink", True)
    if new:
        rect(s, x + 230, y + 55, 76, 22, "a", radius=3)
        text(s, x + 230, y + 55, 76, 22, "FASE 5", 12, "white", font=MONO, align="c", anchor="m")
    text(s, x + 22, y + 96, w - 44, 120, p, 19, "ink2")
    rect(s, x + 22, y + hh - 92, w - 44, 70, "soft", radius=5)
    text(s, x + 32, y + hh - 84, w - 64, 56, r, 16, "ink", font=MONO, anchor="m")
footer(s, 2, "A política roda a cada intervalo do controle de congestionamento, depois do TIMELY")

# ---------------- 3. Implementation ----------------
s = new_slide()
header(s, "Implementação", "Onde o DeadlineTCP entra no eTran")
ox, oy = 80, 180
cards = [(0, "APLICAÇÃO", "Informa o deadline", "setsockopt com deadline e tamanho do flow. A libetran repassa ao microkernel.", False),
         (410, "MICROKERNEL · SLOW PATH", "Decide o rate", "deadline_cc() roda a cada intervalo de CC e escolhe o modo: urgente, moderado ou normal.", True),
         (820, "eBPF · FAST PATH", "Aplica e mede", "Envia no rate escolhido (timing wheel) e registra bytes enviados e RTT.", True)]
for cx_, tag, title, body, ours in cards:
    rect(s, X(cx_), Y(20), 300, 220, "asoft" if ours else "white", "aline" if ours else "box", radius=10, lw=1.5)
    text(s, X(cx_ + 22), Y(38), 260, 20, tag, 13, "a" if ours else "ink3", font=MONO)
    text(s, X(cx_ + 22), Y(68), 260, 34, title, 24, "ink", True)
    text(s, X(cx_ + 22), Y(112), 260, 120, body, 17, "ink2", lsp=1.15)
arrow(s, X(300), Y(130), X(408), Y(130))
svgtext(s, X(355), Y(112), "deadline,", 14, "ink2", False, "middle", 100)
svgtext(s, X(355), Y(156), "tamanho", 14, "ink2", False, "middle", 100)
arrow(s, X(710), Y(130), X(818), Y(130))
svgtext(s, X(765), Y(118), "rate", 14, "ink2", False, "middle", 100)
arrow(s, X(970), Y(240), X(970), Y(300), "a", 2, dash=True, head=False)
arrow(s, X(970), Y(300), X(560), Y(300), "a", 2, dash=True, head=False)
arrow(s, X(560), Y(300), X(560), Y(242), "a", 2, dash=True)
svgtext(s, X(765), Y(330), "deadline_map: bytes enviados e RTT", 16, "a", False, "middle", 500)
footer(s, 3, "Azul = código novo do DeadlineTCP · também foi preciso corrigir a recuperação de perdas do eTran")

# ---------------- 4. Timing wheel ----------------
s = new_slide()
header(s, "Implementação · pacing dos pacotes", "O eTran guarda cada pacote numa timing wheel até o seu send time", 34)
ox, oy = 80, 175   # svg origin
rect(s, X(250), Y(10), 280, 80, "asoft", "aline", radius=8, lw=1.5)
svgtext(s, X(390), Y(44), "DeadlineTCP", 20, "ink", True, "middle", 260)
svgtext(s, X(390), Y(70), "define o rate de cada flow", 16, "ink2", False, "middle", 260)
arrow(s, X(390), Y(90), X(390), Y(148), "a", 2, dash=True)
rect(s, X(0), Y(170), 190, 100, "white", "box", radius=8, lw=1.5)
svgtext(s, X(95), Y(214), "App", 20, "ink", True, "middle", 180)
svgtext(s, X(95), Y(240), "escreve dados", 16, "ink2", False, "middle", 180)
arrow(s, X(190), Y(220), X(248), Y(220))
rect(s, X(250), Y(150), 280, 140, "soft", "box", radius=8, lw=1.5)
svgtext(s, X(390), Y(190), "eBPF send hook", 20, "ink", True, "middle", 270)
svgtext(s, X(390), Y(224), "send time =", 16, "ink2", False, "middle", 270)
svgtext(s, X(390), Y(250), [[("previous + size ÷ ", {}), ("rate", {"color": "a", "bold": True})]], 16, "ink2", False, "middle", 270)
arrow(s, X(530), Y(220), X(590), Y(220))
cx, cy, ro, ri, N = X(730), Y(220), 125, 80, 32
def pt(r, deg):
    a = math.radians(deg); return (cx + r * math.cos(a), cy + r * math.sin(a))
for k in range(N):
    a0, a1 = k * 360 / N + 1, (k + 1) * 360 / N - 1
    pts = [pt(ro, a0 + (a1 - a0) * j / 6) for j in range(7)] + [pt(ri, a1 - (a1 - a0) * j / 6) for j in range(7)]
    poly(s, pts, "ink" if k == 0 else "slot")
    pk = (["a"] if k <= 9 else []) + (["b"] if k % 4 == 0 and k <= 12 else [])
    for i, col in enumerate(pk):
        px_, py_ = pt(ro + 13 + i * 16, (k + 0.5) * 360 / N)
        rect(s, px_ - 6, py_ - 6, 12, 12, col, radius=2)
svgtext(s, cx, cy - 10, "Timing wheel", 18, "ink", True, "middle", 150)
svgtext(s, cx, cy + 14, "clockwise = later", 14, "ink2", False, "middle", 150)
svgtext(s, cx + ro - 12, cy - 16, "now", 14, "ink", True, "end", 60)
arrow(s, X(876), Y(196), X(938), Y(196))
rect(s, X(940), Y(150), 180, 100, "white", "box", radius=8, lw=1.5)
svgtext(s, X(1030), Y(194), "NIC", 20, "ink", True, "middle", 170)
svgtext(s, X(1030), Y(220), "envia na hora", 16, "ink2", False, "middle", 170)
svgtext(s, X(560), Y(402), "Cada slot vale 500 ns. O pacote espera no slot do seu send time.", 17, "ink2", False, "middle", 900)
rect(s, X(300), Y(422), 13, 13, "a", radius=2)
svgtext(s, X(320), Y(434), "Flow A, rate alto: pacotes próximos", 16, "ink2", w=330)
rect(s, X(660), Y(422), 13, 13, "b", radius=2)
svgtext(s, X(680), Y(434), "Flow B, rate baixo: espaçados", 16, "ink2", w=300)
footer(s, 4, "Não é um heap: o send time é o número do slot, então inserir um pacote é O(1)")

# ---------------- 5. Experiment ----------------
s = new_slide()
header(s, "Experimento", "Dois flows disputam o mesmo gargalo")
ox, oy = 80, 170
rect(s, X(0), Y(10), 320, 220, "white", "box", radius=10, lw=1.5)
svgtext(s, X(24), Y(46), [[("node-4  ", {"bold": True, "color": "ink", "size": 21}), ("emissor", {"color": "ink3", "size": 17})]], 21, w=290)
for i, (nm, dl, soft, col) in enumerate([("Flow A · 100 MB", "deadline 200 ms", "asoft", "a"), ("Flow B · 100 MB", "deadline 500 ms", "bsoft", "b")]):
    yy = 66 + i * 80
    rect(s, X(24), Y(yy), 272, 64, soft, radius=8)
    rect(s, X(24), Y(yy), 6, 64, col)
    svgtext(s, X(44), Y(yy + 28), nm, 19, "ink", True, w=240)
    svgtext(s, X(44), Y(yy + 52), dl, 16, "ink2", w=240)
arrow(s, X(296), Y(98), X(796), Y(98), "a", 4)
arrow(s, X(296), Y(178), X(796), Y(178), "b", 2)
svgtext(s, X(560), Y(134), "enlace de 25G", 18, "ink", True, "middle", 400)
svgtext(s, X(560), Y(158), "A precisa de 4,0 Gb/s · B de 1,6 Gb/s", 15, "ink2", False, "middle", 400)
rect(s, X(800), Y(10), 320, 220, "white", "box", radius=10, lw=1.5)
svgtext(s, X(824), Y(46), [[("node-5  ", {"bold": True, "color": "ink", "size": 21}), ("receptor", {"color": "ink3", "size": 17})]], 21, w=290)
svgtext(s, X(824), Y(104), "gargalo", 15, "ink3", w=280)
svgtext(s, X(824), Y(146), "≈ 7,2 Gb/s", 40, "ink", True, w=290)
svgtext(s, X(824), Y(178), "servidor com uma thread", 16, "ink2", w=280)
svgtext(s, X(824), Y(204), "A + B = 5,6 Gb/s cabe", 16, "ink2", w=280)
text(s, 80, 440, 1120, 28, "Uma execução passa quando:", 19, "ink", True)
for i, t in enumerate(["A tem ≥ 1,1× o goodput de B", "A termina antes de B", "A cumpre o deadline", "B cumpre o deadline"]):
    x = 80 + i * 283.5
    rect(s, x, 478, 269, 86, "soft", radius=8)
    text(s, x + 16, 494, 237, 60, [[(f"{i + 1}  ", {"font": MONO, "color": "a", "size": 16, "bold": True}), (t, {})]], 19, "ink2")
footer(s, 5, "10 execuções por configuração · 6 configurações")

# ---------------- 6. Main result ----------------
s = new_slide()
header(s, "Resultado", "Com prazos, o fluxo urgente termina primeiro e os dois cumprem")
ox, oy = 80, 200
sx = lambda ms: X(150 + ms * 1.24)
for ms in range(0, 501, 100):
    arrow(s, sx(ms), Y(20), sx(ms), Y(340), "grid", 1, head=False)
    svgtext(s, sx(ms), Y(362), f"{ms}" + (" ms" if ms == 500 else ""), 14, "ink3", False, "middle", 80)
svgtext(s, X(770), Y(388), "tempo médio de conclusão, 10 execuções", 14, "ink3", False, "end", 400)
svgtext(s, X(0), Y(56), "Sem prazos", 19, "ink", True, w=150)
svgtext(s, X(0), Y(78), "linha de base", 15, "ink3", w=150)
rect(s, X(150), Y(40), 279 * 1.24, 30, "a", radius=4)
svgtext(s, X(504), Y(61), "A 279 ms · 2,9 Gb/s", 16, "ink2", w=260)
rect(s, X(150), Y(76), 266.4 * 1.24, 30, "b", radius=4)
svgtext(s, X(488), Y(97), "B 266 ms · 3,0 Gb/s", 16, "ink2", w=260)
rect(s, X(150), Y(128), 14, 14, "a", radius=3)
svgtext(s, X(172), Y(140), "Fluxo A (prazo mais cedo)", 15, "ink2", w=240)
rect(s, X(420), Y(128), 14, 14, "b", radius=3)
svgtext(s, X(442), Y(140), "Fluxo B", 15, "ink2", w=120)
svgtext(s, X(0), Y(206), "DeadlineTCP", 19, "ink", True, w=150)
svgtext(s, X(0), Y(228), "prazos A 200, B 500 ms", 15, "ink3", w=150)
rect(s, X(150), Y(190), 195 * 1.24, 30, "a", radius=4)
svgtext(s, X(410), Y(211), "A 195 ms · 4,2 Gb/s", 16, "ink2", w=260)
rect(s, X(150), Y(226), 454.6 * 1.24, 30, "b", radius=4)
svgtext(s, X(702), Y(247), "B 455 ms · 1,8 Gb/s", 16, "white", True, "end", 260)
arrow(s, sx(200), Y(182), sx(200), Y(224), "ink", 2.5, dash=True, head=False)
svgtext(s, sx(200), Y(176), "prazo de A", 13, "ink", False, "middle", 120)
arrow(s, sx(500), Y(222), sx(500), Y(292), "ink", 2.5, dash=True, head=False)
svgtext(s, sx(500), Y(308), "prazo de B", 13, "ink", False, "middle", 120)
for i, (v, k) in enumerate([("2,4×", "goodput de A em relação ao de B"), ("84 ms", "a menos para A terminar, comparado à linha de base"),
                            ("8 / 10", "execuções passam nas quatro condições; B cumpriu o prazo em 10 / 10")]):
    y = 205 + i * 130
    text(s, 920, y, 290, 52, v, 46, "ink", True)
    text(s, 920, y + 58, 290, 60, k, 17, "ink2")
footer(s, 6, "B reduz para a taxa que seu prazo exige; A usa a banda liberada")

# ---------------- 7. Table ----------------
s = new_slide()
header(s, "Resultado", "Funciona quando os prazos são viáveis")
rows = [["Prazos A / B", "O que testa", "A primeiro", "A cumpriu", "B cumpriu", "Passou"],
        ["200 / 500 ms", "Viável", "10 / 10", "8 / 10", "10 / 10", "8 / 10"],
        ["200 / 500 ms, A começa depois", "Ordem de início", "10 / 10", "5 / 10", "10 / 10", "5 / 10"],
        ["150 / 400 ms", "Exige mais do que o enlace tem", "10 / 10", "0 / 10", "9 / 10", "0 / 10"],
        ["200 / 200 ms", "Prazos iguais", "dividido", "1 / 10", "0 / 10", "0 / 10"]]
widths = [300, 330, 130, 120, 120, 120]
tshape = s.shapes.add_table(len(rows), len(widths), E(80), E(180), E(sum(widths)), E(56 * len(rows)))
tbl = tshape.table
tblPr = tshape._element.graphic.graphicData.tbl.tblPr
for attr in ("bandRow", "firstRow"):
    tblPr.set(attr, "0")
style = tblPr.find(qn("a:tableStyleId"))
if style is not None:
    style.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # "No Style, No Grid"
for j, wd in enumerate(widths):
    tbl.columns[j].width = E(wd)
for i, row in enumerate(rows):
    tbl.rows[i].height = E(56)
    for j, val in enumerate(row):
        cell = tbl.cell(i, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(C["asoft"] if i in (1, 2) else C["white"])
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = cell.margin_right = E(14)
        tf = cell.text_frame; tf.text = ""
        r = tf.paragraphs[0].add_run(); r.text = val
        f = r.font
        if i == 0:
            f.name, f.size, f.color.rgb = MONO, Pt(14 * 0.75), rgb(C["ink3"])
        else:
            f.name = MONO if j >= 2 else SANS
            f.size = Pt(19 * 0.75)
            col = "ink"
            if j == 5: col, f.bold = ("good" if i in (1, 2) else "bad"), True
            if j == 2 and val.startswith("10"): col, f.bold = "good", True
            f.color.rgb = rgb(C[col])
        # bottom border only
        tcPr = cell._tc.get_or_add_tcPr()
        for side in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
            ln = etree.SubElement(tcPr, qn(side))
            if side == "a:lnB":
                ln.set("w", str(9525))
                sf = etree.SubElement(ln, qn("a:solidFill")); c_ = etree.SubElement(sf, qn("a:srgbClr")); c_.set("val", C["rule"])
            else:
                ln.set("w", "0"); etree.SubElement(ln, qn("a:noFill"))
        # schema order: borders must come before the fill element
        fill = tcPr.find(qn("a:solidFill"))
        if fill is not None:
            tcPr.remove(fill); tcPr.append(fill)
text(s, 80, 490, 1120, 60, "Os casos inviáveis falham como esperado: não há banda para os dois prazos. A ainda tem prioridade quando B tem folga para ceder.", 19, "ink2")
footer(s, 7, "10 execuções cada · 100 MB por fluxo")

# ---------------- 8. Takeaways ----------------
s = new_slide()
header(s, "Conclusões", "A Fase 5 funciona para prazos viáveis; restam algumas limitações")
cols = [("O que funciona", ["Um fluxo com folga cede banda a um mais urgente",
                            "O fluxo urgente recebe cerca de 2,4× o goodput e termina primeiro",
                            "O fluxo que cede ainda cumpre o próprio prazo"]),
        ("Limitações e próximos passos", ["Um fluxo sem prazo nunca cede. Precisa de coordenação entre fluxos.",
                                          "A recuperação de perdas do eTran ainda trava em algumas execuções (36 repetidas). A linha de base trava mais.",
                                          "O prazo de A é apertado: as perdas são de poucos ms. Ajustar a margem de cessão."])]
for i, (h, items) in enumerate(cols):
    x = 80 + i * 584
    text(s, x, 220, 536, 32, h, 22, "ink", True)
    text(s, x, 266, 536, 360, [[("•  ", {"color": "ink3"}), (t, {})] for t in items], 20, "ink2", lsp=1.25)
footer(s, 8, "DeadlineTCP")

out = "/users/marcusVM/eTran-DeadlineTCP/slides/DeadlineTCP_Fase5.pptx"
import os
os.makedirs(os.path.dirname(out), exist_ok=True)
prs.save(out)
print("saved", out)
