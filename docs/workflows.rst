Workflows
=========

The workflows covered below answer the question, "How can I use
CTADL to accomplish an analysis goal?"

Workflow - Iterate on sources & sinks
-------------------------------------

Running successful CTADL queries largely depends on how you model parts
of the SUT. Sources, sinks, sanitizers, and function models are
specified using our ```model_generator`` file
format <https://github.com/sandialabs/ctadl/blob/main/docs/models.md>`__;
the full schema is in `our schema
file <https://github.com/sandialabs/ctadl/blob/main/src/ctadl/models/ctadl-model-generator.schema.json>`__.

Say you’ve indexed a program and you want to model a function as a
*source*: you want to associate the taint label ``HttpContent`` with the
return value of the ``getContent()`` method from
``Lorg/apache/http/HttpEntity;``. You can generate a template to start
with using ``ctadl query --template -o query.json``. Write a source
model generator like this:

.. code:: json

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

Save this into ``query.json`` and run a query with it:

.. code:: sh

   ctadl query query.json

You can see if your models “take” by inspecting the source-sink models
afterward:

.. code:: sh

   ctadl inspect --dump-source-sink-models

This will dump, in ``model_generator`` format, the sources and sinks
that were matched by CTADL. Note that internally *all sources are
vertices of the data flow graph (not methods)*, so the dumped models
will match on variables, not methods. The model you get back might look
like this:

.. code:: json

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

While you can write models that ``find`` on ``variable`` like this,
matching on methods is typical. This output is primarily for users to
understand what matched.

If you want to set up sinks, just use the ``"sinks"`` model instead of
``"sources"``.

Once you’ve set up sources and sinks, CTADL query will compute any paths
between them. You can obtain these paths as SARIF. See the next
workflows for how to visualize the paths.

Workflow - Visualize path results with VSCode’s SARIF Viewer
------------------------------------------------------------

.. code:: sh

   ctadl query [query.json] --format sarif -o results.sarif

The query path results are saved into the file ``results.sarif``. You
can open this file in the `SARIF
Viewer <https://marketplace.visualstudio.com/items?itemName=MS-SarifVSCode.sarif-viewer>`__
(or the `SARIF
Explorer <https://marketplace.visualstudio.com/items?itemName=trailofbits.sarif-explorer>`__)
to browse the paths found, if any, from sources to sinks.

After installing the plugin, make sure to run VSCode on the ``sources``
directory of the import:

.. code:: sh

   code /path/to/import/sources 

In VSCode, ``File -> Open`` the ``results.sarif`` and it should open a
``SARIF Results`` pane. Click on a LOCATION to zoom in on a path. In the
ANALYSIS STEPS pane, click on part of a path to jump there in the
decompiled code.

Each step in the path refers to a taint flow, either into or out of a
vertex (tainted location). Flows with an asterisk (e.g. ``out of *``)
refer to a flow that crosses a function boundary. Vertexes may have a
couple of names, such as internal names (e.g. ``@retparameter``) and
source names (e.g., ``tmDevice``), and may have special roles
(e.g. ``parameter(1)``, a parameter of an associated function). We
provide as much info as we can in the ANALYSIS STEPS view to
contextualize each step of the taint flow.

.. figure::
   https://github.com/sandialabs/ctadl/raw/main/docs/VSCode-SARIF-screenshot.png
   :alt: Screenshot

   Screenshot

NOTE: This workflow has been principally tested with APKs. `File an
issue <https://github.com/sandialabs/ctadl/issues>`__ if it doesn’t work
with other languages.

Workflow - Find and fill in propagation models for external functions
---------------------------------------------------------------------

Taint analysis hits a hard stop during analysis if a function is not
properly modeled. Even something as simple as the following will lose
taint on ``z``:

::

   x = sourceOfData(); // x is tainted
   z = max(x, y); // taint on z is lost if max not modeled

To solve such a problem, you’d add a propagation model for ``max``.
Here’s our actual model for max in Java, which states that arguments 0
and 1 should propagate flows to the return value.

.. code:: json

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

It’s often tough to know which functions you, as a user, should model to
get optimal results. To hone in on such problems, after a query you can
dump partial models for black hole functions:

.. code:: sh

   ctadl query
   ctadl inspect --dump-black-hole-functions

This will dump *partial* propagation model generators, like the one
below. Partial models indicate where taint was lost and let you easily
supply where it should flow. The partial model below means the analyzer
(1) found that argument 1 (the String) of ``divideMessage`` was tainted
and that (2) the method ``divideMessage`` has no model, so the taint was
lost.

.. code:: json5

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

It’s up to you to decide what to do:

-  Sometimes the desirable behavior is to leave it unmodeled.
-  Sometimes you want to model it. So you would add an ``"output"``
   field to complete the partial propagation model.
-  Or you could add it as an endpoint (source or sink).

Reverse-taint that is lost in the reverse way is dumped as a partial
model with only an ``output`` field.

Advanced Workflow - Working with either sources or sinks, but not both
----------------------------------------------------------------------

Sometimes you have a question like, “What things eventually flow to the
sink I’m interested in?” This question has well-defined sinks (e.g., a
database ``execute()`` statement) but you don’t have a good idea, or
don’t care, where the data comes from. You want to learn about where the
data might come from.

NOTE: this workflow may generate huge amounts of results.

As an example, we’ll use ``execute`` method of two HTTP clients.

.. code:: json

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

Save to ``sink_models.json``. Run the query:

.. code:: sh

   ctadl query sink_models.json

::

   [...]
   summary of query results:
   0 source vertexes reach 0 sink vertexes
   0 source taint labels across 0 taint sources
   1 sink taint labels across 2 taint sinks
   0 instructions tainted by sources
   19 instructions backward-tainted by sinks

Note that there are no source vertices, only backward taint. We can’t
visualize paths because there’s no place for the paths to start. This
workflow simply computes an interprocedural backward slice, starting
from sinks.

To find paths, let’s add a special source that matches on ``has_code``;
this instructs CTADL to find sources that have no code, i.e., they’re
external:

.. code:: json

       {
         "find": "methods",
         "where": [{ "constraint": "has_code", "value": false }],
         "model": {
           "sources": [
             { "kind": "Data", "port": "Return" }
           ]
         }
       }

Paths in the results of this query will go from some external method’s
return value to our sinks. Run the query again:

.. code:: sh

   ctadl query --compute-slices backward sink_models.json

::

   summary of query results:
   2 source vertexes reach 2 sink vertexes
   1 source taint labels across 809 taint sources
   1 sink taint labels across 2 taint sinks
   12714 instructions tainted by sources
   19 instructions backward-tainted by sinks

We pass ``--compute-slices backward`` for efficiency, so that CTADL does
not try to compute forward slices from every method that has no code,
which could be lots. (CTADL defaults to only computing forward slices;
``--compute-slices`` lets you control the direction, or do both.) Now we
can visualize the paths with SARIF (see above).

Workflow - Analyze a SUT with libraries by linking code
-------------------------------------------------------

If the system under test (SUT) is factored into a main program with a
bunch of supporting libraries, such as a jar with many library jars, you
may want to merge them all together before analysis. This gives the most
accurate result.

In general, linking code together requires a process particular to the
SUT language. For this example, we’ll target Java jar files. We’ll
assume the Java program is composed of ``app.jar`` and two libraries,
``lib1.jar`` and ``lib2.jar``. You can use
`merjar <https://github.com/dbueno/merjar>`__ to merge them together.

.. code:: sh

   merjar -o app-with-libraries.jar app.jar lib1.jar lib2.jar
   ctadl import jadx app-with-libraries.jar -o ./app-with-libraries
   cd ./app-with-libraries
   ctadl index

Sometimes the resulting code is too large to analyze and CTADL consumes
too much memory. In that case, you can try the alternative discussed
next.

Workflow - Analyze a SUT with libraries by composing analyses
-------------------------------------------------------------

When the system under test (SUT) is factored into a main program with a
bunch of supporting libraries, such as a jar with many library jars,
merging them sometimes results in a problem that is too large. Because
CTADL is compositional, you can separately analyze the libraries and
compose the result with the main program. The result may not be as
precise as combining all the problems, but it’s way better than nothing.

We’ll assume the java program is composed of ``app.jar`` and two
libraries, ``lib1.jar`` and ``lib2.jar``. Import them:

.. code:: sh

   ctadl import jadx lib1.jar -o ./lib1
   ctadl import jadx lib2.jar -o ./lib2
   ctadl import jadx app.jar -o ./app

We now should have three directories, ``lib1``, ``lib2``, and ``app``.
Next, analyze the libraries alone:

.. code:: sh

   cd lib1 && ctadl index
   cd lib2 && ctadl index

Finally, extract the function summaries as models to run together with
the main app:

.. code:: sh

   ctadl inspect -i lib1/ctadlir.db --dump-summaries > lib1-models.json
    ctadl inspect -i lib2/ctadlir.db --dump-summaries > lib2-models.json

   # combine the models files with jq:
   jq -s '{ model_generators: map(.model_generators) | add }' lib1-models.json lib2-models.json > all-lib-models.json

   # index again but with lib models
   cd ./app
   ctadl index --models all-lib-models.json

If you look at the summaries, for example in ``lib1-models.json``,
you’ll see *propagation models*. These allow you to say things like,
“for the method ``toString``, data flows from ``this`` to the return
value.” Feeding propagation models to ``ctadl index`` results in
function summaries.

Workflow - Work with Datalog directly
-------------------------------------

Our data flow and query analyses are written in Datalog. Users wishing
to add some extra Datalog can do so as follows:

.. code:: sh

    ctadl index --dl extra.dl # appends extra.dl to the indexer
    ctadl query --dl extra.dl # appends extra.dl to the query

You can also run souffle yourself on the ``index.dl`` and ``query.dl``
files produced by the ``index`` and ``query`` commands, respectively.
Queries can use Datalog and model generators at the same time.
