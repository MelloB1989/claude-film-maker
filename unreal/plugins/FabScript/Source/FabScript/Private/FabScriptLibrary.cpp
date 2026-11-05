#include "FabScriptLibrary.h"

#include "Dom/JsonObject.h"
#include "JsonObjectConverter.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/Package.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UnrealType.h"

namespace
{
	const TCHAR* FabApiClassPath = TEXT("/Script/Fab.FabBrowserApi");

	UObject* GetFabApi()
	{
		static TStrongObjectPtr<UObject> Api;
		if (!Api.IsValid())
		{
			UClass* Class = FindObject<UClass>(nullptr, FabApiClassPath);
			if (!Class)
			{
				return nullptr;
			}
			Api.Reset(NewObject<UObject>(GetTransientPackage(), Class));
		}
		return Api.Get();
	}

	// Parameters of a UFunction in a buffer: initialised, and destroyed when it goes out of scope.
	struct FParams
	{
		UFunction* Func;
		TArray<uint8> Buffer;

		explicit FParams(UFunction* InFunc) : Func(InFunc)
		{
			Buffer.SetNumZeroed(FMath::Max<int32>(Func->ParmsSize, 1));
			for (TFieldIterator<FProperty> It(Func); It && It->HasAnyPropertyFlags(CPF_Parm); ++It)
			{
				It->InitializeValue_InContainer(Buffer.GetData());
			}
		}

		~FParams()
		{
			for (TFieldIterator<FProperty> It(Func); It && It->HasAnyPropertyFlags(CPF_Parm); ++It)
			{
				It->DestroyValue_InContainer(Buffer.GetData());
			}
		}
	};

	FString CallWithMetadata(FName FuncName, const FString& DownloadUrl, const FString& MetadataJson)
	{
		UObject* Api = GetFabApi();
		if (!Api)
		{
			return TEXT("the Fab plugin is not loaded (no /Script/Fab.FabBrowserApi)");
		}
		UFunction* Func = Api->FindFunction(FuncName);
		if (!Func)
		{
			return FString::Printf(TEXT("UFabBrowserApi has no %s in this Fab version"), *FuncName.ToString());
		}
		FStrProperty* UrlProp = FindFProperty<FStrProperty>(Func, TEXT("DownloadUrl"));
		FStructProperty* MetaProp = FindFProperty<FStructProperty>(Func, TEXT("AssetMetadata"));
		if (!UrlProp || !MetaProp)
		{
			return FString::Printf(TEXT("%s's parameters changed in this Fab version (want DownloadUrl, AssetMetadata)"),
				*FuncName.ToString());
		}
		TSharedPtr<FJsonObject> Json;
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(MetadataJson);
		if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
		{
			return TEXT("metadata is not a JSON object");
		}
		FParams Params(Func);
		UrlProp->SetPropertyValue_InContainer(Params.Buffer.GetData(), DownloadUrl);
		void* MetaPtr = MetaProp->ContainerPtrToValuePtr<void>(Params.Buffer.GetData());
		FText Why;
		if (!FJsonObjectConverter::JsonObjectToUStruct(Json.ToSharedRef(), MetaProp->Struct, MetaPtr, 0, 0, false, &Why))
		{
			return FString::Printf(TEXT("metadata does not fit FFabAssetMetadata: %s"), *Why.ToString());
		}
		Api->ProcessEvent(Func, Params.Buffer.GetData());
		return FString();
	}

	FString CallString(FName FuncName)
	{
		UObject* Api = GetFabApi();
		UFunction* Func = Api ? Api->FindFunction(FuncName) : nullptr;
		if (!Func)
		{
			return FString();
		}
		FParams Params(Func);
		Api->ProcessEvent(Func, Params.Buffer.GetData());
		FStrProperty* Ret = CastField<FStrProperty>(Func->GetReturnProperty());
		return Ret ? Ret->GetPropertyValue_InContainer(Params.Buffer.GetData()) : FString();
	}
}

FString UFabScript::AddToProject(const FString& DownloadUrl, const FString& MetadataJson)
{
	return CallWithMetadata(TEXT("AddToProject"), DownloadUrl, MetadataJson);
}

FString UFabScript::InstallToProject(const FString& DownloadUrl, const FString& MetadataJson)
{
	return CallWithMetadata(TEXT("InstallToProject"), DownloadUrl, MetadataJson);
}

bool UFabScript::IsSignedIn()
{
	return !CallString(TEXT("GetAuthToken")).IsEmpty();
}

FString UFabScript::OpenFabTab()
{
	UObject* Api = GetFabApi();
	UFunction* Func = Api ? Api->FindFunction(TEXT("OpenInNewTab")) : nullptr;
	if (!Func)
	{
		return TEXT("the Fab plugin is not loaded, or has no OpenInNewTab");
	}
	FParams Params(Func);
	if (FStrProperty* Url = FindFProperty<FStrProperty>(Func, TEXT("Url")))
	{
		Url->SetPropertyValue_InContainer(Params.Buffer.GetData(), FString());
	}
	Api->ProcessEvent(Func, Params.Buffer.GetData());
	return FString();
}

bool UFabScript::IsFabLoaded()
{
	return GetFabApi() != nullptr;
}
