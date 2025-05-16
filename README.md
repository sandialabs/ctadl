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

## Compatibility

CTADL works under MacOS, Linux, and Windows via Windows Subsystem for Linux (WSL). CTADL requires python 3.9 or later.

## Dependency - Install Souffle

[Souffle](https://souffle-lang.github.io) is the Datalog engine CTADL uses to perform analysis.
The [supported version](https://github.com/dbueno/souffle/tree/v2.3-fix-sqlite) is installed into the path `<prefix>` like so:

```sh
git clone --branch v2.3-fix-sqlite https://github.com/dbueno/souffle/tree/v2.3-fix-sqlite
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
- Windows users not using WSL, see [here](#windows_section) for Souffle instructions.


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
SARIF files can be viewed with the [VSCode Sarif Viewer](https://marketplace.visualstudio.com/items?itemName%253DMS-SarifVSCode.sarif-viewer).

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
The workflows below provide guidance on how to proceed.


## Workflow - Iterate on sources & sinks

Running successful CTADL queries largely depends on how you model parts of the SUT.
Sources, sinks, sanitizers, and function models are specified using our [`model_generator` file format](https://github.com/sandialabs/ctadl/blob/main/docs/models.md);
the full schema is in [our schema file](https://github.com/sandialabs/ctadl/blob/main/src/ctadl/models/ctadl-model-generator.schema.json).

Say you've indexed a program and you want to model a function as a *source*: you want to associate the taint label `HttpContent` with the return value of the `getContent()` method from `Lorg/apache/http/HttpEntity;`.
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

Save this into `query.json` and run a query with it:

```sh
ctadl query query.json
```

You can see if your models "take" by inspecting the source-sink models afterward:

```sh
ctadl inspect --dump-source-sink-models
```

This will dump, in `model_generator` format, the sources and sinks that were matched by CTADL.
Note that internally *all sources are vertices of the data flow graph (not methods)*, so the dumped models will match on variables, not methods.
The model you get back might look like this:

```json
{
  "find": "variables",
  "where": [
    {
      "constraint": "signature_match",
      "name": "@retparameter",
      "parent": "Landroid/content/Context;:(Ljava/lang/String;)Ljava/io/FileInputStream;V"
    }
  ],
  "model": {
    "sources": [
      {
        "kind": "HttpContent",
        "field": ""
      }
    ]
  }
}
```

While you can write models that `find` on `variable` like this, matching on methods is typical.
This output is primarily for users to understand what matched.

If you want to set up sinks, just use the `"sinks"` model instead of `"sources"`.

Once you've set up sources and sinks, CTADL query will compute any paths between them. You can obtain these paths as SARIF. See the next workflows for how to visualize the paths.

## Workflow - Visualize path results with VSCode's SARIF Viewer

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

When the system under test (SUT) is factored into a main program with a bunch of supporting libraries, such as a jar with many library jars, merging them sometimes results in a problem that is too large.
Because CTADL is compositional, you can separately analyze the libraries and compose the result with the main program.
The result may not be as precise as combining all the problems, but it's way better than nothing.

We'll assume the java program is composed of `app.jar` and two libraries, `lib1.jar` and `lib2.jar`.
Import them:

```sh
ctadl import jadx lib1.jar -o ./lib1
ctadl import jadx lib2.jar -o ./lib2
ctadl import jadx app.jar -o ./app
```

We now should have three directories, `lib1`, `lib2`, and `app`.
Next, analyze the libraries alone:

```sh
cd lib1 && ctadl index
cd lib2 && ctadl index
```

Finally, extract the function summaries as models to run together with the main app:

```sh
ctadl inspect -i lib1/ctadlir.db --dump-summaries > lib1-models.json
 ctadl inspect -i lib2/ctadlir.db --dump-summaries > lib2-models.json

# combine the models files with jq:
jq -s '{ model_generators: map(.model_generators) | add }' lib1-models.json lib2-models.json > all-lib-models.json

# index again but with lib models
cd ./app
ctadl index --models all-lib-models.json
```

If you look at the summaries, for example in `lib1-models.json`, you'll see *propagation models*.
These allow you to say things like, "for the method `toString`, data flows from `this` to the return value."
Feeding propagation models to `ctadl index` results in function summaries.

## Workflow - Work with Datalog directly

Our data flow and query analyses are written in Datalog.
Users wishing to add some extra Datalog can do so as follows:

```sh
 ctadl index --dl extra.dl # appends extra.dl to the indexer
 ctadl query --dl extra.dl # appends extra.dl to the query
```

You can also run souffle yourself on the `index.dl` and `query.dl` files produced by the `index` and `query` commands, respectively.
Queries can use Datalog and model generators at the same time.


<a id="windows_section"></a>
## Installing on Windows without Windows Subsystem for Linux

Although you may have better luck using a Mac system or a Linux system or VM (or WSL), we provide a release zip that contains a [Windows souffle binary](https://github.com/sandialabs/ctadl/releases/download/v0.11.0/souffle-windows-x64.zip) (to see how to build souffle yourself for Windows, see [souffle-build-windows](https://github.com/sandialabs/ctadl/blob/main/docs/souffle-build-windows.md)). There is a `souffle.bat` file in there that you use to run souffle.

Python setup instructions:
1) Install python3 for Windows (e.g. https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe)
2) Run `py -3 -m pip install setuptools`.
3) In the ctadl repo, run `py -3 setup.py install --user`
4) Run `py -3 bin\ctadl --help` to see if it worked

See the above sections for further instructions, substituting the `ln -s` commands for `mklink /d` or similar or just copying things directly and using git for Windows if needed.

Additional run instructions:
- To run souffle directly (example outputting to stdout on a simple test): `.\souffle-windows-x64\souffle.bat -D- .\souffle-windows-x64\test.dl`
- To run ctadl after installing: `py -3 \path\to\ctadl\bin\ctadl --souffle .\path\to\souffle.bat ...`
- To run ctadl in the mode where souffle compiles binaries for the analysis, you first have to install Visual Studio, then run something like this in cmd.exe (although with additional effort you can run `vcvars64.bat` in powershell), substituting your paths:
```cmd
"C:/Program Files/Microsoft Visual Studio/2022/Professional/VC/Auxiliary/Build/vcvars64.bat"
set PATH=%PATH%;\path\to\souffle-windows-x64
py -3 \path\to\ctadl\bin\ctadl --souffle souffle.bat index -f -C .\binary_name \path\to\facts
.\binary_name.exe -F \path\to\facts
```
- For the above, the souffle directory needs to be in your path so the library files are picked up since windows uses binary and load path as the same thing; you can also add it to the path in your system or user environment variables so you don't have to do that every time. It's also a similar process for queries.
- You can do the Ghidra import in the Ghidra GUI as normal on Windows, but to run it in headless mode, do something like (in powershell):
```powershell
# This has to be either set in the terminal, or in environment variables to the path to the outer ghidra directory
$Env:GHIDRA_HOME = "C:\path\to\ghidra_XX.Y_PUBLIC"
$pcode_facts_path = "\path\to\facts\output"
mkdir $pcode_facts_path -ErrorAction SilentlyContinue
$ctadl_path = "\path\to\ctadl"
# first arg is project parent dir, "curl" is project name
& $ctadl_path\src\ctadl\souffle-logic\pcode\analyzeHeadlessBigMem.bat $pcode_facts_path curl -import \path\to\binary -deleteProject -scriptPath $ctadl_path\src\ctadl\souffle-logic\pcode -postScript ExportPCodeForCTADL.java $pcode_facts_path
```


# Appendix - Docker container

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

# Support

- File an issue: <https://github.com/sandialabs/ctadl/issues>
- Ask a question: <https://github.com/sandialabs/ctadl/discussions>

<a id="known_issues_section"></a>
## Known issues

- If the analyzer you compiled mysteriously crashes, it may be because the C++ compiler has been updated since the last time Souffle was installed.
  If you update the compiler, then souffle needs to be updated and all our analyses need to be recompiled.
  After you rebuild and reinstall Souffle, remove the `$XDG_CONFIG_DIR/share/ctadl/analysis` directory.
  On Windows the share directory is instead under `%APPDATA%`.

# Copyright

Copyright 2025 National Technology & Engineering Solutions of Sandia, LLC (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S. Government retains certain rights in this software.
