Simple front-end for taint analysis
===================================

Make sure `menhir` is installed:

```
$ opam install menhir
```

Then compile with `dune`

```
$ dune build
```

Facts can then be generated:

```
$ ./_build/default/taintfront.exe test.tnt
```

This will compile `test.tnt` into the `facts` directory expected by `souffle`.

The language is fairly self explanatory -- see `test.tnt` for an example.
The frontend does not optimize any access paths -- it simply preserves what's in the source.

Sources, sanitizers, and sinks are specified using function call syntax.

    x = source(label);
    y = sanitize(x, label);
    sink(y, label);

`label` is the label for the source/sink.

