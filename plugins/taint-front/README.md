# CTADL Taint-front Fact Generator Plugin

This project is part of the [CTADL Taint Analyzer](https://github.com/sandialabs/ctadl).

This project provides a plugin for CTADL so that it can perform taint analysis on a custom language called taint-front, useful for hand-writing taint analysis examples.
See the taint-front [README](https://github.com/sandialabs/ctadl/blob/main/taint-front/README.md) for more info.

# Installation

## Dependency - taint-front fact generator

The taint-front fact generator is written in OCaml and built with dune:

```sh
cd taint-front
dune build
dune install
```

Ensure that the installed binary, `taintfront`, is on your PATH.

## Install plugin

Use pip.

```sh
pip install ctadl-taint-front-fact-generator
```

Afterward, if ctadl is installed, you can do:

```sh
ctadl import taint-front example.tnt
```

See `ctadl --help` for more detauls.
