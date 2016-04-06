import string
import os.path
from datetime import date
from glob import glob

header = string.Template("""---
layout: default
title: $Title
categories: design
date: $Date
---
""")

for fname in glob('_build/html/*.html'):
    basename = os.path.basename(fname)
    if basename in ('contents.html', 'genindex.html', 'search.html', 'LangRef.html'):
        continue

    srcfile = open(fname, 'r')
    text = srcfile.read()
    srcfile.close()

    destfname = '../design/'+basename
    mdate = date.today()
    if os.path.isfile(destfname):
        mdate = date.fromtimestamp(os.path.getmtime(destfname))

    print "Writing", destfname, "modified", mdate.strftime('%Y-%m-%d')
    destfile = open(destfname, 'w')
    d = {'Title': basename, 'Date': mdate.strftime('%Y-%m-%d')}
    destfile.write(header.substitute(d) + text)
    destfile.close()
