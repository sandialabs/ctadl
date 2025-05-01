#!/usr/bin/env python

from setuptools import setup

# It is very important that we install as an uncompressed dir structure, not a
# zip (egg). Souffle needs access to the entire datalog directory structure in
# order to run. If that dir structure is in a zipfile, we all lose.
setup(zip_safe=False)


