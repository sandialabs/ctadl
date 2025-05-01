{ singularity-tools
, name
, ctadl
, souffle
, coreutils
, binutils
, less
, more
, additionalDeps ? [] }:
singularity-tools.buildImage {
  inherit name;
  diskSize = 1024*16;
  memSize = 1024*8;
  contents = [ coreutils binutils less more souffle ctadl ] ++ additionalDeps;
  runScript = "/bin/ctadl";
}
