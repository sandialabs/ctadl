# CTADL networkx graph export

This project is part of the [CTADL Taint Analyzer](https://github.com/sandialabs/ctadl).

This project provides a plugin for CTADL to export data flow graph information via networkx.

# Installation

Use pip.

    $ pip install ctadl-networx-export-plugin

Afterward, if ctadl is installed, you can do:

    $ ctadl export --format gml pcode /path/to/a/binary

See `ctadl --help` for more detauls.
