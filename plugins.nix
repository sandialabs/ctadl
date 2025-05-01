{
  lib,
  callPackage,
  llvmPackages,
  jadxPlugin,
  ghidra,
  withPythonWheel,
}: let
  plugins = {
    taintfront = callPackage ./nix/taintfront/taintfront-plugin.nix {};
    ghidra = callPackage ./nix/ghidra/plugin.nix {inherit ghidra;};
    networkxExport = callPackage ./nix/export/networkx.nix {};
  };
in
  {jadx = jadxPlugin;}
  // (
    lib.attrsets.mapAttrs (name: pkg: pkg.overrideAttrs withPythonWheel) plugins
  )
