# CTADL PCODE frontend design

This section discusses the PCODE translation to CTADL IR.
It covers how we leverage decompiled code, giving details on how we handle variables, operands, fields, and functions.

The translation works on Ghidra's decompiled code.
Decompiled code looks like C, meaning variables have types & names, assignments are in SSA form, functions have fixed parameter counts (or are explicitly marked varargs), function bodies have fixed extents, etc.
These are features important for CTADL, which in particular operates on variables and fields.
We translate all code inside `HighFunctions`.

It's tempting to track flows using `HighVariable`s.
The problem is that it conflates low-level data flows.
Low-level flows occur on varnodes, and Ghidra keeps track of a mapping from varnodes to `HighVariable`s.
Ghidra uses a special `HighVariable` called `UNNAMED` when it doesn't know how to map a varnode to a `HighVariable`.
Two unrelated varnodes can both map to `UNNAMED` -- meaning there's no good reason to relate them.
If CTADL used the `High` objects, it would find many false flows.

Instead of `HighVariables`, we track all data flow on varnodes only.
Varnodes generalize registers and memory.
They denote an address space, an offset into the space, and a size.

Every PCODE operation takes varnode operands as input and output.
Our translation treats varnodes as variables, preserving almost all of the PCODE instructions.
Varnode is `(space, offset, size)`.

-   Ram and register varnodes are treated as global variables.

-   Varnode size is ignored.

CAST will lose type information.
Even propagating types.
There is no type information attached to the pcode.

We translate loads and stores using high types.
We rely on type information to map field accesses to offsets and field names.
This makes the code we generate clear, it makes the LOADS we generate correspond properly to fields, and it means that when users improve the types, CTADL's analysis improves, too.

Ghidra provides type information for HighVariables only, not Varnodes.
To get Varnode nodes, we follow links that map Varnode to HighVariable, then HighVariable to type.
We use the types to resolve field accesses.

Example PCODE for a field access looks like:

    b = PTRSUB a, 0x4
    c = LOAD(b)
    d = PTRSUB c, 0x8
    e = LOAD(d)

We find the structure type for `a`, use the offset `0x4` to retrieve its corresponding field, grab the field's name, and generate a move instruction `c := a.field`.

Unfortunately, some Varnodes do not map to any specific HighVariable and so we don't have type information for those.
For instance, Ghidra doesn't report the proper type for `c`.

I am thinking of doing intraprocedural flow solving in order to propagate these types.

    .decl isType
    .decl Varnode_GhidraType
    .decl Varnode_ReachingType

The Ghidra type is assigned by Ghidra, but doesn't cover all the Varnodes.
The Reaching type is calculing by solving an intraprocedural flow problem.

    isType :- Varnode_GhidraType(_, ty).
    Varnode_ReachingType :- Varnode_GhidraType
    Varnode_ReachingType(out, t_out) :-
        Varnode_ReachingType(in, t_in),
        TypeRule(_, out, t_out, in, t_in).

    TypeRule(i, out, t_out, in, t_in) :-
        PCODE_MNEMONIC(i, m),
        m = COPY; m = MULTIEQUAL;
        PCODE_INPUT(i, _, in),
        PCODE_OUTPUT(i, out),
        isType(t_in),
        t_out = t_in).

Each operation is translated into assignments.
Operations which use multiple operands, like addition and sign-extension, are translated to multiple assignments.
If an operand loads from memory, we compute its corresponding dereferenced access path.
Otherwise, the operand is a scalar, and we compute its corresponding bare access path.

Our translation handles nested field and array accesses.
Ghidra's decompiler expresses structure and constant-index array access using `PTRSUB` ("pointer subcomponent") and `PTRADD` operations.
We model these using the concept of GEPs (`GetElementPtr`s), borrowing vocabulary from LLVM IR.
A GEP stands for an arbitrarily long sequence of constant additions and multiplications, referring to a subcomponent of a structure with a pointer base.
Sequences of GEP loads are translate to nested field and array accesses.

Field names are used if name and type information is present.
This makes reading the output easier.

CTADL needs to know whether function arguments are passed by value or by reference.
For a given function paremeter, CTADL assumes that pointer parameters are pass-by-reference.
Otherwise the parameter is pass-by-value.

By default, CTADL attemps to resolve indirect calls (in `analysis/pcode/index.dl`).
When a pointer to a known function is assigned, its flow is tracked globally.
If the function pointer flows to an indirect call, CTADL records this as a call to the appropriate function.
This way CTADL resolves indirect calls.
It doesn't otherwise rely on Ghidra to resolve indirect calls.
This can be disabled by definining `CTADL_PCODE_DISABLE_INDIRECT_CALL_RESOLUTION`.

## Details


## Usage

We supply a Ghidra import script that generates the Souffle facts (`src/pcode/ExportPCodeForCTADL.java`).
Facts are just a set of relations.
The file `src/pcode/declarations.dl` contains the declared relations.
They cover all the relevant PCODE data types: `HighFunction`, `HighVariable`, `PCodeOp`, `Varnode`, all the `DataType` classes, `BlockBasic`, `FunctionPrototype`, and `HighSymbol`.
They are useful for many purposes: clients, even those who don't want to use CTADL (absit omen!), may import `src/pcode/import.dl` to read in these facts for themselves.

Clients can query varnodes flows and use the included PCODE facts to map varnode flows onto `HighVariable`s, if desired.
Here we use the facts to declare that all variables named `pcVar5` in the `main` function are sources:

    TaintSourceVertex("Network", vn, "" /* empty access path */) :-
        HFUNC_NAME(m, "main"),   // m is main
        CVar_GetMethod(vn, m),   // vn is a varnode in main
        VNODE_HVAR(vn, hv),      // hv is vn's HighVar
        HVAR_NAME(hv, "pcVar5"). // hv's name is pcVar5

# Limitations

-   We assume the decompiled code uses only one address space (input 0 of
    `LOAD` and `STORE`). If more than one is used, an error message is emitted
    in the `ErrorTranslation` relation.
-   We don't support varargs.
-   The import script isn't currently parallelized so it may take some time

# Questions

# Debugging

You can define `CTADL_PCODE_PRINT` to get a relation `PCodePrint2` that shows the symbolic pcode for every instruction.

# Known Issues

- Some variables don't have addresses.
  It appears that the pc address can be missing if Ghidra doesn't know the calling convention.

