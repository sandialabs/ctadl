# CTADL Taint-front Fact Generator Plugin

This project is part of the [CTADL Taint Analyzer](https://github.com/sandialabs/ctadl).

This project provides a plugin for CTADL so that it can perform taint analysis on a custom language called taint-front, useful for hand-writing taint analysis examples.

# Installation

Use pip.

    $ pip install ctadl-taint-front-fact-generator

Afterward, if ctadl is installed, you can do:

    $ ctadl import taint-front example.tnt

See `ctadl --help` for more detauls.

Make sure, when you run ctadl, that [taint-front](https://github.com/sandialabs/ctadl/taint-front) is install and the `taintfront` binary is available in your `PATH`.
If you forget, it'll remind you.

