# CTADL Installation

CTADL has been tested on Mac and Linux operating systems.
Windows users (non wsl), see [here](#windows) for souffle, but follow the same [Install CTADL](#install-ctadl) and [frontend](#frontends) setup instructions.

## Dependencies

- A C++ compiler
- Souffle 2.3, see below
- Sqlite3
- Python 3.9+ with the following libraries:
    - pip: json5, to support parsing of the more-human-readable-than-json format JSON5
    - pip: psutil, to show live memory consumption (optional, but recommended as CTADL may use a lot of memory)
    - pip: jsonschema (optional, if omitted, no validation of models is performed). We recommend this when developing models by hand as the error messages are reasonbly nice
    - pip: rich, for pretty output (optional)

## Install Souffle

[Souffle](https://souffle-lang.github.io) is the Datalog engine CTADL uses to perform analysis.
Souffel 2.3 needs to be patched to work with CTADL.
A patched version is found below:

- https://github.com/dbueno/souffle/tree/v2.3-fix-sqlite
- If you clone it directly, make sure to also run `git checkout v2.3-fix-sqlite`.

The bug report is here: <https://github.com/souffle-lang/souffle/issues/2411>.
The patch fixes round-trips through Souffle's sqlite backend.

We recommend reading the entirety of the install process before running it, as there are a few choices to make:

- **Note:** We recommend installing Souffle and CTADL at the same time because they both require compiling C++ files with the *same* compiler.
- If you're going to use Ghidra, you need to compile Souffle with 64-bit support, because Ghidra produces large offsets.
  Do this with the `-DSOUFFLE_DOMAIN_64BIT=ON` option to CMake.
- We recommend the CMake flag `-DSOUFFLE_USE_OPENMP=1`, which compiles souffle with openmp support for parallel execution. (I believe it's on by default.)
- For dependencies, this was sufficient starting from a fresh Ubuntu 24.04 wsl installation:
  ```
  sudo apt install cmake libncurses-dev flex bison zlib1g-dev sqlite3 libsqlite3-dev libffi-dev build-essential
  ```
- Souffle uses the standard CMake build process. Make sure to set an install prefix (e.g. /usr/local) and install souffle:

  ```
  cd souffle
  cmake -S . -B build -DSOUFFLE_USE_OPENMP=1 -DCMAKE_BUILD_TYPE=Release -DSOUFFLE_DOMAIN_64BIT=ON -DCMAKE_INSTALL_PREFIX=<prefix> ..
  cmake --build build -j8
  cmake --build build --target install
  ```

## Install CTADL

CTADL's command line interface is mostly a Python program that calls other programs, including Souffle, JADX, and Ghidra.
CTADL is pip installable:

    $ pip install ctadl

For CTADL to analyze languages, you need a frontend.
Frontends are implemented as CTADL plugins that typically call out to other external tools.
You invoke them via the `ctadl import` command, which imports the artifact into a directory CTADL can index directly.

## Install JADX frontend (Java apk+jar)

To analyze APKs and JARs you need our JADX fact generator.

    $ pip install ctadl-jadx-fact-generator-plugin

The source is [available on github](https://github.com/sandialabs/ctadl-jadx-fact-generator/releases).

## Install Pcode frontend (binaries through Ghidra)

    $ pip install ctadl-ghidra-fact-generator-plugin

Make sure of the following:

- [Ghidra](https://ghidra-sre.org)
- You need to compile Souffle in 64-bit mode, with the CMake flag
  `-DSOUFFLE_DOMAIN_64BIT=ON`. We need to process large offsets produced during
  Ghidra import.
- At runtime it is required that `ghidra` is in the path or `GHIDRA_HOME` is set. Ghidra will be run headless under command line, so a gui (e.g. for wsl) is not required.

## Taint-front (A language for hand-written taint analysis examples)

Taint-front is a language we developed for hand-coding taint analysis examples.
See the [README](taint-front/README.md) for more info.
The taint-front fact generator is written in OCaml and built with dune:

    $ cd taint-front
    $ dune build
    $ dune install

Ensure that the installed binary, `taintfront`, is on your PATH.

    $ pip install ctadl-taint-front-fact-generator-plugin

# Windows

Although you may have better luck using a Mac system or a Linux system or VM (or wsl), we provide a release zip that contains a [Windows souffle binary](https://github.com/sandialabs/ctadl/releases/download/v0.11.0/souffle-windows-x64.zip) (to see how to build souffle yourself for Windows, see [souffle-build-windows](docs/souffle-build-windows.md)). There is a `souffle.bat` file in there that you use to run souffle.

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


# Contact

- File an issue: <https://github.com/sandialabs/ctadl/issues>
- Ask a question: <https://github.com/sandialabs/ctadl/discussions>
