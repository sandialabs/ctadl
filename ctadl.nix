{
  ctadl,
  lib,
  callPackage,
  stdenv,
  python3,
  souffle,
  mcpp,
  makeWrapper,
  withPythonWheel,
  llvmPackages,
  jdk ? null,
  enableRich ? true,
  enableJdk ? false,
  enableExternalIndexers ? true,
  ...
}: let
  withPlugins = plugins:
    python3.pkgs.buildPythonPackage {
      pname = "${ctadl.pname}-with-plugins";
      inherit (ctadl) version;
      format = "other";

      dontUnpack = true;
      dontBuild = true;
      doCheck = false;

      propagatedBuildInputs =
        plugins
        ++ ctadl.propagatedBuildInputs;
      pluginWrapArgs =
        lib.lists.concatMap (plugin: plugin.makeWrapperArgs or []) plugins;

      installPhase = ''
        runHook preInstall

        makeWrapperArgs+=(
          "''${pluginWrapArgs[@]}"
          --prefix PYTHONPATH ':' "${ctadl}/${python3.sitePackages}:$PYTHONPATH"
        )

        mkdir -p $out
        for file in ctadl; do
          makeWrapper "${ctadl}/bin/$file" "$out/bin/$file" \
            ''${makeWrapperArgs[@]}
        done
        ln -sfv ${ctadl}/lib $out/lib

        runHook postInstall
      '';

      passthru =
        ctadl.passthru
        // {
          withPlugins = morePlugins: withPlugins (morePlugins ++ plugins);
        };

      meta.mainProgram = "ctadl";
    };
  pkg = python3.pkgs.buildPythonPackage rec {
    pname = "ctadl";
    version = lib.strings.removeSuffix "\n" (builtins.readFile ./src/ctadl/VERSION);

    src = with builtins;
      builtins.path {
        path = ./.;
        name = "ctadl-${version}";
        filter = path: type: let
          ignoreFiles = ["tests/bin/test"];
          ignoreDirs = ["nix" "refimpl" "lib" "talks" "jars" "utils" "benchtest" "release_scripts"];
        in
          if
            (lib.lists.any (p: (builtins.match (".*" + p) path != null)) ignoreFiles)
            || (lib.lists.any (p: p == (baseNameOf path)) ignoreDirs)
          then false
          else true;
      };

    # disable tests, won't work without index which can't be generated without building
    doCheck = false;

    nativeBuildInputs =
      [makeWrapper souffle]
      ++ (with python3.pkgs; [setuptools]);
    propagatedBuildInputs = with python3.pkgs;
      [jsonschema psutil json5 mcpp]
      ++ lib.optionals enableRich [rich];

    passthru = {
      inherit jdk withPlugins python3;
    };

    prePatch = ''
      patchShebangs src/ctadl/souffle-logic/pcode
    '';

    makeWrapperArgs =
      [
        ''--prefix PATH ':' "${lib.makeBinPath [souffle]}"''
      ]
      ++ lib.optionals stdenv.cc.isClang [
        ''--set LDFLAGS "-L${llvmPackages.libcxxabi}/lib"''
      ]
      ++ lib.optionals enableJdk [
        ''--set JAVA_HOME "${jdk.home}"''
      ];

    meta.mainProgram = "ctadl";
  };
in
  pkg.overrideAttrs withPythonWheel
