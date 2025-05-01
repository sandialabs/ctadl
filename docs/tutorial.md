# CTADL Tutorial

CTADL (pronounced "citadel" or mispronounced "see-taddle") is a static program slicer and taint analyzer.

This file will walk you through running `ctadl` for the first time and visualizing results in VSCode.
If you already understand how to run CTADL, see the [workflows](workflows.md).

This file assumes you have installed CTADL with docker or through other means.
See the [INSTALL](INSTALL.md) directions if you haven't installed CTADL.
The commands below will refer to running CTADL using `ctadl`.
If you're using the Docker distribution, see the last section for notes on how to minimize friction.
With a little set up, the commands look mostly the same.

To use CTADL, follow our three step plan:

0.  [**Import**](#import) the program of interest so that CTADL can use it.
1.  [**Index**](#index) the program, which performs a data flow analysis and constructs a data flow graph.
2.  [**Query**](#query) the program for taint relationships.

The import only need be created once per program (or if we release an importer update).

## Quickstart

```
ctadl import [jadx|pcode] <artifact> -o <workdir>
cd <workdir>
ctadl index # writes to 'ctadlir.db'
ctadl query --format sarif -o results.sarif # reads/writes to 'ctadlir.db'
```

## Step 0: Import
<a name="import"></a>

Importing creates a directory with a variety of results.

- The `facts` subdir represents the entire native program in a TSV (tab-separated values) formatted, suitable for input to CTADL
- Other subdirs, such as `sources`, contain decompiled output

### JADX

To import `myapp.apk`, you'd execute:

```
ctadl import jadx myapp.apk -o <workdir>
```

This creates an `<workdir>` directory with everything needed to run CTADL for that `myapp.apk`.
It includes decompiled sources (in the `sources` subdir).

### Ghidra PCODE

To import `/usr/bin/ls`:

```
ctadl import pcode /usr/bin/ls
```

## Step 1: Index
<a name="index"></a>

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

## Step 2: Query
<a name="query"></a>

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

### Visualize results

To see all the results, CTADL provides SARIF output:

```
$ ctadl query --format sarif > results.sarif
```

- SARIF files can be viewed with the [VSCode Sarif Viewer](https://marketplace.visualstudio.com/items?itemName%253DMS-SarifVSCode.sarif-viewer). More details in [workflows](workflows.md).
- You can see [our SARIF documentation](SARIF.md).


## Customizing taint analysis

We have documented some [workflows](workflows.md) that cover how to practically apply CTADL to a program.

# Appendix: Docker container

Our docker distribution contains CTADL plus all available plugins and the tools they depend on.
It isn't small.
Running it is a bit fiddly because CTADL operates on an index in the current directory.
One has to be careful to associate host and container mounts, and run ctadl in the right directory.
Let's assume your setup looks like this:

- Host machine:
    - Artifact dir `/path/to/artifacts` that contains `app.apk`
    - Imports dir `/path/to/imports` where imports will be written
- Container. Let's make simple mounts:
    - Maps host artifact dir to `/artifacts`
    - Maps host imports dir to `/imports`
    - Ensure we write to the imports dir using the `--directory` option to CTADL
    - Assume the container name is `ctadl:latest`

The steps below show how to run docker, mounting these volumes, and making sure CTADL is invoked appropriately so output is generated on the host.

```
$ docker load < ctadl-docker.tar.gz
$ mkdir -p /path/to/imports/app
$ docker run --rm -it --volume /path/to/artifacts:/artifacts --volume /path/to/imports:/imports \
    ctadl:latest --directory /imports import jadx app.apk -o app
$ docker run --rm -it --volume /path/to/artifacts:/artifacts --volume /path/to/imports:/imports \
    ctadl:latest --directory /imports/app index
$ docker run --rm -it --volume /path/to/artifacts:/artifacts --volume /path/to/imports:/imports \
    ctadl:latest --directory /imports/app query
```

To explain:

- The `--directory` option that makes `ctadl` switch to the given directory in the container before writing its output.
  This ensures that index and query operate on the index corretly.
- On import, `-o app` is also needed so that the output ends up at `/path/to/imports/app` on the host.

To simplify running CTADL in docker, we made [dctadl](bin/dctadl), a Python script that wraps up the rather complicated docker command line behind the scenes.
It provides a CLI experience similar to running native CTADL when using docker.
It's configurable so that it can wrap more complex docker commands (or even use podman).

```
$ dctadl --init # generates config file
$ dctadl --directory ... # run ctadl using docker
```

If you have the docker distribution, you can copy the file `/bin/dctadl` from the container to your host with [`docker cp`](https://docs.docker.com/reference/cli/docker/container/cp/).
