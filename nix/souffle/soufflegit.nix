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
    version = "e6cc66820e0d3c537f57aab2f5c80b0d54cb5208";
    src = fetchFromGitHub {
      #owner = "dbueno";
      #repo = "souffle";
      owner = "souffle-lang";
      repo = "souffle";
      "rev" = "${version}";
      "hash" = "sha256-e+AA7p3ag/RhqZ7iKvJoPRJLGjtjT7eJIUze+fpsP4A=";
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
