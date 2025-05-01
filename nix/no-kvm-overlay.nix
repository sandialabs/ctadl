# Building docker images with Nix requires kvm but CI doesn't support that,
# so we disable kvm the requirement with an overlay.
# See https://github.com/NixOS/nixpkgs/issues/67079
# This is still super hacky because other functions in vmTools will not use the overridden runInLinuxVM
final: prev:
    let
        runInLinuxVMNoKVM = drv: final.lib.overrideDerivation (final.vmTools.runInLinuxVM drv) (_: { requiredSystemFeatures = []; });
        modifiedVmTools = prev.vmTools // { runInLinuxVM = runInLinuxVMNoKVM; };
    in
    {
        dockerTools = prev.dockerTools.override { vmTools = modifiedVmTools; };
        singularity-tools = prev.singularity-tools.override { vmTools = modifiedVmTools; };
    }
