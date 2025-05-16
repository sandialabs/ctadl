# CTADL Ghidra Pcode Fact Generator Plugin

This project is part of the [CTADL Taint Analyzer](https://github.com/sandialabs/ctadl).

This project provides a plugin for CTADL so that it can perform taint analysis on [Ghidra](https://github.com/NationalSecurityAgency/ghidra) Pcode.

# Installation

Use pip.

    $ pip install ctadl-ghidra-fact-generator

Afterward, if ctadl is installed, you can do:

    $ ctadl import pcode /path/to/a/binary

See `ctadl --help` for more detauls.

Make sure, when you run ctadl, that [Ghidra](https://ghidra-sre.org) runs in your environment and that `GHIDRA_HOME` is set.
If you forget, it'll remind you.

