Development Guide
=================

There are three primary schemas used in CTADL:

-  The CTADL IR schema, documented in
   `ctadl_schema.dl <https://github.com/sandialabs/ctadl/blob/main/src/ctadl/souffle-logic/ctadl_schema.dl>`__
-  The data flow graph schema, documented in
   `graph_schema.dl <https://github.com/sandialabs/ctadl/blob/main/src/ctadl/souffle-logic/graph_schema.dl>`__
-  The taint slice schema, documented in
   `taint_schema.dl <https://github.com/sandialabs/ctadl/blob/main/src/ctadl/souffle-logic/taint_schema.dl>`__

CTADL Import & Export Plugins
-----------------------------

CTADL supports two types of plugins: import and export, which enable
features in the corresponding ``ctadl import`` and ``ctadl export``
commands, respectively. All plugins must define a few attributes and a
``run`` function whose characteristics depend on the type of plugin. The
plugin API is currently subject to change without notice.

Import Plugins
^^^^^^^^^^^^^^

Import plugins are used to define new languages for CTADL to analyze.
Import plugins must define two global attributes: ``language`` and
``version``.

CTADL filters plugins based on the ``language`` attribute. The Ghidra
import plugin, for example, defines the ``language = "PCODE"``
attribute, and this is what appears as the first argument to the
``ctadl import`` command when the plugin is installed.

The ``run`` function must support the following positional arguments:

-  ``ctadl``: The ``ctadl`` module
-  ``args``: The raw command-line arguments from ``argparse``
-  ``artifact``: A ``str`` that points at the artifact the plugin uses
   as input. For some plugins, e.g. JADX, this is a directory. For
   others, it’s a file.
-  ``out``: A ``str`` that denotes a path where output should be stored.
   Could be a file or directory depending on the plugin
-  Other keyword arguments that the plugin knows how to interpret.

Export Plugins
^^^^^^^^^^^^^^

Export plugins are used to define external formats to which we can
export CTADL index information. Export plugins must define two global
attributes: ``export_formats`` and ``version``.

CTADL filters plugins based on the ``export_formats`` attribute. The
networkx export plugin, for example, defines the
``export_formats = ["gml"]`` attribute because it can export to the GML
format. The format name appears as an option for the
``ctadl export --format`` flag when the plugin is installed.

The ``run`` function must support the following positional arguments:

-  ``ctadl``: The ``ctadl`` module
-  ``args``: The raw command-line arguments from ``argparse``
-  ``format``: A ``str``, the format chosen by the user
-  ``index``: A ``Path`` pointing at the index to export
-  ``out``: A ``str`` that denotes a path where output should be stored.
   Could be a file or directory depending on the plugin
-  Other keyword arguments that the plugin knows how to interpret.
