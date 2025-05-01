# CTADL

CTADL (pronounced "citadel" or mispronounced "see-taddle") is a static program slicer and taint analyzer.

It takes Java/Dex bytecode and Ghidra Pcode programs and allows you to query data flows inside and across procedures.
CTADL &mdash; which stands for Compositional Taint Analysis in DataLog &mdash; is customizable, performant, and uses simple heuristics.
CTADL supports the languages:

- Pcode from Ghidra,
- Java and Android using JADX, and
- taint-front, a custom language for hand-writing runnable taint analysis examples.

Its primary output format is [SARIF](docs/SARIF.md).

See the [CHANGELOG](./CHANGELOG.md).

# Install

See [INSTALL.md](INSTALL.md) for detailed installation instructions.

# Usage

- See the [tutorial](./docs/tutorial.md) to understand how to run `ctadl` to analyze a program and run a taint analysis (it's a couple-step process).
- See our [supported workflows](./docs/workflows.md) to understand how to visualize results, develop your own source/sink queries, analyze large programs, and more.

The rest of the documentation is in the [docs](./docs) directory.

# Support

- File an issue: <https://github.com/sandialabs/ctadl/issues>
- Ask a question: <https://github.com/sandialabs/ctadl/discussions>

## Known issues

- If the analyzer you compiled mysteriously crashes, it may be because the C++ compiler has been updated since the last time Souffle was installed.
  If you update the compiler, then souffle needs to be updated and all our analyses need to be recompiled.
  After you rebuild and reinstall Souffle, remove the `$XDG_CONFIG_DIR/share/ctadl/analysis` directory.
  On Windows the share directory is instead under `%APPDATA%`.
