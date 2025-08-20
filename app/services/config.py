import os
from dataclasses import dataclass
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


@dataclass
class AzureSettings:
	use_key_vault: bool
	key_vault_url: Optional[str]
	api_key_secret_name: Optional[str]
	endpoint_secret_name: Optional[str]
	endpoint: Optional[str]
	api_key: Optional[str]
	api_version: str
	llm_deployment: str
	embedding_deployment: str
	temperature: float


@dataclass
class MongoSettings:
	uri: str
	database: str
	materials_collection: str


@dataclass
class PostgresSettings:
	url: str


def load_azure_settings() -> AzureSettings:
	use_kv = str(os.getenv("SE_KEYVAULT", "false")).lower() == "true"
	return AzureSettings(
		use_key_vault=use_kv,
		key_vault_url=os.getenv("AZURE_KEYVAULT_URL"),
		api_key_secret_name=os.getenv("KV_SECRET_AZURE_OPENAI_API_KEY"),
		endpoint_secret_name=os.getenv("KV_SECRET_AZURE_OPENAI_ENDPOINT"),
		endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
		api_key=os.getenv("AZURE_OPENAI_API_KEY"),
		api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
		llm_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
		embedding_deployment=os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
		temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.1")),
	)


def resolve_azure_openai_credentials(settings: AzureSettings) -> tuple[str, str]:
	"""Return (endpoint, api_key). If Key Vault is enabled, resolve via KV."""
	if settings.use_key_vault:
		if not settings.key_vault_url:
			raise RuntimeError("AZURE_KEYVAULT_URL is required when SE_KEYVAULT=true")
		credential = DefaultAzureCredential()
		client = SecretClient(vault_url=settings.key_vault_url, credential=credential)
		endpoint_name = settings.endpoint_secret_name
		key_name = settings.api_key_secret_name
		if not endpoint_name or not key_name:
			raise RuntimeError("KV secret names KV_SECRET_AZURE_OPENAI_ENDPOINT and KV_SECRET_AZURE_OPENAI_API_KEY are required")
		endpoint = client.get_secret(endpoint_name).value
		api_key = client.get_secret(key_name).value
		return endpoint, api_key
	# Fallback to env
	if not settings.endpoint or not settings.api_key:
		raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set when Key Vault is disabled")
	return settings.endpoint, settings.api_key


def load_mongo_settings() -> MongoSettings:
	return MongoSettings(
		uri=os.getenv("MONGODB_URI", ""),
		database=os.getenv("MONGODB_DB", "edu_platform"),
		materials_collection=os.getenv("MONGODB_COLLECTION_MATERIALS", "materials"),
	)


def load_pg_settings() -> PostgresSettings:
	return PostgresSettings(url=os.getenv("POSTGRESQL_URL", ""))


