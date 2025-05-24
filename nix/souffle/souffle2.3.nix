{ stdenv, lib, callPackage, fetchFromGitHub
, bash
, python3
, openmp ? null
, enableOpenMP ? true
, enable64BitDomain ? false
, enableDebug ? false
, enableSanitizeMemory ? false
}:


let
  souffle = callPackage ./common.nix rec {
    inherit stdenv;
    version = "2.3";
    src = fetchFromGitHub {
      owner = "dbueno";
      repo = "souffle";
      rev = "v${version}-fix-sqlite";
      sha256 = "sha256-d8Nsd0501L4xsl6L15D0OLxJUylcodLpqb2TykSkczA=";
    };
    inherit openmp enableOpenMP enableDebug enable64BitDomain python3;
  };
  toolsPath = lib.makeBinPath [ stdenv.cc ];
in
souffle.overrideAttrs (attrs: rec {

  patches = [ ./remove-lld.patch ];

  preConfigure = ''
    substituteInPlace src/main.cpp \
          --replace 'const char* interpreter = "python3";' 'const char* interpreter = "${bash}/bin/bash";'
    substituteInPlace src/main.cpp \
        --replace 'bool endInput() {' 'bool endInput() override {'

    substituteInPlace src/CMakeLists.txt \
        --replace '\"source_include_dir\": \"''${CMAKE_CURRENT_SOURCE_DIR}/include\"' \
                  '\"source_include_dir\": \"''${CMAKE_INSTALL_PREFIX}/include\"'

  '';

  cmakeFlags = [ "-DSOUFFLE_GIT=0" "-DPACKAGE_VERSION=${attrs.version}" ]
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
    wrapPythonPrograms
  '';
})
