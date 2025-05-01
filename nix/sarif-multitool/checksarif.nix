{
  stdenv,
  callPackage,
  fetchFromGitHub,
  writeShellScriptBin,
}: let
  sarif-multitool = callPackage ./default.nix {};
  sarif-spec = stdenv.mkDerivation {
    name = "sarif-spec";
    version = "2.1.0";
    src = fetchFromGitHub {
      owner = "oasis-tcs";
      repo = "sarif-spec";
      "rev" = "53296faddf08e610230739d7d6a2f061f6e587d8";
      "hash" = "sha256-44UTa4DdXrF4DB2EtZO22wv1b/p1sLMKYKyLEBF0UeA=";
    };
    installPhase = ''
      mkdir $out
      cp -r * $out
    '';
  };
in
  writeShellScriptBin "checksarif" ''
    export DOTNET_ROLL_FORWARD=Major
    exec ${sarif-multitool}/bin/sarif validate -c ${./sarif-validation.xml} -j ${sarif-spec}/Schemata/sarif-schema-2.1.0.json "$@"
  ''
