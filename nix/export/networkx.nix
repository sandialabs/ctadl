{
  python3,
  makeWrapper,
  lib,
}:
python3.pkgs.buildPythonPackage rec {
  pname = "ctadl-networkx-export-plugin";
  version = lib.strings.removeSuffix "\n" (builtins.readFile ../../plugins/networkx-export/src/ctadl_networkx_export_plugin/VERSION);
  src = ../../plugins/networkx-export;

  doCheck = false;

  nativeBuildInputs = [] ++ (with python3.pkgs; [setuptools]);
  propagatedBuildInputs = with python3.pkgs; [networkx];
}
