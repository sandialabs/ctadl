Usage
=====

Import the SUT
----------------------------

A system under test (SUT) must be imported to be used with CTADL.
The general form of the command is:

.. code-block:: sh

    ctadl import <language> <artifact> -o <workdir>

``ctadl import --help`` lists, among other things, the languages
your installation supports.
The language is the language of the SUT.
Artifacts are specific to the language, as you'll see below.
Importing creates a directory, ``<workdir>`` with a variety of results.

-  The ``facts`` subdir represents the entire native program in a TSV
   (tab-separated values) formatted, suitable for input to CTADL.
   This format is typically referred to as Datalog "facts."
-  Other subdirs, such as ``sources``, contain decompiled output

Analyze Android APKs and Java bytecode
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To import ``myapp.apk``, you’d execute:

.. code-block:: sh

   ctadl import jadx myapp.apk -o <workdir>

This creates an ``<workdir>`` directory with everything needed to run
CTADL for that ``myapp.apk``. It includes decompiled sources (in the
``sources`` subdir).

Ghidra PCODE
^^^^^^^^^^^^

To decompile and import ``/usr/bin/ls``:

.. code-block:: sh

   ctadl import pcode /usr/bin/ls

.. note::

   Importing a binary through Ghidra requires that Ghidra is
   installed and that the ``GHIDRA_HOME`` environment variable is
   set properly, typically to ``GHIDRA/lib/ghidra`` where GHIDRA
   is the place where Ghidra was extracted.

Index the SUT
----------------

Indexing runs our compositional data flow analysis over the entire
SUT.

Run the CTADL indexer with:

.. code-block:: sh

   ctadl [--directory <working-directory>] index

By default, it looks for the import in the current directory, but you
can provide a path, too. The indexing process autodetects the import
language.

First, CTADL generates an ``index.dl`` containing the Datalog code for
the indexer. CTADL then checks whether it’s compiled an indexer for this
language before. If not, it calls out to Souffle to compile the indexer,
then runs it.

Next, this command creates an index, a sqlite database file
``ctadlir.db``. The index contains a data flow graph, a call graph, and
other analysis artifacts. The filename is unfortunately *not*
configurable due to the limitations of the Souffle Datalog engine’s
compiler. To optimize indexing, ensure that the index is not being
written to over the network. You can pass ``-j`` to set the number of
cores to use. I’d recommend using as many as you can.

Indexing can take some time and unfortunately there’s no good way to
measure its progress. We print a live view of resources consumed,
including load average and RAM consumption (if ``psutil`` is installed).

Query the SUT: Run Taint Analysis
--------------------------------------------

Run a CTADL query with the command:

.. code-block:: sh

   $ ctadl query [models.json]

CTADL reads the index from ``ctadlir.db`` and performs taint analysis.
It creates a ``query.dl`` file containing the complete Datalog code for
the query. It prints a summary of the paths, sources, sinks, and taint
labels found. CTADL outputs the query results into ``ctadlir.db``. You
can skip the query analysis with ``--skip`` if it’s already cached in
the index.

Without a ``models.json`` argument, CTADL chooses a default query. The
default query uses a pre-selected, language-specific set of interesting
sources and sinks.
