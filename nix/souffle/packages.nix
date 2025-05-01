{
  stdenv,
  callPackage,
  llvmPackages,
  clangStdenv,
  gccStdenv
}: rec {
  souffle_clang = callPackage ./souffle2.1.nix {
    stdenv = clangStdenv;
    inherit (llvmPackages) openmp;
  };
  souffle_gcc = callPackage ./souffle2.1.nix {
    stdenv = gccStdenv;
    inherit (llvmPackages) openmp;
  };
  souffle202 = callPackage ./souffle2.0.2.nix {inherit (llvmPackages) openmp;};
  souffle21 = callPackage ./souffle2.1.nix {inherit (llvmPackages) openmp;};
  souffle22 = callPackage ./souffle2.2.nix {inherit (llvmPackages) openmp;};
  souffle23 = callPackage ./souffle2.3.nix {inherit (llvmPackages) openmp;};
  souffle23_64bit = callPackage ./souffle2.3.nix {
    inherit (llvmPackages) openmp;
    enable64BitDomain = true;
  };
  souffle24 = callPackage ./souffle2.4.nix {inherit (llvmPackages) openmp;};
  souffle24_64bit = callPackage ./souffle2.4.nix {
    inherit (llvmPackages) openmp;
    enable64BitDomain = true;
  };
  souffle23_debug = callPackage ./souffle2.3.nix {
    inherit (llvmPackages) openmp;
    enableSanitizeMemory = true;
  };
  souffle241 = callPackage ./souffle2.4.1.nix {inherit (llvmPackages) openmp;};
  souffle241_64bit = callPackage ./souffle2.4.1.nix {
    inherit (llvmPackages) openmp;
    enable64BitDomain = true;
  };

  souffle23_no_openmp = callPackage ./souffle2.3.nix {enableOpenMP = false;};
  souffle23_64bit_no_openmp = callPackage ./souffle2.3.nix {
    enable64BitDomain = true;
    enableOpenMP = false;
  };
  souffle24_64bit_no_openmp = callPackage ./souffle2.4.nix {
    enable64BitDomain = true;
    enableOpenMP = false;
  };
  souffle241_64bit_no_openmp = callPackage ./souffle2.4.1.nix {
    enable64BitDomain = true;
    enableOpenMP = false;
  };
  soufflegit_64bit_no_openmp = callPackage ./soufflegit.nix {
    enable64BitDomain = true;
    enableOpenMP = false;
  };
  souffle =
    if stdenv.system == "aarch64-darwin"
    then souffle23_64bit_no_openmp
    else souffle23_64bit;
}
