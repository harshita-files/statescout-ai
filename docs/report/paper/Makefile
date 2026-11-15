PAPER = main

$(PAPER).pdf: $(PAPER).tex references.bib sections/*.tex
	pdflatex -interaction=nonstopmode -halt-on-error $(PAPER)
	bibtex $(PAPER)
	pdflatex -interaction=nonstopmode -halt-on-error $(PAPER)
	pdflatex -interaction=nonstopmode -halt-on-error $(PAPER)

clean:
	rm -f $(PAPER).aux $(PAPER).bbl $(PAPER).blg $(PAPER).log $(PAPER).out sections/*.aux

.PHONY: clean
