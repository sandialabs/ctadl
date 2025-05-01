# CTADL-SARIF overview

CTADL provides [SARIF-formatted](https://sarifweb.azurewebsites.net) query results.

```
$ ctadl query --format sarif -o results.sarif
```

We designed our SARIF output to enable visualizations of taint results.
Because SARIF is a complex format covering a variety of use cases, we provide here a description of how CTADL uses SARIF.

A CTADL SARIF file has a single run and tool.
Each rule in the SARIF file is a particular kind of taint output, which is also described in the file itself.
Each result in the SARIF file is associated with a single rule ID (as the SARIF spec requires); it is an instance of the thing described by the rule.

CTADL rules and their meanings:

- `C0001`: A result of this type is a connected path from a source to a sink.
- `C0002`: A result of this type is an instruction that manipulates tainted data.
- `C0003`: A vertex (variable + field/array access) that is tagged as a source.
- `C0004`: A vertex that is tagged as a sink.
- `C0005`: A vertex that is tainted.
- `C0006`: A function that contains both forwards and backwards tainted data.

So each `C0005` result is a single tainted vertex; the set of all results of type `C0005` describe the set of all tainted vertices.

To get a SARIF file with every conceivable result, pass `--format=sarif+all`.

## `C0001` - Paths

The `--format=sarif` option outputs only results of this type.

Any tainted source-sink paths that CTADL finds are SARIF results for the `C0001` rule.
The steps of the path are described in the `codeFlows[0].threadFlows[0].locations` element of the result.
The first and last elements of the path correspond to source and sink vertices, respectively.
The intermediate elements are conceptually paired.
Each one is labeled by an "into" or "out of" to indicate the direction of taint flow for that step of the path.
This result type is intended primarily for loading in a SARIF viewer such as VSCode.

## `C0002` - Tainted instructions

CTADL works forward from sources and backward from sinks to propagate taint.
Each instruction which manipulates tainted data is included in `C0002` results.
The taint label associated with the source or sink in the query can be used to distinguish source-tainted from sink-tainted instructions.

## `C0003` - Source vertices

Sources are specified with the datalog relation `TaintSourceVertex` and are matched against the code under analysis.
Any locations that match are tagged as sources.
These locations may include fields/arrays.

## `C0004` - Sink vertices

Sinks are specified with the datalog relation `LeakingSinkVertex` and are matched against the code under analysis.
Any locations that match are tagged as sinks.
These locations may include fields/arrays.

## `C0005` - Tainted vertices

When propagating taint, CTADL aggregates all vertices that are reached.
They are all included in `C0005` results.
The taint label associated with the source or sink in the query can be used to distinguish source-tainted from sink-tainted vertices.

## `C0006` - Almost-path functions

If any functoin is found to have at least one source-tainted variable and at least one sink-tainted variable, it is reported as a `C0006` result. The intuition is that such functions *almost* form a path from source to sink.

To get these results, both forward and backward slices must be enabled during a query.

## Source Taint Graph

In addition to the rules above, we include forward (source-sink) and backward (sink-source) slices as graphs.
(See the `--format=sarif+graphs` option.)
The forward slice is an interprocedural graph containing taint sources, their labels, and all the vertices forward reachable from the sources, with the approriate labels.
The backward slice is an interprocedural graph containing taint sinks, their labels, and all the vertices backward reachable from the sinks, with the approriate labels.
Each node in the graph corresponds a vertex. Each edge in the graph corresponds to an instruction.
The `graphs[0]` member contains the forward slice, and the `graphs[1]` member contains the backward slice.

# Use Cases

## SARIF Viewer

CTADL SARIF files can be viewed with the [VSCode Sarif Viewer](https://marketplace.visualstudio.com/items?itemName%253DMS-SarifVSCode.sarif-viewer).

# Glossary

## Vertex

A *vertex* is a node in the data flow graph associated with a variable and possible a field/array access. The following are all vertices:

- `x`
- `x.foo`
- `treeNode.data[3].left`

It's a location where the program can store data.

## SARIF Locations

The `locations` array at the top-level are referred to elsewhere in the SARIF.
Note that the locations array itself is just a database of addresses and locations; it don't have any other inherent meaning.
In particular just because there is a vertex is `locations` does not mean the vertex is tainted.

### Logical Locations

Every SARIF result is reported with a logical location.

For all languages, CTADL reports a logical location for every function, instruction, and vertex.
A vertex is either global or local.
If it is local, it has a parent logical location, a function.
Instructions are all local and have a parent logical location, a function.
Functions may have a parent logical location, a namespace.

Each function, instruction, and variable has a `decoratedName` which is the ID by which CTADL refers to that thing.
If available, each variable and function has a short `name` and a `fullyQualifiedName`.
For instance, here is a variable location from one of our taintbench benchmarks:

```json
{
  "name": "urlString",
  "fullyQualifiedName": "Lcom/adobe/flashplayer_/FlashVirtual;.doInBackground2:([Ljava/lang/String;)Ljava/lang/String;::urlString",
  "decoratedName": "Lcom/adobe/flashplayer_/FlashVirtual;.doInBackground2:([Ljava/lang/String;)Ljava/lang/String;/ssa/r19v0",
  "kind": "variable",
  "parentIndex": 5137
}
```

As seen above, variables can have two names: an internal name (the `ssa/r19v0` at the end of the `decoratedName) and a source name (`urlString`).

### Physical Locations

When available, every SARIF result is reported with a physical location.
- When analyzing Ghidra PCODE, CTADL tags vertices and instructions with address locations (if available).
- When analyzing Java, CTADL tags vertices and instructions with source locations (if available).

Physical locations are associated with logical locations when they co-occur inside a `locations` array in a `result`.
For example, the following associates logical location at index 91 with the given address:

```json
"locations": [
{
  "physicalLocation": {
    "artifactLocation": {
      "uri": "C:\\\\Person\\\\binary.exe"
    },
    "address": {
      "absoluteAddress": 16786032,
      "kind": "instruction",
      "fullyQualifiedName": "FUN_010021f0@010021f0:01002270:138"
    }
  },
  "logicalLocations": [
    {
      "index": 91
    }
  ]
}
]
```
