{
  python3,
  makeWrapper,
  taintfront,
  lib,
}:
python3.pkgs.buildPythonPackage rec {
  pname = "ctadl-taint-front-fact-generator-plugin";
  version = lib.strings.removeSuffix "\n" (builtins.readFile ../../plugins/taint-front/src/ctadl_taint_front_fact_generator_plugin/VERSION);
  src = ../../plugins/taint-front;

  doCheck = false;

  passthru = {
    makeWrapperArgs = [
      ''--prefix PATH : ${lib.makeBinPath [taintfront]}''
    ];
  };
}
