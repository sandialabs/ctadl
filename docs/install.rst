Installation
============

Dependency - Install Souffle
----------------------------

.. note::

   The only supported version of Souffle must be downloaded from
   `this fork on Github
   <https://github.com/dbueno/souffle/tree/v2.3-fix-sqlite>`__.

`Souffle <https://souffle-lang.github.io>`__ is the Datalog engine CTADL
uses to perform analysis. We require a `patched
version <https://github.com/dbueno/souffle/tree/v2.3-fix-sqlite>`__. Install
it into the path ``<prefix>`` like so:

.. code:: sh

   git clone --branch v2.3-fix-sqlite https://github.com/dbueno/souffle/tree/v2.3-fix-sqlite
   cd souffle
   # recommended config, substitute <prefix> for your install path
   cmake -S . -B build -DSOUFFLE_USE_OPENMP=1 -DCMAKE_BUILD_TYPE=Release -DSOUFFLE_DOMAIN_64BIT=ON -DCMAKE_INSTALL_PREFIX=<prefix> ..
   cmake --build build -j8
   cmake --build build --target install

-  **Note:** Souffle and CTADL require compiling C++ files with the
   *same* compiler. See the `known issues
   section <#known_issues_section>`__.

-  We recommend the CMake flag ``-DSOUFFLE_USE_OPENMP=1``, which
   compiles souffle with openmp support for parallel execution. (I
   believe it’s on by default.)

-  See `Souffle's docs <https://souffle-lang.github.io/build>`__ for a listing of its build dependencies. The following dependencies were sufficient on a fresh Ubuntu 24.04
   WSL installation:

   ::

      sudo apt install cmake libncurses-dev flex bison zlib1g-dev sqlite3 libsqlite3-dev libffi-dev build-essential

-  Windows users not using WSL, see our documentation for more info.

The `supported
version <https://github.com/dbueno/souffle/tree/v2.3-fix-sqlite>`__ is a
patched version of Souffle 2.3. The patch fixes round trips through
Souffle’s sqlite backend. The bug report is here:
https://github.com/souffle-lang/souffle/issues/2411.

Install CTADL
-------------

You can install CTADL with pip:

.. code:: sh

   python3 -mpip install ctadl ctadl-jadx-fact-generator-plugin ctadl-ghidra-fact-generator-plugin ctadl-taint-front-fact-generator-plugin

We recommend some optional libraries:

.. code:: sh

   python3 -mpip install psutil jsonschema rich

Their purpose:

- `psutil <https://pypi.org/project/psutil/>`__: to show
  live memory consumption (optional, but recommended as CTADL may use a
  lot of memory).

- `rich <https://pypi.org/project/rich/>`__: for pretty
  output.
  
- `jsonschema <https://pypi.org/project/jsonschema/>`__ (if
  omitted, no validation of models is performed): for validating model
  generators. When developing model generators by hand, we recommend
  installing this because it produces useful validation error messages.

Plugins implement import and export:

-  `ctadl-jadx-fact-generator-plugin <https://pypi.org/project/ctadl-jadx-fact-generator-plugin/>`__
   and `source
   repository <https://github.com/sandialabs/ctadl-jadx-fact-generator/releases>`__.
-  `ctadl-ghidra-fact-generator-plugin <https://pypi.org/project/ctadl-ghidra-fact-generator-plugin/>`__
-  `ctadl-taint-front-fact-generator-plugin <https://pypi.org/project/ctadl-taint-front-fact-generator-plugin/>`__.
-  `ctadl-networkx-export-plugin <https://pypi.org/project/ctadl-networkx-export-plugin/>`__

Docker distribution
-------------------

Our docker distribution contains CTADL plus all available plugins
and the tools they depend on. It isn’t small. Running it is a bit
fiddly because CTADL operates on a working directory model. One
has to be careful to associate host and container mounts, and run
CTADL in the right directory. Let’s assume your setup looks like
this:

-  Host machine:

   -  Artifact dir ``/path/to/artifacts`` that contains ``app.apk``
   -  Imports dir ``/path/to/imports`` where imports will be written

-  Container. Let’s make simple mounts:

   -  Maps host artifact dir to ``/artifacts``
   -  Maps host imports dir to ``/imports``
   -  Ensure we write to the imports dir using the ``--directory``
      option to CTADL
   -  Assume the container name is ``ctadl:latest``

The steps below show how to run docker, mounting these volumes, and
making sure CTADL is invoked appropriately so output is generated on the
host.

.. code:: sh

   docker load < ctadl-docker.tar.gz
   mkdir -p /path/to/imports/app
   docker run --rm -it --volume /path/to/artifacts:/artifacts --volume /path/to/imports:/imports \
       ctadl:latest --directory /imports import jadx app.apk -o app
   docker run --rm -it --volume /path/to/artifacts:/artifacts --volume /path/to/imports:/imports \
       ctadl:latest --directory /imports/app index
   docker run --rm -it --volume /path/to/artifacts:/artifacts --volume /path/to/imports:/imports \
       ctadl:latest --directory /imports/app query

To explain:

-  The ``--directory`` option that makes ``ctadl`` switch to the given
   directory in the container before writing its output. This ensures
   that index and query operate on the index corretly.
-  On import, ``-o app`` is also needed so that the output ends up at
   ``/path/to/imports/app`` on the host.

To simplify running CTADL in docker, we made `dctadl
<https://github.com/sandialabs/ctadl/blob/main/bin/dctadl>`__, a
standalone Python script that wraps up the rather complicated
docker command line behind the scenes. It provides a CLI
experience similar to running native CTADL when using docker. It’s
configurable so that it can wrap more complex docker commands (or
even use podman).

.. code:: sh

   dctadl --init # generates config file
   dctadl --directory ... # run ctadl using docker

If you have our docker distribution, you can copy the file
``/bin/dctadl`` from the container to your host with
```docker cp`` <https://docs.docker.com/reference/cli/docker/container/cp/>`__.
