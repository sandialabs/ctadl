<a name="import_section"></a>
### Step 0: Import

Importing creates a directory with a variety of results.

- The `facts` subdir represents the entire native program in a TSV (tab-separated values) formatted, suitable for input to CTADL
- Other subdirs, such as `sources`, contain decompiled output

#### JADX

To import `myapp.apk`, you'd execute:

```
ctadl import jadx myapp.apk -o <workdir>
```

This creates an `<workdir>` directory with everything needed to run CTADL for that `myapp.apk`.
It includes decompiled sources (in the `sources` subdir).

#### Ghidra PCODE

To import `/usr/bin/ls`:

```
ctadl import pcode /usr/bin/ls
```

<a name="index_section"></a>
### Step 1: Index

Run the CTADL indexer with

```
ctadl index [<importdir>]
```

By default, it looks for the import in the current directory, but you can provide a path, too.
The indexing process autodetects the import language.

First, CTADL generates an `index.dl` containing the Datalog code for the indexer.
CTADL then checks whether it's compiled an indexer for this language before.
If not, it calls out to Souffle to compile the indexer, then runs it.

Next, this command creates an index, a sqlite database file `ctadlir.db`.
The index contains a data flow graph, a call graph, and other analysis artifacts.
The filename is unfortunately *not* configurable due to the limitations of the Souffle Datalog engine's compiler. To optimize indexing, ensure that the index is not being
written to over the network.
You can pass `-j` to set the number of cores to use.
I'd recommend using as many as you can.

Indexing can take some time and unfortunately there's no good way to measure its progress.
We print a live view of resources consumed, including load average and RAM consumption (if `psutil` is installed).

<a name="query_section"></a>
### Step 2: Query

Run a CTADL query with the command:

```
$ ctadl query [models.json]
```

CTADL reads the index from `ctadlir.db` and performs taint analysis.
It creates a `query.dl` file containing the complete Datalog code for the query.
It prints a summary of the paths, sources, sinks, and taint labels found.
CTADL outputs the query results into `ctadlir.db`.
You can skip the query analysis with `--skip` if it's already cached in the index.

Without a `models.json` argument, CTADL chooses a default query.
The default query uses a pre-selected, language-specific set of interesting sources and sinks.
