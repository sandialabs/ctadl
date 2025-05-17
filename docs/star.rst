Star abstraction
================

This document explains star abstraction, the ``index --star`` option.

Introduction
------------

CTADL may lose data flows when analyzing field accesses. When this
three-line program runs,  [1]_

::

   a = p;
   b = a.f;    // b <- p.f
   c = b.g;    // c <- p.f.g

``p.f.g`` flows into ``c``, as shown in the commented code, but CTADL
won’t discover this. CTADL follows assignments statements to discover
data flow, but the desired flow isn’t manifest in these assignments
alone. So CTADL elaborates them using a fixpoint process called field
propagation. Field propagation makes field accesses explicit: it uses
existing accesses and assignments to derives new assignments, unfurling
field accesses. For the program above, it propagates the existing access
``a.f`` onto assignment ``a = p``, deriving:

::

   a.f = p.f; (1)

This makes the implicit field assignment ``p.f`` explicit. CTADL then
tries to propagate ``b.g`` onto ``b = a.f``, deriving:

::

   b.g = a.f.g; (2*)

but it cannot, because the access path (AP) ``.f.g`` is restricted: it
does not occur in the program text.  [2]_ Consequently CTADL thinks
there is no data flow from ``p.f.g`` to ``c``.

We’d like to infer the missing flow. To that end, we introduce ``.*`` as
a wildcard standing for any non-empty AP. When CTADL fails to propagate
a restricted access path, star abstraction will instead introduce a star
access. In place of (2\*) above, it derives the assignment:

::

   b.g = a.f.*; (2)

meaning that every subfield of ``a.f`` flows to ``b.g``. This
approximates the assignment (2\*) at the expense of precision.
Subsequently propagating ``a.f.*`` on (1) adds the assignment:

::

   a.f.* = p.f.*;

Using the original and derived assignments, CTADL can now discover:

::

   p.f.g -> p.f.* -> a.f.* -> b.g -> c

This gives us the data flow we wanted and indicates that we’ve lost the
flow’s precise location.

Star abstraction rules
----------------------

Star creation is implemented as three rules: star-forward,
star-backward, and star-summary. The direction, forward or backward,
refers to the direction of the star relative to assignment direction.
(It also mirrors the direction of propagation.) We’ll state the rules in
a simple form under the following assumptions:

-  ``.p``, ``.q``, ``.f``, ``.f.q`` are known APs, i.e., they’re in the
   program text
-  ``.p.q`` is not a known AP
-  ``y.f.q`` is in the program text, not show in the original fragments
   below

each rule introduces ``x.p.*`` because ``x.p.q`` cannot be represented
otherwise.

star-forward
~~~~~~~~~~~~

::

   x.p = y.f;     // this assignment is in the program
   =>
   x.p.* = y.f.q; // star-abstraction introduces this assignment

Since ``x.p.q`` is restricted, a star is created on the left-hand side.

star-backward
~~~~~~~~~~~~~

::

   y.f = x.p;     // this assignment is in the program
   =>
   y.f.q = x.p.*; // star-abstraction introduces this assignment

Since ``x.p.q`` is restricted, a star is created on the right-hand side.

star-summary
~~~~~~~~~~~~

::

   // p1.q <- p2.q is the summary of A
   def A(p1, p2) {
       p1.q = p2.q;
   }
   def B(x, y) {
       A(x, y); // x.p := y.q is the instantiated summary

       A(x.p, y.f);
       =>
       x.p.* = y.f.q // star-abstraction introduces this assignment
   }

CTADL computes the summary for ``A`` first and then tries to instantiate
it at each call site. The first call to ``A`` can be instantiated
without star abstraction, resulting in the assignment above. This
assignment is created inside ``B``, onto its local variables.

Instantiation can fail, like field propagation, because of a restricted
path. So, for the second call, star abstraction instantiates the star
assignment above. Since ``x.p.q`` cannot be represented, it is
abstracted.

Discussion
----------

Star abstraction complements, but doesn’t replace, field propagation.
When propagating, a star access is treated like a normal field access.
Star abstraction introduces star accesses; field propagation derives
assignments from existing accesses, including star accesses.

Star abstraction ensures termination
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If CTADL were to create unrestricted access paths, it would not
terminate in general. The following code processes nodes in a linked
list:

::

   while (x) {
       t = x.next;
       process(x);
       x = t;
   }

CTADL properly propagates ``x.next`` onto ``x = t``, deriving the
assignment:

::

   x.next = t.next; (3)

If we lift the restriction on access paths, it would propagate
``t.next`` onto ``t = x.next``, deriving the assignment:

::

   t.next = x.next.next; (4)

But now the access ``x.next.next`` needs to be propagated more, so the
process goes on and on. The pattern will create ``x.next.next... .next``
arbitrarily many times (it will also do the same for ``t.next...``). The
analysis doesn’t terminate.

Star abstraction introduces the following star assignment instead of
(4):

::

   t.next = x.next.*;   // introduced by star assignment
   x.next.* = t.next.*; // derived by propagation

Field propagation adds the second assignment and the analysis
terminates.

Queries
-------

Taint queries require you, the user, to select source and sink accesses.
Prior to star abstraction, the only accesses you might refer to occur in
the target program, so they’re easy to select. Star abstraction with
field propagation creates new accesses which are hard for you to
predict. But you shouldn’t have to predict them. Instead, CTADL matches
your query accesses with those created during analysis.

For instance, you can set up ``p.f.g.h.i.j.k`` as a taint source for the
first example program; this location does not exist in the program or
the analysis. CTADL concludes that taint may flow to ``c`` from this
source. How? The star access ``p.f.*`` is selected as a taint source
because it matches the taint source ``p.f.g.h.i.j.k``. Once you also
designate ``c`` as a sink, CTADL concludes there is a taint flow from
source to sink.

Beware that star abstraction designates only non-empty field access
paths. Consider what happens if we designate ``c.*`` as a sink instead
of ``c``. CTADL concludes there is no taint flow, because there is no
flow to a subfield of ``c``, only to ``c`` itself. If you want to know
if there is a flow to anywhere in ``c``, including ``c`` itself, just
set up two sinks: ``c`` and ``c.*``.

Matching
--------

Star isn’t about matching. There is no process that takes existing
vertices like ``x.foo`` and matches thom with ``x.*`` and propagates
information about the former to the latter. Star is about providing a
handle (the star vertex) on field-aggregated information. Any such
information should be directly assigned to and read from star.

Summary
-------

CTADL, by design, operates on a finite set of APs. Before star
abstraction, CTADL lost flows which cannot be represented on that set of
APs. Star abstraction introduces star assignments, which represent new
flows that approximate the lost flows. Star abstraction is introduced
for local assigments and at call sites. Star abstraction at worst
doubles the set of APs, keeping it finite. Star abstraction is optional,
since it may approximate in undesirable ways.

Usage
-----

Define ``CTADL_ENABLE_STAR`` before running CTADL.

In queries, use the ``STAR`` macro to append stars onto access paths:

::

   // for example program
   // source
   taint.TaintSourceVertex("Input", "F/p", ".f.g.h.i.j.k").

   // sinks
   taint.LeakingSinkVertex("Input", "F/c", "").   // leak into c
   taint.LeakingSinkVertex("Input", "F/c", STAR). // no leak
   taint.LeakingSinkVertex("Input", "F/b", STAR). // leak into b.g

Implementation notes
--------------------

Star abstraction is done by concatenating a string ``..*`` onto access
paths. The string ``..*`` is used instead of ``.*`` because then we can
directly use Souffle’s ``match`` operator to handle taint queries.
``match`` uses ``.*`` to match possibly empty strings and the first
period is the field separator. The star-forward and star-backward rules
are implemented like the propagation rules, as macros with one argument.
The argument denotes the ``MatchPrefix`` case (there are four cases).

To prevent infinite paths, the star rules have two constraints: (1) They
only consult non-star virtual-assignments. (2) They ensure the
constructed star path exactly one star.

Footnotes
---------

.. [1]
   You can play around with this program using the ``taint-front``
   language. The program is in ``taint-front/star3.md``.

.. [2]
   The propagation restriction ensures CTADL’s analysis terminates.
   Later we explain why and how star abstraction addresses this.
