{ gccStdenv, lib, callPackage, fetchFromGitHub
, python3
, openmp ? null
, enableOpenMP ? true
, enable64BitDomain ? false
, enableDebug ? false
, enableSanitizeMemory ? false
}:


let
  souffle = callPackage ./common.nix rec {
    stdenv = gccStdenv;
    version = "2.4.1";
    src = fetchFromGitHub {
      #owner = "dbueno";
      #repo = "souffle";
      owner = "souffle-lang";
      repo = "souffle";
      "rev" = "01f11777b4b09329b8232466d82376e039ac1ba8";
      "hash" = "sha256-U3/1iNOLFzuXiBsVDAc5AXnK4F982Uifp18jjFNUv2o=";
    };
    inherit openmp enableOpenMP enableDebug enable64BitDomain python3;
  };
  toolsPath = lib.makeBinPath [ gccStdenv.cc ];
in
souffle.overrideAttrs (attrs: rec {

  patches = [ ./souffle-2.4.patch ];
  # ./souffle-2.3-sources.patch ];

  cmakeFlags = [ "-DSOUFFLE_GIT=0" "-DPACKAGE_VERSION=${attrs.version}" "-DVERBOSE=1" ]
  ++ lib.optional enableSanitizeMemory "-DSOUFFLE_SANITISE_MEMORY=ON"
  ++ attrs.cmakeFlags;

  postInstall = ''
    sed 's#"includes": "#"includes": "-I'$out'/include ${attrs.souffleCompileIncludes} #' -i $out/bin/souffle-compile.py
    sed 's#"cxx_flags": "#"cxx_flags": " ${attrs.souffleCompileCxxFlags} #' -i $out/bin/souffle-compile.py
    sed 's#"link_options": "#"link_options": "${attrs.souffleCompileLdFlags} #' -i $out/bin/souffle-compile.py
    ${attrs.postInstallWrap}
    wrapProgram "$out/bin/souffle-compile.py" \
      --prefix PATH : "${toolsPath}"
  '';

  postFixup = ''
    sed 's#"includes": "#"includes": "${attrs.souffleCompileIncludes} #' -i $out/bin/souffle-compile.py
    sed "s#\"includes\": \"#\"includes\": \"-I$out/include #" -i $out/bin/souffle-compile.py
    sed 's#"cxx_flags": "#"cxx_flags": " ${attrs.souffleCompileCxxFlags} #' -i $out/bin/souffle-compile.py
    sed 's#"link_options": "#"link_options": "${attrs.souffleCompileLdFlags} #' -i $out/bin/souffle-compile.py
    wrapPythonPrograms
  '';
})
