{ stdenv, callPackage, fetchFromGitHub, lib
, openmp
, python3
, enable64BitDomain ? false
, enableDebug ? false
}:


let
  souffle = callPackage ./common.nix rec {
    version = "2.2";
    src = fetchFromGitHub {
      owner = "dbueno";
      repo = "souffle";
      rev = "v${version}-fix-sqlite";
      sha256 = "sha256-0cMgsrguooEfrq/vOO8M16QvP9jxD2rVC+rutRlJ0IY=";
    };
    inherit openmp enableDebug enable64BitDomain python3;
  };
  toolsPath = lib.makeBinPath [ stdenv.cc ];
in
souffle.overrideAttrs (attrs: rec {

  patches = [ ./remove-lld.patch ];

  cmakeFlags = [ "-DSOUFFLE_GIT=0" "-DPACKAGE_VERSION=${attrs.version}" ]
  ++ attrs.cmakeFlags;

  postFixup = ''
    wrapProgram "$out/bin/souffle-compile" \
      --prefix PATH : "${toolsPath}" \
      --prefix CXXFLAGS " " "$souffleCompileIncludes $souffleCompileCxxFlags" \
      --prefix LDFLAGS " " "$souffleCompileLdFlags"
  '';
})

