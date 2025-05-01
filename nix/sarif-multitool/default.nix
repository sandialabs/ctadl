{ buildDotnetGlobalTool, makeWrapper, lib }:
buildDotnetGlobalTool {
  pname = "Sarif.Multitool";
  version = "4.5.4";

  nativeBuildInputs = [ makeWrapper ];

  executables = [ "sarif" ];

  nugetSha256 = "sha256-OulbIBGGEMjLAIUTCQ55NJ4ikjex/UOwiCxTKkZedxA=";
}
