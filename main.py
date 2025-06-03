from fastapi import FastAPI, HTTPException, WebSocket, Request, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import pytz
from fastapi.templating import Jinja2Templates
import uvicorn
import json
import logging

# Configura logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todas as origens (ajuste para produção)
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos HTTP
    allow_headers=["*"],  # Permite todos os cabeçalhos
)

templates = Jinja2Templates(directory="templates")

# Modelo para validação do JSON recebido
class Mensagem(BaseModel):
    dataAtualizacao: Optional[str] = None
    codigo: str
    origem: str
    destino: str
    mensagem: str
    status: str
    dataCadastro: Optional[str] = None

# Armazenamento em memória
mensagens = []
connected_clients = []

# Fuso horário de Brasília (GMT-03:00)
BRASILIA_TZ = pytz.timezone("America/Sao_Paulo")

def formatar_data(data_str: Optional[str]) -> Optional[str]:
    """Converte data ISO para formato '%d-%m-%Y - %H:%M:%S'.""" 
    if not data_str:
        return None
    try:
        dt = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
        return dt.strftime("%d-%m-%Y - %H:%M:%S")
    except ValueError:
        return data_str

async def notificar_clientes():
    """Notifica todos os clientes WebSocket conectados com as duas últimas mensagens."""
    if connected_clients:
        # Envia apenas as duas últimas mensagens
        mensagens_recentes = mensagens[:] # [:2] alterada para exibir todas para debug.
        mensagem_json = json.dumps(mensagens_recentes, ensure_ascii=False)
        for client in connected_clients:
            try:
                await client.send_text(mensagem_json)
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem para cliente: {e}")
                connected_clients.remove(client)

@app.post("/mensagens", status_code=200)
async def receber_mensagens(novas_mensagens: List[Mensagem]):
    """Recebe uma lista de mensagens e as adiciona à lista global."""
    for msg in novas_mensagens:
        msg_dict = msg.dict()
        msg_dict["dataAtualizacao"] = formatar_data(msg.dataAtualizacao)
        msg_dict["dataCadastro"] = formatar_data(msg.dataCadastro)
        # Gera data_recebimento no fuso horário de Brasília
        msg_dict["data_recebimento"] = datetime.now(BRASILIA_TZ).strftime("%d-%m-%Y - %H:%M:%S")
        mensagens.append(msg_dict)
    
    # Ordena mensagens por data de recebimento (decrescente)
    mensagens.sort(key=lambda x: x["data_recebimento"], reverse=True)
    
    # Notifica os clientes conectados com as duas últimas mensagens
    await notificar_clientes()
    
    return {"status": "Mensagens recebidas com sucesso"}

@app.get("/", response_class=HTMLResponse)
async def exibir_mensagens(request: Request):
    """Exibe a página inicial com as duas últimas mensagens."""
    # Envia apenas as duas últimas mensagens para o template
    mensagens_recentes = mensagens[:]
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "mensagens": mensagens_recentes}
    )

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Gerencia conexões WebSocket para atualizações em tempo real."""
    logger.debug("Tentativa de conexão WebSocket recebida")
    await websocket.accept()
    logger.debug("Conexão WebSocket aceita")
    connected_clients.append(websocket)
    try:
        # Envia as duas últimas mensagens ao conectar
        mensagens_recentes = mensagens[:]
        await websocket.send_text(json.dumps(mensagens_recentes, ensure_ascii=False))
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Dados recebidos do cliente: {data}")
    except WebSocketDisconnect:
        logger.debug("Cliente WebSocket desconectado")
        connected_clients.remove(websocket)
    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")
        connected_clients.remove(websocket)
    finally:
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")