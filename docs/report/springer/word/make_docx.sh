#!/bin/sh
# Rebuild StateScout.docx from the compiled paper (run `make` in ../ first).
# Needs uv; pandoc and python-docx are fetched ephemerally, nothing is installed.
set -e
cd "$(dirname "$0")"
python3 prep.py .. flat.tex
uv run --no-project --with pypandoc_binary python -c "
import pypandoc
pypandoc.convert_file('flat.tex','docx',format='latex',outputfile='raw.docx',extra_args=['--number-sections'])"
uv run --no-project --with python-docx python build.py raw.docx ../main.tex StateScout_paper.docx
rm -f raw.docx
