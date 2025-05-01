{ stdenv, lib, fetchFromGitHub, fetchgit
, perl, ncurses, zlib, sqlite, libffi, libtool
, mcpp, bison, flex, doxygen, graphviz
, makeWrapper, openmp, which, cmake
, python3
, llvmPackages
, src
, version
, macosx-version-min ? "10.14"
, enableOpenMP
, enable64BitDomain
, enableDebug
}:


let
  toolsPath = lib.makeBinPath [ mcpp stdenv.cc ];
  libsPath = lib.makeLibraryPath ([ stdenv.cc.cc ] ++ lib.optional stdenv.cc.isClang llvmPackages.libcxxabi);
in
stdenv.mkDerivation rec {
  pname = "souffle";
  inherit src version;

  enableParallelBuilding = true;
  nativeBuildInputs = [ cmake bison flex mcpp makeWrapper libtool which python3.pkgs.wrapPython ];
  buildInputs = [ ncurses zlib sqlite libffi ]
  ++ lib.optional (stdenv.cc.isClang  && enableOpenMP) openmp;

  postPatch = ''
    substituteInPlace CMakeLists.txt \
      --replace "''${SOUFFLE_VERSION}" "${version}"
  '';

  # CXX gets embedded into the software, so we want to expand it to a full path
  # macosx-version-min used to ensure aligned allocators are available
  # NIX_CFLAGS_COMPILE= [ "-fno-aligned-allocation" ]; # also works
  preConfigure = ''
    ${ lib.optionalString stdenv.isDarwin "MACOSX_DEPLOYMENT_TARGET=${macosx-version-min}" }
  '';

  cmakeFlags = []
    ++ (if enableOpenMP then [ "-DSOUFFLE_USE_OPENMP=1" ] else [ "-DSOUFFLE_USE_OPENMP=0" ])
    ++ lib.optionals enable64BitDomain [ "-DSOUFFLE_DOMAIN_64BIT=ON" ]
    ++ lib.optionals enableDebug [ "-DCMAKE_BUILD_TYPE=Debug" ];

  CXXFLAGS = '' -Wno-unused-command-line-argument ${lib.optionalString stdenv.isDarwin "-mmacosx-version-min=${macosx-version-min}"}'';

  # to embed the C++ compiler, we also need various paths
  souffleCompileIncludes = "-I${ncurses.dev}/include -I${zlib.dev}/include -I${sqlite.dev}/include -I${libffi.dev}/include"
  + lib.optionalString (stdenv.cc.isClang && enableOpenMP) " -I${openmp}/include";

  souffleCompileCxxFlags = lib.optionalString stdenv.isDarwin "-mmacosx-version-min=${macosx-version-min}";

  souffleCompileLdFlags = "-L${ncurses}/lib -L${zlib}/lib -L${sqlite.out}/lib -L${libffi}/lib"
  + lib.optionalString (stdenv.cc.isClang && enableOpenMP) " -L${openmp}/lib"
  + lib.optionalString stdenv.cc.isClang " -L${llvmPackages.libcxxabi}/lib";

  # Ensure debug symbols when enableDebug is passed
  hardeningDisable = lib.optional enableDebug "all";
  dontStrip = enableDebug;

  # This needs to be set in the derivation in postInstall
  postInstallWrap = ''
    wrapProgram "$out/bin/souffle" --prefix PATH : "${toolsPath}"
  '';

  outputs = [ "out" ];

  meta = with lib; {
    description = "A translator of declarative Datalog programs into the C++ language";
    homepage    = "https://souffle-lang.github.io/";
    platforms   = platforms.unix;
    maintainers = with maintainers; [ thoughtpolice copumpkin wchresta ];
    license     = licenses.upl;
  };
}
