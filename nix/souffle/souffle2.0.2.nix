{ stdenv, callPackage, lib, fetchFromGitHub
, autoreconfHook269, cmake
, openmp
, enable64BitDomain ? false
, enableDebug ? false
}:


let
  souffle = callPackage ./common.nix rec {
    version = "2.0.2";
    src = fetchFromGitHub {
      owner = "souffle-lang";
      repo = "souffle";
      rev = "${version}";
      sha256 = "1fa6yssgndrln8qbbw2j7j199glxp63irfrz1c2y424rq82mm2r5";
    };
    inherit openmp enableDebug enable64BitDomain;
  };
in
souffle.overrideAttrs (attrs: rec {

  # patches = [ ./git-and-completion.patch ./remove-cpack.patch ./remove-index-warning.patch ];

  nativeBuildInputs = (lib.remove cmake attrs.nativeBuildInputs) ++ [ autoreconfHook269 ];
  configureFlags = [ "--enable-openmp" ]
  ++ lib.optional enable64BitDomain "--enable-64bit-domain";

  # see 565a8e73e80a1bedbb6cc037209c39d631fc393f and parent commits upstream for
  # Wno-error fixes
  patchPhase = ''
    substituteInPlace ./src/Makefile.am \
      --replace '-Werror' '-Werror -Wno-error=deprecated -Wno-error=other'

    substituteInPlace configure.ac \
      --replace "souffle_version=$(git describe --tags --always)" "souffle_version=${attrs.version}"

    substituteInPlace ./src/souffle-config.in \
      --replace 'CXX=@CXX@' 'CXX="@CXX@"'
  '';

  NIX_CFLAGS_COMPILE =
    " -Wno-format-security";

  postFixup = ''
    wrapProgram "$out/bin/souffle-compile" --prefix CXXFLAGS " " "$souffleCompileIncludes $souffleCompileCxxFlags" --prefix LDFLAGS " " "$souffleCompileLdFlags"
  '';
})

