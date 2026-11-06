// Every engine call below was checked on the UE 5.8.4 source (docs/unreal/cloth.md API_NOTES).
#include "FMClothLibrary.h"

#include "ClothingAsset.h"                         // UClothingAssetCommon (LodData, PhysicsAsset, ApplyParameterMasks)
#include "ClothingAssetBase.h"
#include "ClothingAssetFactory.h"                  // UClothingAssetFactory::CreateFromSkeletalMesh (ClothingSystemEditor)
#include "ClothingSystemRuntimeTypes.h"            // FClothSimulData
#include "ClothLODData.h"
#include "ClothPhysicalMeshData.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"                   // FSkeletalMeshClothBuildParams, AddClothingAsset
#include "PhysicsEngine/PhysicsAsset.h"
#include "PointWeightMap.h"
#include "Rendering/SkeletalMeshLODModel.h"
#include "Rendering/SkeletalMeshModel.h"
#include "SkeletalMeshClothingSystemUtilities.h"  // AssignClothingToSection (SkeletalMeshEditor)
#include "SkeletalMeshTypes.h"                     // FScopedSkeletalMeshPostEditChange

namespace FMClothPrivate
{
	bool Target(const FString& Name, EWeightMapTargetCommon& Out)
	{
		if (Name == TEXT("MaxDistance")) { Out = EWeightMapTargetCommon::MaxDistance; return true; }
		if (Name == TEXT("BackstopDistance")) { Out = EWeightMapTargetCommon::BackstopDistance; return true; }
		if (Name == TEXT("BackstopRadius")) { Out = EWeightMapTargetCommon::BackstopRadius; return true; }
		if (Name == TEXT("AnimDriveStiffness")) { Out = EWeightMapTargetCommon::AnimDriveStiffness; return true; }
		return false;
	}

	FSkelMeshSection* Section(USkeletalMesh* Mesh, int32 LodIndex, int32 SectionIndex)
	{
		FSkeletalMeshModel* Model = Mesh ? Mesh->GetImportedModel() : nullptr;
		if (!Model || !Model->LODModels.IsValidIndex(LodIndex) || !Model->LODModels[LodIndex].Sections.IsValidIndex(SectionIndex))
		{
			return nullptr;
		}
		return &Model->LODModels[LodIndex].Sections[SectionIndex];
	}
}

int32 UFMCloth::LargestSection(USkeletalMesh* Mesh, int32 LodIndex)
{
	FSkeletalMeshModel* Model = Mesh ? Mesh->GetImportedModel() : nullptr;
	if (!Model || !Model->LODModels.IsValidIndex(LodIndex))
	{
		return -1;
	}
	int32 Best = -1, BestNum = -1;
	const TArray<FSkelMeshSection>& Sections = Model->LODModels[LodIndex].Sections;
	for (int32 i = 0; i < Sections.Num(); ++i)
	{
		if (Sections[i].NumVertices > BestNum)
		{
			Best = i;
			BestNum = Sections[i].NumVertices;
		}
	}
	return Best;
}

UClothingAssetBase* UFMCloth::SectionCloth(USkeletalMesh* Mesh, int32 LodIndex, int32 SectionIndex)
{
	FSkelMeshSection* Sec = FMClothPrivate::Section(Mesh, LodIndex, SectionIndex);
	if (!Sec || !Sec->HasClothingData())
	{
		return nullptr;
	}
	return Mesh->GetClothingAsset(Sec->ClothingData.AssetGuid);
}

FString UFMCloth::EnsureClothOnSection(USkeletalMesh* Mesh, int32 LodIndex, int32 SectionIndex, const FString& Name,
                                       UPhysicsAsset* PhysicsAsset)
{
	if (!FMClothPrivate::Section(Mesh, LodIndex, SectionIndex))
	{
		return FString::Printf(TEXT("no LOD %d section %d on %s"), LodIndex, SectionIndex, Mesh ? *Mesh->GetPathName() : TEXT("(null)"));
	}
	if (UClothingAssetCommon* Existing = Cast<UClothingAssetCommon>(SectionCloth(Mesh, LodIndex, SectionIndex)))
	{
		if (PhysicsAsset && Existing->PhysicsAsset != PhysicsAsset)
		{
			Existing->Modify();
			Existing->PhysicsAsset = PhysicsAsset;
			Existing->InvalidateAllCachedData();
		}
		return FString();
	}
	Mesh->Modify();
	UClothingAssetBase* NewAsset = nullptr;
	{
		FScopedSkeletalMeshPostEditChange ScopedPostEditChange(Mesh);
		FSkeletalMeshClothBuildParams Params;
		Params.AssetName = Name;
		Params.LodIndex = LodIndex;
		Params.SourceSection = SectionIndex;
		Params.bRemoveFromMesh = false;
		Params.PhysicsAsset = PhysicsAsset;
		UClothingAssetFactory* Factory = NewObject<UClothingAssetFactory>(GetTransientPackage());
		NewAsset = Factory->CreateFromSkeletalMesh(Mesh, Params);
		if (!NewAsset)
		{
			return TEXT("UClothingAssetFactory::CreateFromSkeletalMesh made nothing (see LogClothingAsset)");
		}
		Mesh->AddClothingAsset(NewAsset);
	}
	FString Error;
	if (!FSkeletalMeshClothingSystemUtilities::AssignClothingToSection(Mesh, NewAsset, LodIndex, SectionIndex, 0, &Error))
	{
		return Error.IsEmpty() ? TEXT("AssignClothingToSection failed") : Error;
	}
	return FString();
}

FString UFMCloth::RemoveClothFromSection(USkeletalMesh* Mesh, int32 LodIndex, int32 SectionIndex)
{
	if (!SectionCloth(Mesh, LodIndex, SectionIndex))
	{
		return FString();
	}
	FString Error;
	if (!FSkeletalMeshClothingSystemUtilities::RemoveClothingFromSection(Mesh, LodIndex, SectionIndex, &Error))
	{
		return Error.IsEmpty() ? TEXT("RemoveClothingFromSection failed") : Error;
	}
	return FString();
}

TArray<FVector> UFMCloth::RestVertices(UClothingAssetBase* Cloth, int32 ClothLod)
{
	TArray<FVector> Out;
	UClothingAssetCommon* Common = Cast<UClothingAssetCommon>(Cloth);
	if (!Common || !Common->LodData.IsValidIndex(ClothLod))
	{
		return Out;
	}
	const TArray<FVector3f>& Vertices = Common->LodData[ClothLod].PhysicalMeshData.Vertices;
	Out.Reserve(Vertices.Num());
	for (const FVector3f& V : Vertices)
	{
		Out.Add(FVector(V));
	}
	return Out;
}

FString UFMCloth::SetWeightMap(UClothingAssetBase* Cloth, int32 ClothLod, const FString& Target, const TArray<float>& Values)
{
	UClothingAssetCommon* Common = Cast<UClothingAssetCommon>(Cloth);
	EWeightMapTargetCommon T;
	if (!FMClothPrivate::Target(Target, T))
	{
		return FString::Printf(TEXT("unknown weight map target %s (MaxDistance, BackstopDistance, BackstopRadius, AnimDriveStiffness)"), *Target);
	}
	if (!Common || !Common->LodData.IsValidIndex(ClothLod))
	{
		return TEXT("not a skeletal-mesh clothing asset (UClothingAssetCommon) or no such cloth LOD");
	}
	FClothLODDataCommon& Lod = Common->LodData[ClothLod];
	const int32 Num = Lod.PhysicalMeshData.Vertices.Num();
	if (Values.Num() != Num)
	{
		return FString::Printf(TEXT("%d values for %d simulation vertices"), Values.Num(), Num);
	}
	Common->Modify();
	FPointWeightMap* Mask = nullptr;
	for (FPointWeightMap& M : Lod.PointWeightMaps)
	{
		if (M.CurrentTarget == (uint8)T)
		{
			Mask = &M;
			break;
		}
	}
	if (!Mask)
	{
		Mask = &Lod.PointWeightMaps.AddDefaulted_GetRef();
		Mask->Name = FName(*Target);
	}
	Mask->Values = Values;
	Mask->CurrentTarget = (uint8)T;
	Mask->bEnabled = true;
	Common->ApplyParameterMasks(/*bUpdateFixedVertData=*/true, /*bInvalidateDerivedDataCache=*/true);
	return FString();
}

TArray<float> UFMCloth::GetWeightMap(UClothingAssetBase* Cloth, int32 ClothLod, const FString& Target)
{
	UClothingAssetCommon* Common = Cast<UClothingAssetCommon>(Cloth);
	EWeightMapTargetCommon T;
	if (!Common || !FMClothPrivate::Target(Target, T) || !Common->LodData.IsValidIndex(ClothLod))
	{
		return TArray<float>();
	}
	const FPointWeightMap* Map = Common->LodData[ClothLod].PhysicalMeshData.FindWeightMap(T);
	return Map ? Map->Values : TArray<float>();
}

TArray<FVector> UFMCloth::SimulatedPositions(USkeletalMeshComponent* Component)
{
	TArray<FVector> Out;
	if (!Component)
	{
		return Out;
	}
	const FTransform ComponentToWorld = Component->GetComponentTransform();
	const TMap<int32, FClothSimulData>& Data = Component->GetCurrentClothingData_GameThread();
	TArray<int32> Keys;
	Data.GetKeys(Keys);
	Keys.Sort();
	for (int32 Key : Keys)
	{
		const FClothSimulData& D = Data[Key];
		// what the GPU skin cache does: cloth to local is ComponentRelativeTransform (SkeletalRenderGPUSkin.cpp)
		const FTransform ToWorld = D.ComponentRelativeTransform * ComponentToWorld;
		for (const FVector3f& P : D.Positions)
		{
			Out.Add(ToWorld.TransformPosition(FVector(P)));
		}
	}
	return Out;
}
