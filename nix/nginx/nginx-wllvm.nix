{
  self,
  makeWrapper,
  fetchFromGitHub,
  fetchzip,
  stdenv,
  llvmPackages,
  wllvm,
  zlib,
}:
stdenv.mkDerivation rec {
  pname = "nginx-llvm";
  version = "1.24.0";

  src = fetchzip {
    url = "https://nginx.org/download/${pname}-${version}.tar.gz";
    sha256 = "sha256-Alm9XPSARyAeiA+ePXhTlE/gKY4zUP2Wa/+ZdM+G8E8=";
  };

  enableParallelBuilding = true;

  buildInputs = [llvmPackages.llvm llvmPackages.clang zlib wllvm];

  preConfigure = ''
    export LLVM_COMPILER_PATH="${llvmPackages.clang}/bin"
    export LLVM_COMPILER=${
      if stdenv.cc.isClang
      then "clang"
      else "gcc"
    }
  '';

  configureFlags = [
    "--with-debug"
    "--with-cc='${wllvm}/bin/wllvm'"
    "--without-http_gzip_module"
    "--without-http_rewrite_module"
  ];

  postInstall = ''
    export LLVM_COMPILER_PATH="${llvmPackages.llvm}/bin"
    extract-bc $out/sbin/nginx
  '';
}
