from app.integrations.ai import (
    AIProvider,
    AzureOpenAIProvider,
    MockProvider,
    OpenAIProvider,
    get_ai_provider,
)

AIClient = AIProvider
MockAIClient = MockProvider
OpenAICompatibleClient = OpenAIProvider
get_ai_client = get_ai_provider
