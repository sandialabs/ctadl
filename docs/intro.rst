Introduction
============

CTADL is a static taint analysis tool.

CTADL (pronounced “citadel”) takes as input a program, known as a system
under test (SUT), and allows you to perform taint analysis across
procedures. Taint analysis discovers data flow paths in the SUT between
user-designated sources and sinks. CTADL — which stands for
Compositional Taint Analysis in DataLog — is customizable, performant,
and uses simple heuristics. CTADL supports the languages:

-  Java and Android using JADX,
-  Pcode from Ghidra, and
-  taint-front, a custom language for hand-writing taint analysis
   examples.

Its primary output format is
`SARIF <https://sarifweb.azurewebsites.net>`__, a results interchange
format that enables VSCode visualization of taint analysis results.


Support
-------

-  File an issue: https://github.com/sandialabs/ctadl/issues
-  Ask a question: https://github.com/sandialabs/ctadl/discussions

Known issues
------------

-  If the analyzer you compiled mysteriously crashes, it may be because
   the C++ compiler has been updated since the last time Souffle was
   installed. If you update the compiler, then souffle needs to be
   updated and all our analyses need to be recompiled. After you rebuild
   and reinstall Souffle, remove the
   ``$XDG_CONFIG_DIR/share/ctadl/analysis`` directory. On Windows the
   share directory is instead under ``%APPDATA%``.

Copyright
---------

Copyright 2025 National Technology & Engineering Solutions of Sandia,
LLC (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the
U.S. Government retains certain rights in this software.
