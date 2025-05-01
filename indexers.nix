{
  ctadl,
  lib,
  callPackage,
  stdenv,
  souffle,
  ...
}: let
  libfunctorsPkg = {souffle}: let
    shlibFlags =
      if stdenv.isDarwin
      then ''-dynamiclib -install_name @executable_path/libfunctors.dylib''
      else ''-shared -Wl,-soname,'$ORIGIN'/libfunctors.so'';
    shlibExt =
      if stdenv.isDarwin
      then "dylib"
      else "so";
  in
    stdenv.mkDerivation {
      pname = "ctadl-libfunctors";
      version = "${ctadl.version}";
      nativeBuildInputs = [souffle];
      dontUnpack = true;
      buildPhase = ''
        set -x
        c++ -O2 --std=c++17 -I ${souffle}/include -I ${souffle}/include/souffle ${./src/ctadl/souffle-logic/functors.cpp} -c -fPIC -o functors.o
        c++ ${shlibFlags} -o libfunctors.${shlibExt} functors.o
        set +x
      '';

      installPhase = ''
        mkdir $out
        cp libfunctors.${shlibExt} $out/
      '';
    };
  libfunctors = callPackage libfunctorsPkg {};
  # This package is to avoid datalog recompilation unless it's necessary.
  souffleCompileDatalog = {
    ctadl,
    python3,
    mcpp,
    datalogSpec,
    lib,
    souffle,
    libfunctors,
    souffleMacros ? [],
  }: let
    defaultMacros = [
      "CTADL_VERSION=${ctadl.version}"
      "CTADL_OUTPUT_DB=ctadlir.db"
      "CTADL_USE_GLOBAL_PARAM"
      "CTADL_INPUT_DB=ctadlir.db"
    ];
    #finalMacros = lib.strings.concatStringsSep " " (defaultMacros ++ (datalogSpec.macros or []));
    finalMacros = lib.strings.concatStringsSep " " (map (m: "-D" + m) (defaultMacros ++ (datalogSpec.macros or [])));
  in
    stdenv.mkDerivation {
      pname = "ctadl-analysis-${datalogSpec.language}";
      version = "${ctadl.version}";
      src = with builtins;
        builtins.path {
          path = ./src/ctadl/souffle-logic;
          name = "${datalogSpec.language}-${ctadl.version}";
          filter = path: type: type != "regular" || lib.strings.hasSuffix ".dl" path;
        };
      nativeBuildInputs = [souffle libfunctors python3 ctadl];

      buildPhase = ''
        ctadl dump-analysis --language ${datalogSpec.language} index -o analysis.dl
        echo $(python3 ${./utils/hashdl.py} analysis.dl)
        souffle -I. -L${libfunctors} -j8 analysis.dl -o "$(python3 ${./utils/hashdl.py} analysis.dl)"
        ctadl dump-analysis --language ${datalogSpec.language} query -o taintquery.dl
        echo $(python3 ${./utils/hashdl.py} taintquery.dl)
        souffle -I. -L${libfunctors} -j8 taintquery.dl -o "$(python3 ${./utils/hashdl.py} taintquery.dl)"
      '';

      installPhase = ''
        mkdir $out
        cp "$(python3 ${./utils/hashdl.py} analysis.dl)" $out
        cp "$(python3 ${./utils/hashdl.py} taintquery.dl)" $out
      '';
    };
  dlSpecs = [
    {language = "jadx";}
    {language = "taint-front";}
    {language = "pcode";}
  ];
  indexers = map (datalogSpec: callPackage souffleCompileDatalog {inherit libfunctors datalogSpec;}) dlSpecs;
  indexersPkg = stdenv.mkDerivation {
    pname = "ctadl-analysis";
    version = "${ctadl.version}";
    dontUnpack = true;
    dontBuild = true;
    installPhase = ''
      mkdir -p $out/ctadl/analysis/${ctadl.version}
      # Setuptools wants to build things in build/lib
      for d in ${lib.strings.concatStringsSep " " indexers}; do
        cp -f $d/* $out/ctadl/analysis/${ctadl.version}
      done
      cp -f ${libfunctors}/* $out/ctadl/analysis/${ctadl.version}
    '';
  };
in
  indexersPkg
