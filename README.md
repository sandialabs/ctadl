# CTADL

[CTADL](https://github.com/sandialabs/ctadl) is a static taint analysis tool.

CTADL (pronounced "citadel") takes as input a program, known as a system under test (SUT), and allows you to perform taint analysis across procedures.
Taint analysis discovers data flow paths in the SUT between user-designated sources and sinks.
CTADL &mdash; which stands for Compositional Taint Analysis in DataLog &mdash; is customizable, performant, and uses simple heuristics.
CTADL supports the languages:

- Java and Android using JADX,
- Pcode from Ghidra, and
- taint-front, a custom language for hand-writing taint analysis examples.

Its primary output format is [SARIF](https://sarifweb.azurewebsites.net), a results interchange format that enables VSCode visualization of taint analysis results.

CTADL has flexible analysis options and supports a number of use cases. See the [documentation](https://ctadl.readthedocs.io/en/latest/) for detailed information.

## Compatibility

CTADL works under MacOS, Linux, and Windows via Windows Subsystem for Linux (WSL). CTADL requires python 3.9 or later.

## Dependency - Install Souffle

[Souffle](https://souffle-lang.github.io) is the Datalog engine CTADL uses to perform analysis.
The [supported version](https://github.com/dbueno/souffle/tree/v2.3-fix-sqlite) is installed into the path `<prefix>` like so:

```sh
git clone --branch v2.3-fix-sqlite https://github.com/dbueno/souffle
cd souffle
# recommended config, substitute <prefix> for your install path
cmake -S . -B build -DSOUFFLE_USE_OPENMP=1 -DCMAKE_BUILD_TYPE=Release -DSOUFFLE_DOMAIN_64BIT=ON -DCMAKE_INSTALL_PREFIX=<prefix> ..
cmake --build build -j8
cmake --build build --target install
```

- **Note:** Souffle and CTADL require compiling C++ files with the *same* compiler. See the [known issues section](#known_issues_section).
- We recommend the CMake flag `-DSOUFFLE_USE_OPENMP=1`, which compiles souffle with openmp support for parallel execution. (I believe it's on by default.)
- The following dependencies were sufficient on a fresh  Ubuntu 24.04 WSL installation:
  ```
  sudo apt install cmake libncurses-dev flex bison zlib1g-dev sqlite3 libsqlite3-dev libffi-dev build-essential
  ```
- Windows users not using WSL, see our documentation for more info.


The [supported version](https://github.com/dbueno/souffle/tree/v2.3-fix-sqlite) is a patched version of Souffle 2.3.
The patch fixes round trips through Souffle's sqlite backend.
The bug report is here: <https://github.com/souffle-lang/souffle/issues/2411>.

## Install CTADL

You can install CTADL with pip:

```sh
python3 -mpip install ctadl ctadl-jadx-fact-generator-plugin ctadl-ghidra-fact-generator-plugin ctadl-taint-front-fact-generator-plugin
```

We recommend some optional libraries:

```sh
python3 -mpip install psutil jsonschema rich
```

Their purpose:

- [psutil](https://pypi.org/project/psutil/): to show live memory consumption (optional, but recommended as CTADL may use a lot of memory).
- [rich](https://pypi.org/project/rich/): for pretty output.
- [jsonschema](https://pypi.org/project/jsonschema/) (if omitted, no validation of models is performed): for validating model generators.
  When developing model generators by hand, we recommend installing this because it produces useful validation error messages.

Plugins implement import and export:

- [ctadl-jadx-fact-generator-plugin](https://pypi.org/project/ctadl-jadx-fact-generator-plugin/) and [source repository](https://github.com/sandialabs/ctadl-jadx-fact-generator/releases).
- [ctadl-ghidra-fact-generator-plugin](https://pypi.org/project/ctadl-ghidra-fact-generator-plugin/)
- [ctadl-taint-front-fact-generator-plugin](https://pypi.org/project/ctadl-taint-front-fact-generator-plugin/).
- [ctadl-networkx-export-plugin](https://pypi.org/project/ctadl-networkx-export-plugin/)

## Android Taint Analysis

To perform taint analysis on an Android APK:

```sh
ctadl import jadx myapp.apk -o myapp_workdir
cd myapp_workdir
ctadl index
ctadl query --format sarif -o results.sarif
```

This produces a SARIF results file containing data flows paths between taint sources and sinks, using a canned set of interesting sources and sinks.
SARIF files can be viewed with the [VSCode Sarif Viewer](https://marketplace.visualstudio.com/items?itemName%253DMS-SarifVSCode.sarif-viewer), available from the VSCode marketplace.

The three step plan is:

0.  **Import** the program of interest so that CTADL can use it. The import only need be created once per program or whenever the importer is updated.
1.  **Index** the program, which performs a data flow analysis and constructs a data flow graph.
2.  **Query** performs taint analysis.

For further details on what these phases do, see our [phases documentation](https://github.com/sandialabs/ctadl/blob/main/docs/phases.md).
Each CTADL subcommand, such as `index` or `query`, has help:

```
ctadl index --help
```

## Ghidra Pcode Taint Analysis

The steps are the same as above except for importing:

```sh
ctadl import pcode /path/to/binary/program -o program_workdir
```

The following sections describe workflows for accomplishing analysis tasks with CTADL.

Running a CTADL query may produce a bunch of paths that are uninteresting to you or no paths at all.
Take heart; this doesn't mean CTADL can't analyze that codebase.
See our [workflow
documentation](https://readthedocs.io/ctadl/workflows)] for
discussion of each workflow. Key workflows are discussed below.

## Visualize path results with VSCode's SARIF Viewer

```sh
ctadl query [query.json] --format sarif -o results.sarif
```

The query path results are saved into the file `results.sarif`.
You can open this file in the [SARIF Viewer](https://marketplace.visualstudio.com/items?itemName=MS-SarifVSCode.sarif-viewer) (or the [SARIF Explorer](https://marketplace.visualstudio.com/items?itemName=trailofbits.sarif-explorer)) to browse the paths found, if any, from sources to sinks.

After installing the plugin, make sure to run VSCode on the `sources` directory of the import:

``` sh
code /path/to/import/sources 
```

In VSCode, `File -> Open` the `results.sarif` and it should open a `SARIF Results` pane.
Click on a LOCATION to zoom in on a path.
In the ANALYSIS STEPS pane, click on part of a path to jump there in the decompiled code.

Each step in the path refers to a taint flow, either into or out of a vertex (tainted location).
Flows with an asterisk (e.g. `out of *`) refer to a flow that crosses a function boundary.
Vertexes may have a couple of names, such as internal names (e.g. `@retparameter`) and source names (e.g., `tmDevice`), and may have special roles (e.g. `parameter(1)`, a parameter of an associated function).
We provide as much info as we can in the ANALYSIS STEPS view to contextualize each step of the taint flow.

![Screenshot](https://github.com/sandialabs/ctadl/raw/main/docs/VSCode-SARIF-screenshot.png)

NOTE: This workflow has been principally tested with APKs.
[File an issue](https://github.com/sandialabs/ctadl/issues) if it doesn't work with other languages.

## Workflow - Analyze a SUT with libraries by linking code

If the system under test (SUT) is factored into a main program with a bunch of supporting libraries, such as a jar with many library jars, you may want to merge them all together before analysis.
This gives the most accurate result.

In general, linking code together requires a process particular to the SUT language.
For this example, we'll target Java jar files.
We'll assume the Java program is composed of `app.jar` and two libraries, `lib1.jar` and `lib2.jar`.
You can use [merjar](https://github.com/dbueno/merjar) to merge them together.

```sh
merjar -o app-with-libraries.jar app.jar lib1.jar lib2.jar
ctadl import jadx app-with-libraries.jar -o ./app-with-libraries
cd ./app-with-libraries
ctadl index
```

Sometimes the resulting code is too large to analyze and CTADL consumes too much memory.
In that case, you can try the alternative discussed next.

## Workflow - Analyze a SUT with libraries by composing analyses

When the SUT is factored into a main program with a bunch of supporting libraries, such as a jar with many library jars, merging them sometimes results in a problem that is too large.
Because CTADL is compositional, you can separately analyze the libraries and compose the result with the main program.
The result may not be as precise as combining all the problems, but it's way better than nothing.

Say you've indexed `app.jar` and two libraries, `lib1.jar` and `lib2.jar` and your directory structure looks like this:

- `./app/ctadlir.db`: Index for app
- `./lib1/ctadlir.db`: Index for lib1
- `./lib2/ctadlir.db`: Index for lib2

Extract the function summaries as models to run together with the main app:

```sh
ctadl --directory lib1 inspect --dump-summaries > lib1-models.json
ctadl --directory lib2 inspect --dump-summaries > lib2-models.json

# combine the models files with jq:
jq -s '{ model_generators: map(.model_generators) | add }' lib1-models.json lib2-models.json > all-lib-models.json

# index again but with lib models
cd ./app
ctadl index --models all-lib-models.json
```

If you look at the summaries, for example in `lib1-models.json`, you'll see *propagation models*.
These allow you to say things like, "for the method `toString`, data flows from `this` to the return value."
Feeding propagation models to `ctadl index` results in function summaries.

## Workflow - Iterate on sources & sinks

Running successful CTADL queries largely depends on how you model parts of the SUT.
Sources, sinks, sanitizers, and function models are specified using our [`model_generator` file format](https://github.com/sandialabs/ctadl/blob/main/docs/models.md);
the full schema is in [our schema file](https://github.com/sandialabs/ctadl/blob/main/src/ctadl/models/ctadl-model-generator.schema.json).

Say you want to model a function as a *source*: you want to associate the taint label `HttpContent` with the return value of the `getContent()` method from `Lorg/apache/http/HttpEntity;`.
You can generate a template to start with using `ctadl query --template -o query.json`.
Write a source model generator like this:

```json
{
  "model_generators": [
    {
      "find": "methods",
      "where": [
        {
          "constraint": "signature_match",
          "name": "openFileInput",
          "parent": "Landroid/content/Context;"
        }
      ],
      "model": {
        "sources": [
          {
            "kind": "HttpContent",
            "port": "Return"
          }
        ]
      }
    }
  ]
}
```

Save this into `query.json` and run a query with it. Afterward, you can inspect whether your models "take":

```sh
ctadl query query.json
ctadl inspect --dump-source-sink-models
```

This will dump, in `model_generator` format, the sources and sinks that were matched by CTADL.
Note that internally *all sources are vertices of the data flow graph (not methods)*, so the dumped models will match on variables, not methods.
While you can write models that `find` on `variable` like this, matching on methods is typical.
This output is primarily for users to understand what matched.

If you want to set up sinks, just use the `"sinks"` model instead of `"sources"`.

Once you've set up sources and sinks, CTADL query will compute any paths between them. You can obtain these paths as SARIF. See the next workflows for how to visualize the paths.

## Workflow - Find and fill in propagation models for external functions

Taint analysis hits a hard stop during analysis if a function is not properly modeled.
Even something as simple as the following will lose taint on `z`:

```
x = sourceOfData(); // x is tainted
z = max(x, y); // taint on z is lost if max not modeled
```

To solve such a problem, you'd add a propagation model for `max`.
Here's our actual model for max in Java, which states that arguments 0 and 1 should propagate flows to the return value.

```json
{ "model_generators": [
    {
      "find": "methods",
      "where": [
        {
          "constraint": "signature_match",
          "names": [
            "max"
          ],
          "parents": [
            "Ljava/lang/Math;",
            "Ljava/lang/Byte;",
            "Ljava/lang/Short;",
            "Ljava/lang/Integer;",
            "Ljava/lang/Long;",
            "Ljava/lang/Float;",
            "Ljava/lang/Double;"
          ]
        }
      ],
      "model": {
        "propagation": [
          { "input": "Argument(0)", "output": "Return" },
          { "input": "Argument(1)", "output": "Return" }
        ]
      }
    }
  ]
}
```

It's often tough to know which functions you, as a user, should model to get optimal results.
To hone in on such problems, after a query you can dump partial models for black hole functions:

```sh
ctadl query
ctadl inspect --dump-black-hole-functions
```

This will dump *partial* propagation model generators, like the one below.
Partial models indicate where taint was lost and let you easily supply where it should flow.
The partial model below means the analyzer (1) found that argument 1 (the String) of `divideMessage` was tainted and that (2) the method `divideMessage` has no model, so the taint was lost.


```json5
    {
      "find": "methods",
      "where": [
        {
          "constraint": "signature_match",
          "unqualified-id": "Landroid/telephony/SmsManager;.divideMessage:(Ljava/lang/String;)Ljava/util/ArrayList;"
        },
        {
          "model": {
            "propagation": [
              {
                "input": "Argument(1)",
                "output": "Return" # you'd add this to create a model
              }
            ]
          }
        }
      ]
    }
```

It's up to you to decide what to do:

- Sometimes the desirable behavior is to leave it unmodeled.
- Sometimes you want to model it. So you would add an `"output"` field to complete the partial propagation model.
- Or you could add it as an endpoint (source or sink).

Reverse-taint that is lost in the reverse way is dumped as a partial model with only an `output` field.

## Advanced Workflow - Working with either sources or sinks, but not both

Sometimes you have a question like, "What things eventually flow to the sink I'm interested in?"
This question has well-defined sinks (e.g., a database `execute()` statement) but you don't have a good idea, or don't care, where the data comes from.
You want to learn about where the data might come from.

NOTE: this workflow may generate huge amounts of results.

As an example, we'll use `execute` method of two HTTP clients.

```json
{
  "model_generators": [
    {
      "find": "methods",
      "where": [
        {
          "constraint": "signature_match",
          "name": "execute",
          "parents": [
            "Lorg/apache/http/client/HttpClient;",
            "Lorg/apache/http/impl/client/DefaultHttpClient;"
          ]
        }
      ],
      "model": {
        "sinks": [
          {
            "kind": "Net",
            "port": "Argument(1)"
          }
        ]
      }
    },
  ]
}
```

Save to `sink_models.json`.
Run the query:

```sh
ctadl query sink_models.json
```
```
[...]
summary of query results:
0 source vertexes reach 0 sink vertexes
0 source taint labels across 0 taint sources
1 sink taint labels across 2 taint sinks
0 instructions tainted by sources
19 instructions backward-tainted by sinks
```

Note that there are no source vertices, only backward taint. We can't visualize paths because there's no place for the paths to start.
This workflow simply computes an interprocedural backward slice, starting from sinks.

To find paths, let's add a special source that matches on `has_code`; this instructs CTADL to find sources that have no code, i.e., they're external:

```json
    {
      "find": "methods",
      "where": [{ "constraint": "has_code", "value": false }],
      "model": {
        "sources": [
          { "kind": "Data", "port": "Return" }
        ]
      }
    }
```

Paths in the results of this query will go from some external method's return value to our sinks.
Run the query again:

```sh
ctadl query --compute-slices backward sink_models.json
```
```
summary of query results:
2 source vertexes reach 2 sink vertexes
1 source taint labels across 809 taint sources
1 sink taint labels across 2 taint sinks
12714 instructions tainted by sources
19 instructions backward-tainted by sinks
```

We pass `--compute-slices backward` for efficiency, so that CTADL does not try to compute forward slices from every method that has no code, which could be lots.
(CTADL defaults to only computing forward slices; `--compute-slices` lets you control the direction, or do both.)
Now we can visualize the paths with SARIF (see above).


## Workflow - Work with Datalog directly

Our data flow and query analyses are written in Datalog.
Users wishing to add some extra Datalog can do so as follows:

```sh
 ctadl index --dl extra.dl # appends extra.dl to the indexer
 ctadl query --dl extra.dl # appends extra.dl to the query
```

You can also run souffle yourself on the `index.dl` and `query.dl` files produced by the `index` and `query` commands, respectively.
Queries can use Datalog and model generators at the same time.


# Support

- File an issue: <https://github.com/sandialabs/ctadl/issues>
- Ask a question: <https://github.com/sandialabs/ctadl/discussions>
- Online documentation: <https://ctadl.readthedocs.io/en/latest/>

<a id="known_issues_section"></a>
## Known issues

- If the analyzer you compiled mysteriously crashes, it may be because the C++ compiler has been updated since the last time Souffle was installed.
  If you update the compiler, then souffle needs to be updated and all our analyses need to be recompiled.
  After you rebuild and reinstall Souffle, remove the `$XDG_CONFIG_DIR/share/ctadl/analysis` directory.
  On Windows the share directory is instead under `%APPDATA%`.

# Copyright

Copyright 2025 National Technology & Engineering Solutions of Sandia, LLC (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S. Government retains certain rights in this software.
