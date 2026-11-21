from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.clients.openrouter import OpenRouterClient, openrouter_http
from app.config import Settings
from app.services.agent import AgentService
from app.services.tool_calling import DatabaseTools, ToolCallingAgent
from app.transport.rabbitmq import RabbitWorker


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = settings or Settings()

        async with openrouter_http(config) as client:
            model = OpenRouterClient(client, config)
            agent = ToolCallingAgent(model, DatabaseTools(config, client))
            service = AgentService(agent, config.response_cache_size)
            worker = RabbitWorker(config, service)
            app.state.worker = worker
            app.state.model = model
            app.state.provider = "ollama" if config.ollama_base_url else "openrouter"

            try:
                await worker.start()
                yield
            finally:
                await worker.close()

    application = FastAPI(title="University AI Service", lifespan=lifespan)

    @application.get("/health")
    async def health(request: Request) -> JSONResponse:
        worker = request.app.state.worker
        model = request.app.state.model
        rabbitmq_ready = worker.is_ready
        model_ready = await model.is_ready()
        ready = rabbitmq_ready and model_ready

        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ok" if ready else "unavailable",
                "rabbitmq": rabbitmq_ready,
                request.app.state.provider: model_ready,
            },
        )

    return application


app = create_app()
