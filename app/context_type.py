from pydantic import BaseModel, ConfigDict


# frozen=True 由 Pydantic 原生提供：不可变 + 可哈希，同时保留默认值与字段校验
class MemoryContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str = "local-user"
    org_id: str = "default-org"