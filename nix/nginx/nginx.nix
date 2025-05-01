{ self
, makeWrapper
, fetchFromGitHub
, fetchzip
, stdenv
, zlib
, libxcrypt
, lib 
}:

stdenv.mkDerivation rec {
  pname = "nginx";
  version = "1.24.0";

  src = fetchzip {
    url = "https://nginx.org/download/${pname}-${version}.tar.gz";
    sha256 = "sha256-Alm9XPSARyAeiA+ePXhTlE/gKY4zUP2Wa/+ZdM+G8E8=";
  };

  enableParallelBuilding = true;
  dontStrip = true;

  buildInputs = [ zlib libxcrypt ];

  configureFlags = [
    "--with-debug"
    "--with-cc-opt=-gdwarf-4"
    "--without-http_gzip_module"
    "--without-http_rewrite_module"
  ];

  postFixup = lib.optionalString stdenv.isDarwin ''
    dsymutil $out/bin/nginx
  '';

}
