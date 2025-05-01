#!/bin/sh

set -e
set -x

usage() { echo "$(basename $0) <facts dir> <headless-args>" >&2; exit 1; }

if [ $# -lt 1 ]; then
    usage
fi
factsdir=$1
shift

this_dir=$(dirname $(readlink -f $0))
tmpdir=$(mktemp -d)
trap 'rm -rf $tmpdir' EXIT
ghidra_bin=$(readlink -e $(which ghidra))
if [ ! -z "$GHIDRA_HOME" ]; then
    ghidra_base=$GHIDRA_HOME
elif [ ! -z "$ghidra_bin" ]; then
    ghidra_base=$(dirname "$ghidra_bin")
else
    echo "Could not find ghidra in path. Add 'ghidra' to path or set GHIDRA_HOME" >&2
    exit 1
fi
if [ -e "$ghidra_base/../lib/ghidra/support/analyzeHeadless" ]; then
    analyze_headless=$ghidra_base/../lib/ghidra/support/analyzeHeadless
elif [ -e "$ghidra_base/support/analyzeHeadless" ]; then
    analyze_headless=$ghidra_base/support/analyzeHeadless
else
    echo "Could not find ghidra analyzeHeadless from ghidra directory $ghidra_base" >&2
    exit 1
fi
echo "Analyze headless path: $analyze_headless" >&2

mkdir -p $(readlink -f $factsdir)
./analyzeHeadlessBigMem "$@" -scriptPath $this_dir -postScript ExportPCodeForCTADL.java $(readlink -f $factsdir)
