
from  deepagents import  create_deep_agent
from deepagents.backends import CompositeBackend, StoreBackend, FilesystemBackend, StateBackend
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from config_settings import settings
from context_type import  MemoryContext

from contextlib import  ExitStack

default_backend=StateBackend()

stack=ExitStack()
checkpointer=stack.enter_context(PostgresSaver.from_conn_string(settings.POSTGRES_URI))
store=stack.enter_context(PostgresStore.from_conn_string(settings.POSTGRES_URI))

checkpointer.setup()
store.setup()

model = ChatOpenAI(
    model=settings.MODEL,
    api_key=settings.API_KEY,
    base_url=settings.BASE_URL,
    use_responses_api=False,
)

agent = create_deep_agent(
        model=model,
        context_schema=MemoryContext,
        memory=["/memories/AGENTS.md","/memories/habits.md"],
        skills=["/skills/"],
        checkpointer=checkpointer,
        backend=CompositeBackend(
            default=default_backend,
            routes={
                #AGENTS.md 是全级配置：单独路由到全局命名空间
                #habits.md 仍按用户命名空间隔离
                "/memories/AGENTS.md":StoreBackend(
                    namespace= lambda  _rt:settings.AGENTS_NAMESPACE,
                    store=store,
                ),
                "/memories/":StoreBackend(
                    namespace=lambda  _rt:settings.AGENTS_NAMESPACE,
                    store=store,
                ),
                "/skills/":FilesystemBackend(
                    root_dir=str(settings.LOCAL_SKILLS_DIR),
                    virtual_mode=True,
                )
            },
        ),
    )

stack.close()