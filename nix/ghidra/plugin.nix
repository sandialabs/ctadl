{
  python3,
  makeWrapper,
  lib,
  ghidra,
}:
python3.pkgs.buildPythonPackage rec {
  pname = "ctadl-ghidra-fact-generator-plugin";
  version = lib.strings.removeSuffix "\n" (builtins.readFile ../../plugins/ghidra/src/ctadl_ghidra_fact_generator_plugin/VERSION);
  src = ../../plugins/ghidra;
  pyproject = true;
  build-system = with python3.pkgs; [setuptools];

  doCheck = false;

  # Set here but useless. ctadl's .withPlugins knows how to use these args to wrap.
  passthru = {
    makeWrapperArgs = [
      ''--set GHIDRA_HOME ${ghidra}/lib/ghidra''
    ];
  };
}
