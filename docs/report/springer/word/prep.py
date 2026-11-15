"""Flatten the svproc paper into pandoc-friendly LaTeX with PDF-identical numbering.

Citation numbers come from main.aux (\\bibcite), cross-reference numbers from
\\newlabel, so the Word file cites exactly as the PDF does. Nothing in the paper's
text is edited; only LaTeX layout machinery is rewritten.

usage: prep.py <springer dir> <flattened.tex>
"""
import pathlib
import re
import sys

SRC = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])

aux = (SRC / "main.aux").read_text()
cite = dict(re.findall(r"\\bibcite\{([^}]+)\}\{\{(\d+)\}", aux))
label = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux))

main = (SRC / "main.tex").read_text()

macros = r"""
\newcommand{\sys}{\textsc{StateScout}}
\newcommand{\Forb}{ℱ}
\newcommand{\Req}{ℛ}
\newcommand{\Sig}{\Sigma}
"""

body = ""
for m in re.finditer(r"\\input\{sections/([a-z]+)\}", main):
    body += (SRC / "sections" / f"{m.group(1)}.tex").read_text() + "\n\n"


def cites(m):
    keys = [k.strip() for k in m.group(1).split(",")]
    missing = [k for k in keys if k not in cite]
    if missing:
        raise SystemExit(f"no bibcite for {missing}")
    return "[" + ", ".join(cite[k] for k in keys) + "]"


body = re.sub(r"\\cite\{([^}]+)\}", cites, body)
body = re.sub(r"\\ref\{([^}]+)\}", lambda m: label[m.group(1)], body)
body = re.sub(r"\\label\{[^}]*\}", "", body)
body = re.sub(r"\\paragraph\{([^}]*)\}\s*", r"\\textbf{\1} ", body)

body = body.replace(r"\mathcal F", "ℱ").replace(r"\mathcal R", "ℛ").replace(r"\mathcal{F}", "ℱ").replace(r"\mathcal{R}", "ℛ")
body = re.sub(r"\$_\{?([ℱℛ])\}?\$", r"\\textsubscript{\1}", body)
body = body.replace(r"\checkmark", "✓").replace(r"$\sim$", "∼")
body = body.replace("\\path{", "\\texttt{")

counters = {}


def thm(m):
    env, title, text = m.group(1), m.group(2), m.group(3)
    counters[env] = counters.get(env, 0) + 1
    head = f"{env.capitalize()} {counters[env]}" + (f" ({title})" if title else "")
    return f"\\textbf{{{head}.}} {text.strip()}\n\n"


body = re.sub(r"\\begin\{(definition|proposition)\}(?:\[([^\]]*)\])?(.*?)\\end\{\1\}",
              thm, body, flags=re.S)
body = re.sub(r"\\begin\{proof\}(.*?)\\end\{proof\}",
              lambda m: "\\emph{Proof.} " + m.group(1).strip() + " $\\square$\n\n",
              body, flags=re.S)


def align(m):
    out, n = [], 0
    for r in re.split(r"\\\\", m.group(1)):
        if not r.strip():
            continue
        n += 1
        r = r.replace("&&", r"\qquad ").replace("&", "")
        out.append("\\[ " + r.strip() + r" \qquad (" + str(n) + r") \]")
    return "\n\n".join(out)


body = re.sub(r"\\begin\{align\}(.*?)\\end\{align\}", align, body, flags=re.S)

n_table = [0]


def table(m):
    n_table[0] += 1
    t = m.group(0)
    t = re.sub(r"\\begin\{table\}\[[^\]]*\]", r"\\begin{table}", t)
    t = re.sub(r"\\(setlength|renewcommand)\{[^}]*\}\{[^}]*\}", "", t)
    t = re.sub(r"\\setlength\{\\tabcolsep\}\{[^}]*\}", "", t)
    t = t.replace("\\footnotesize", "").replace("\\centering", "")
    t = re.sub(r"\\begin\{tabular\*\}\{\\textwidth\}\{[^\n]*\}\s*\n",
               "\\\\begin{tabular}{lcccccc}\n", t)
    t = t.replace("\\end{tabular*}", "\\end{tabular}")
    t = re.sub(r"\\begin\{tabular\}\{@\{\}(.*?)@\{\}\}", r"\\begin{tabular}{\1}", t)
    t = re.sub(r"\\caption\{", f"\\\\caption{{\\\\textbf{{Table {n_table[0]}.}} ", t, count=1)
    return t


body = re.sub(r"\\begin\{table\}.*?\\end\{table\}", table, body, flags=re.S)

for junk in (r"\noindent", r"\medskip", r"\smallskip", r"\bigskip"):
    body = body.replace(junk, "")

bbl = (SRC / "main.bbl").read_text()
entries = re.findall(r"\\bibitem\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})",
                     bbl, flags=re.S)
refs_tex = "\\section*{References}\n\n"
for key, text in sorted(entries, key=lambda e: int(cite[e[0]])):
    text = re.sub(r"\s+", " ", text.replace("\\newblock", " ")).strip()
    refs_tex += f"[{cite[key]}]\\quad {text}\n\n"

OUT.write_text("\\documentclass{article}\n" + macros + "\\begin{document}\n" +
               body + "\n" + refs_tex + "\\end{document}\n")
print("flattened:", len(entries), "references;", n_table[0], "tables;", counters)
