from typing import List
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, ValidationError
from openai import AzureOpenAI, APIError, RateLimitError
import config
import logging
import json
import asyncio
from httpx import HTTPStatusError

app = FastAPI()

# Initialize AzureOpenAI client
client = AzureOpenAI(
    max_retries=0,
    azure_endpoint=config.azure_openai_endpoint,
    api_key=config.azure_openai_key_key,
    api_version=config.azure_api_version,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def chunk_text(text, chunk_size=2):
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = False


async def generate_stream(chat_request: ChatRequest):
    try:
        response = client.chat.completions.create(
            model=config.azure_openai_deployment_name,
            messages=[message.model_dump() for message in chat_request.messages],
            temperature=0,
            stream=True
        )
        for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                  text = delta.content
                  chunks = chunk_text(text)
                  for chunk in chunks:
                      yield f"data: {json.dumps({'choices':[{'delta': {'content': chunk}}]})}\n\n".encode('utf-8')
        yield b"data: [DONE]\n\n"

    except RateLimitError as e:
        logging.error(f"OpenAI Rate Limit Error: {e}")
        error_message = f"Error code: 429 - {json.dumps({'error': {'code': '429', 'message': str(e)}})}"
        yield f"data: {json.dumps({'choices':[{'delta': {'content': error_message}}]})}\n\n".encode('utf-8')
    except APIError as e:
        logging.error(f"OpenAI API Error: {e}")
        error_message = f"Error code: 500 - {json.dumps({'error': {'code': '500', 'message': str(e)}})}"
        yield f"data: {json.dumps({'choices':[{'delta': {'content': error_message}}]})}\n\n".encode('utf-8')
    except HTTPStatusError as e:
        logging.error(f"HTTPStatusError: {e}")
        error_message = f"Error code: {e.response.status_code} - {json.dumps({'error': {'code': str(e.response.status_code), 'message': str(e)}})}"
        yield f"data: {json.dumps({'choices':[{'delta': {'content': error_message}}]})}\n\n".encode('utf-8')
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        error_message = f"Error code: 500 - {json.dumps({'error': {'code': '500', 'message': str(e)}})}"
        yield f"data: {json.dumps({'choices':[{'delta': {'content': error_message}}]})}\n\n".encode('utf-8')



@app.post("/v1/chat/completions")
async def chat_completions(request: Request, chat_request: ChatRequest):
    try:
        # 获取请求头中的 Authorization 字段
        auth_header = request.headers.get('Authorization')

        # 检查 Authorization 字段是否存在
        if not auth_header:
            return JSONResponse({"error": "缺少 Authorization 请求头"}, status_code=200)

        # 验证 API 密钥是否正确
        try:
            auth_type, api_key = auth_header.split(" ")
            if auth_type != "Bearer":
                return JSONResponse({"error": "Authorization 请求头格式不正确, 需要使用 Bearer 认证"}, status_code=200)
            if api_key != config.hardcoded_api_key:
                return JSONResponse({"error": "API 密钥无效"}, status_code=200)
        except:
            return JSONResponse({"error": "Authorization 请求头格式不正确"}, status_code=200)

        if chat_request.stream:
             return StreamingResponse(generate_stream(chat_request), media_type="text/event-stream")

        else:
            try:
                response = client.chat.completions.create(
                    model=config.azure_openai_deployment_name,
                    messages=[message.model_dump() for message in chat_request.messages],
                    temperature=0,
                    stream=False,
                )
                if response.choices:
                    content = response.choices[0].message.content
                    return JSONResponse({
                        'choices': [{
                            'message': {'content': content},
                            'finish_reason': 'stop'
                            }]
                    }, status_code=200)
                else:
                    return JSONResponse({
                         'choices': [],
                         }, status_code=200)

            except RateLimitError as e:
                logging.error(f"OpenAI Rate Limit Error: {e}")
                error_message = f"Error code: 429 - {json.dumps({'error': {'code': '429', 'message': str(e)}})}"
                return JSONResponse({
                      'choices': [{
                            'message': {'content': error_message},
                            'finish_reason': 'error'
                        }]
                    }, status_code=200)
            except APIError as e:
                logging.error(f"OpenAI API Error: {e}")
                error_message = f"Error code: 500 - {json.dumps({'error': {'code': '500', 'message': str(e)}})}"
                return JSONResponse({
                      'choices': [{
                            'message': {'content': error_message},
                            'finish_reason': 'error'
                           }]
                    }, status_code=200)
            except HTTPStatusError as e:
                logging.error(f"HTTPStatusError: {e}")
                error_message = f"Error code: {e.response.status_code} - {json.dumps({'error': {'code': str(e.response.status_code), 'message': str(e)}})}"
                return JSONResponse({
                      'choices': [{
                            'message': {'content': error_message},
                             'finish_reason': 'error'
                           }]
                    }, status_code=200)
            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}")
                error_message = f"Error code: 500 - {json.dumps({'error': {'code': '500', 'message': str(e)}})}"
                return JSONResponse({
                    'choices': [{
                       'message': {'content': error_message},
                        'finish_reason': 'error'
                       }]
                    }, status_code=200)

    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        error_message = f"Error code: 500 - {json.dumps({'error': {'code': '500', 'message': str(e)}})}"
        return JSONResponse({
                      'choices': [{
                           'message': {'content': error_message},
                            'finish_reason': 'error'
                           }]
                    }, status_code=200)
