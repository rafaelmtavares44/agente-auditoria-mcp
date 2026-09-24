"""Exporta docs/relatorio/relatorio.md -> relatorio.html -> relatorio.pdf (A4).

Reprodutível e sem ferramentas pagas:
  1) Markdown -> HTML com o pacote `markdown` (pip install -r requirements.txt);
  2) HTML -> PDF com um navegador Chromium em modo headless
     (Microsoft Edge já vem no Windows; no Linux/macOS use Chrome/Chromium).

Uso (a partir da pasta do projeto):
    .\\.venv\\Scripts\\python.exe docs\\relatorio\\build_pdf.py
    python docs/relatorio/build_pdf.py --browser "C:\\caminho\\para\\msedge.exe"

Ao final, informa o número de páginas (o enunciado pede 3 a 5).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
SRC = HERE / "relatorio.md"
CSS = HERE / "estilo.css"
HTML_OUT = HERE / "relatorio.html"
PDF_OUT = HERE / "relatorio.pdf"

CANDIDATES = [
    os.environ.get("BROWSER_PATH", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
PATH_NAMES = ["msedge", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]


def find_browser(explicit: str | None) -> str:
    for c in [explicit or "", *CANDIDATES]:
        if c and Path(c).is_file():
            return c
    for name in PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("Navegador Chromium/Edge não encontrado. Informe --browser ou BROWSER_PATH.")


def build_html() -> Path:
    body = markdown.markdown(SRC.read_text(encoding="utf-8"),
                             extensions=["tables", "fenced_code", "sane_lists", "attr_list"])
    css = CSS.read_text(encoding="utf-8")
    html = (f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            f"<title>Relatório Técnico — Agente de Auditoria MCP</title><style>{css}</style></head>"
            f"<body>{body}</body></html>")
    HTML_OUT.write_text(html, encoding="utf-8")
    return HTML_OUT


def count_pages(pdf: Path) -> int:
    try:
        from pypdf import PdfReader  # opcional
        return len(PdfReader(str(pdf)).pages)
    except ImportError:
        data = pdf.read_bytes()
        return len(re.findall(rb"/Type\s*/Page(?!s)", data))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", help="Caminho do Edge/Chrome/Chromium")
    args = ap.parse_args()
    html = build_html()
    browser = find_browser(args.browser)
    with tempfile.TemporaryDirectory() as profile:
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
               f"--user-data-dir={profile}", "--no-pdf-header-footer", "--print-to-pdf-no-header",
               f"--print-to-pdf={PDF_OUT}", html.as_uri()]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    pages = count_pages(PDF_OUT)
    status = "OK (3 a 5)" if 3 <= pages <= 5 else "FORA do intervalo 3 a 5!"
    print(f"PDF gerado: {PDF_OUT}\nPáginas: {pages} — {status}")
    return 0 if 3 <= pages <= 5 else 1


if __name__ == "__main__":
    sys.exit(main())
