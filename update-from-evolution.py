#!/usr/bin/python
# Copy proposals from my swift-evolution fork

import string
import os.path
from datetime import date
from glob import glob

header = string.Template("""---
layout: default
title: $Title
categories: proposal
date: $Date
---
""")

proposalnames = [
    ("/s/swift-evolution/proposals/XXXX-unsaferawpointer.md", "voidpointer.md")
]

for (origfname, newfname) in proposalnames:
    srcfile = open(origfname, 'r')
    text = srcfile.read()
    srcfile.close()

    mdate = date.fromtimestamp(os.path.getmtime(origfname))
    proposalname = text.splitlines()[0].lstrip('#')

    destfname = './proposal/'+newfname
    print "Writing", destfname, "modified", mdate.strftime('%Y-%m-%d')
    destfile = open(destfname, 'w')
    d = {'Title': proposalname, 'Date': mdate.strftime('%Y-%m-%d')}
    destfile.write(header.substitute(d) + text)
    destfile.close()
