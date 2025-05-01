# Handling Globals in CTADL

This document describes some options for handling globals in CTADL.

# Introduction

The CTADL IR language supports global variables.
They are used to model variables like `public static` variables in Java.
Unlike tidy intraprocedural data flow, globals can flow data from one function to many others.
A typical example is below, where `a` flows to `b` in `main` because of a global variable `g`.

```
var g;
main() {
    WriteGlobal(a);
    b = ReadGlobal();
}
WriteGlobal(p) {
    g = p;
}
ReadGlobal() {
    return g;
}
```

CTADL uses a threading strategy to model globals.

## Compositional strategy: Threading globals as parameters

One way to handle global variables compositionally is by threading them through each function as a parameter.
This way they are handled like local variables, they can occur in function summaries, be instantiated, etc.
Below is the same program as above, but transformed by removing and threading the global variable:

```
// var g; is removed
main(globals) {
    F(a, globals);
    b = H(globals);
}
WriteGlobal(p, globals) {
    globals.g = p;
}
ReadGlobal(, globals) {
    return globals.g;
}
```

An in-out parameter `globals` is added to each function, each global access is translated into a corresponding access of the `globals` parameter, and each call site threads the parameter.
For this instrumentation, one more thing needs to be done, which is not shown: the set of access paths is augmented with paths for each global.
The path added for this example is `.g`.
