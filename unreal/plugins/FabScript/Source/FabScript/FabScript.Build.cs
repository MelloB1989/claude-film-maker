using UnrealBuildTool;

public class FabScript : ModuleRules
{
	public FabScript(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.NoPCHs;  // built against a restored engine with no shared PCHs (film-ue plugin-build)
		bUseUnity = false;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new string[] { "Json", "JsonUtilities" });
	}
}
