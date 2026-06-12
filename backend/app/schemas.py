from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    target_regions: list[str] = Field(default_factory=lambda: ["Southeast Asia"])
    product_keywords: list[str] = Field(default_factory=lambda: ["surgical robotics"])
    max_results: int = Field(default=8, ge=1, le=50)
    real_search: bool = True
    require_email: bool = True


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    max_results: int = Field(default=8, ge=1, le=20)


class WebFetchRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    email: str = Field(default="", max_length=320)


class LeadUpdateRequest(BaseModel):
    status: str | None = Field(default=None, min_length=2, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)


class OutreachRequest(BaseModel):
    lead_ids: list[int] = Field(min_length=1)


class ReplyAnalysisRequest(BaseModel):
    reply_text: str = Field(min_length=3, max_length=10000)
    lead_id: int | None = None


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str | None = Field(default=None, max_length=160)


class AgentChatResponse(BaseModel):
    message: str
    session_id: str
    events: list[dict[str, object]] = Field(default_factory=list)


class AgentConfigUpdate(BaseModel):
    provider_name: str | None = Field(default=None, min_length=2, max_length=80)
    api_key: str | None = Field(default=None, max_length=4096)
    openai_api_key: str | None = Field(default=None, max_length=4096)
    model_name: str | None = Field(default=None, min_length=2, max_length=120)
    backend_base_url: str | None = Field(default=None, min_length=8, max_length=500)


class AgentConfigResponse(BaseModel):
    provider_name: str
    has_api_key: bool
    api_key_preview: str | None = None
    has_openai_api_key: bool
    openai_api_key_preview: str | None = None
    model_name: str
    backend_base_url: str
    agent_env_path: str
    restart_required: bool = False


class EmailTestRequest(BaseModel):
    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(default="[Medbot Test]", max_length=200)
    body: str = Field(default="This is a test email from Medbot.", max_length=5000)
