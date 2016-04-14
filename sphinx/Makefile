# Makefile for Sphinx documentation
#

EXTERNAL_FILES = /s/sdocs/docs/TypeSafeMemory.rst

# Don't try to bring in LangRef.html
OVERRIDEOPTS = -D "html_additional_pages.LangRef=dummy.html"

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
PAPER         =
BUILDDIR      = _build

# Internal variables.
ALLSPHINXOPTS   = -W -d $(BUILDDIR)/doctrees $(SPHINXOPTS) ../design -c .

.PHONY: help clean html dirhtml singlehtml pickle json htmlhelp qthelp devhelp epub latex latexpdf text man changes linkcheck doctest gettext

all:	html

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  html       to make standalone HTML files"

clean:
	-rm -rf $(BUILDDIR)/*

html:
	cp $(EXTERNAL_FILES) ../design/
	$(SPHINXBUILD) -b html $(ALLSPHINXOPTS) $(OVERRIDEOPTS) $(BUILDDIR)/html
	@echo
	@echo "Build finished. The HTML pages are in $(BUILDDIR)/html."
	python ./copyhtml.py
	git add -v -A ../design/*.html
