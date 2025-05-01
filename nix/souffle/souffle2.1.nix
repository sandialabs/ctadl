{ stdenv, callPackage, fetchFromGitHub
, openmp
, python3
, enable64BitDomain ? false
, enableDebug ? false
}:


let
  souffle = callPackage ./common.nix rec {
    version = "2.1";
    src = fetchFromGitHub {
      owner = "souffle-lang";
      repo = "souffle";
      rev = "${version}";
      sha256 = "11x3v78kciz8j8p1j0fppzcyl2lbm6ib4svj6a9cwi836p9h3fma";
    };
    inherit openmp enableDebug enable64BitDomain python3;
  };
in
souffle.overrideAttrs (attrs: rec {

  patches = [ ./git-and-completion.patch ./remove-cpack.patch ./remove-index-warning.patch ];

  NIX_CFLAGS_COMPILE =
    " -Wno-format-security";

  postFixup = ''
    wrapProgram "$out/bin/souffle-compile" --prefix CXXFLAGS " " "$souffleCompileIncludes $souffleCompileCxxFlags" --prefix LDFLAGS " " "$souffleCompileLdFlags"
  '';
})

