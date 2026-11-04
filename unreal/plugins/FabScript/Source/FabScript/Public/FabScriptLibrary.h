// FabScript: the Fab plugin's AddToProject for editor Python (fmbridge fab.add).
//
// The Fab plugin's UFabBrowserApi (Engine/Plugins/Fab/Source/Fab/Private/FabBrowserApi.h) is bound to the Fab web
// page and none of it is BlueprintCallable; AddToProject takes FFabAssetMetadata, a USTRUCT with no Python type, so
// Python's call_method cannot build its arguments. This library finds the class and the function by name and fills
// the struct from JSON through reflection (no link to Fab's private code), so Epic's own import workflows run for
// every format: Quixel/Megascans glTF, generic glTF/FBX, unreal-engine packs (Build Patch Services).
#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "FabScriptLibrary.generated.h"

UCLASS()
class FABSCRIPT_API UFabScript : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Run UFabBrowserApi::AddToProject(DownloadUrl, Metadata). MetadataJson: {"AssetId", "AssetName", "AssetType",
	 *  "ListingType", "AssetNamespace", "DistributionPointBaseUrls": [], "IsQuixel"} as the Fab page passes them.
	 *  Returns "" when the workflow started, else what went wrong. The workflow runs on its own (Slate
	 *  notifications); watch /Game/Fab for the assets. */
	UFUNCTION(BlueprintCallable, Category = "FabScript")
	static FString AddToProject(const FString& DownloadUrl, const FString& MetadataJson);

	/** Same for UFabBrowserApi::InstallToProject (code plugins into the project). */
	UFUNCTION(BlueprintCallable, Category = "FabScript")
	static FString InstallToProject(const FString& DownloadUrl, const FString& MetadataJson);

	/** True when Fab has a signed-in user (the token itself never leaves C++). */
	UFUNCTION(BlueprintCallable, Category = "FabScript")
	static bool IsSignedIn();

	/** Open a Fab tab: the plugin then tries its saved sign-in (and the -AUTH_TYPE=exchangecode fallback). */
	UFUNCTION(BlueprintCallable, Category = "FabScript")
	static FString OpenFabTab();

	/** Whether the Fab plugin's API class is loaded at all. */
	UFUNCTION(BlueprintCallable, Category = "FabScript")
	static bool IsFabLoaded();
};
