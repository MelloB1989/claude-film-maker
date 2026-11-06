// FMCloth: skeletal-mesh Chaos cloth for editor Python (fmbridge cloth.setup, qa.cloth).
//
// In UE 5.8 a skeletal mesh's clothing data is made by UClothingAssetFactory::CreateFromSkeletalMesh and bound by
// FSkeletalMeshClothingSystemUtilities::AssignClothingToSection, and its weight maps live in
// UClothingAssetCommon::LodData[].PointWeightMaps; none of it is reflected for Python (LodData is a bare
// UPROPERTY(), the factory and the utilities are plain C++). The simulated positions
// (USkeletalMeshComponent::GetCurrentClothingData_GameThread) are C++ only too. This library wraps exactly those
// calls, nothing more: the rules (which map values, which preset) stay in Python (fmbridge.clothkit).
#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "FMClothLibrary.generated.h"

class USkeletalMesh;
class USkeletalMeshComponent;
class UClothingAssetBase;
class UPhysicsAsset;

UCLASS()
class FMCLOTH_API UFMCloth : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** The section of LOD `LodIndex` with the most vertices (the garment's body), or -1. */
	UFUNCTION(BlueprintCallable, Category = "FMCloth")
	static int32 LargestSection(USkeletalMesh* Mesh, int32 LodIndex);

	/** The clothing asset bound to a section, or null. */
	UFUNCTION(BlueprintCallable, Category = "FMCloth")
	static UClothingAssetBase* SectionCloth(USkeletalMesh* Mesh, int32 LodIndex, int32 SectionIndex);

	/** Clothing data on a section (create it from the section's geometry when it has none) and bound to it, with
	 *  `PhysicsAsset` for collision. Converges: a section that already has clothing keeps it (its physics asset is
	 *  updated). Returns "" on success, else what went wrong. */
	UFUNCTION(BlueprintCallable, Category = "FMCloth")
	static FString EnsureClothOnSection(USkeletalMesh* Mesh, int32 LodIndex, int32 SectionIndex, const FString& Name,
	                                    UPhysicsAsset* PhysicsAsset);

	/** Unbind and drop the clothing on a section (the garment is skinned again). Returns "" or the error. */
	UFUNCTION(BlueprintCallable, Category = "FMCloth")
	static FString RemoveClothFromSection(USkeletalMesh* Mesh, int32 LodIndex, int32 SectionIndex);

	/** The clothing's simulation mesh at rest (its physical mesh vertices, component space, cm): the points the
	 *  weight maps are indexed by. */
	UFUNCTION(BlueprintCallable, Category = "FMCloth")
	static TArray<FVector> RestVertices(UClothingAssetBase* Cloth, int32 ClothLod);

	/** One weight map's values, per RestVertices point. Target: MaxDistance | BackstopDistance | BackstopRadius |
	 *  AnimDriveStiffness. Written as an enabled painted mask (what the Paint tool writes), then pushed to the
	 *  simulation mesh (ApplyParameterMasks). Returns "" or the error. */
	UFUNCTION(BlueprintCallable, Category = "FMCloth")
	static FString SetWeightMap(UClothingAssetBase* Cloth, int32 ClothLod, const FString& Target,
	                            const TArray<float>& Values);

	/** One weight map as the simulation sees it ([] when absent). */
	UFUNCTION(BlueprintCallable, Category = "FMCloth")
	static TArray<float> GetWeightMap(UClothingAssetBase* Cloth, int32 ClothLod, const FString& Target);

	/** The component's simulated cloth particles this frame, world space (cm), every clothing asset in turn; [] when
	 *  nothing simulates. Set bWaitForParallelClothTask on the component for this frame's values. */
	UFUNCTION(BlueprintCallable, Category = "FMCloth")
	static TArray<FVector> SimulatedPositions(USkeletalMeshComponent* Component);
};
