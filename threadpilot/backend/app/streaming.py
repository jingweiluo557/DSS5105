"""SSE transport for structured Responses output; expose only answer text deltas."""
import asyncio
import json
import jiter
from openai import APIError, APITimeoutError, APIConnectionError, APIStatusError, RateLimitError


def event(name, data):
    return f'event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'


async def answer_events(client, kwargs, known, request_id):
    yield event('start', {'request_id': request_id, 'model': kwargs['model']})
    raw = ''
    emitted = ''
    try:
        async with asyncio.timeout(180):
            async with client.responses.stream(**kwargs) as stream:
                async for item in stream:
                    if item.type == 'error':
                        quota = getattr(item, 'code', None) == 'insufficient_quota'
                        yield event('error', {'code': 'MODEL_QUOTA_EXCEEDED' if quota else 'MODEL_API_ERROR',
                                             'message': 'OpenAI API credits are exhausted. Check API billing and add credits before retrying.' if quota else 'OpenAI reported an error during generation. Check server configuration.',
                                             'request_id': request_id})
                        return
                    if item.type == 'response.output_text.delta':
                        raw += item.delta
                        try:
                            parsed = jiter.from_json(raw.encode('utf-8'), partial_mode='trailing-strings')
                            text = parsed.get('answer', '') if isinstance(parsed, dict) else ''
                        except ValueError:
                            continue
                        if isinstance(text, str) and text.startswith(emitted) and len(text) > len(emitted):
                            yield event('delta', {'text': text[len(emitted):]})
                            emitted = text
                result = await stream.get_final_response()
                answer = result.output_parsed
                if result.status != 'completed' or answer is None or not answer.answer.strip():
                    yield event('error', {'code': 'INVALID_MODEL_RESPONSE', 'message': 'The answer was not completed. Please retry.', 'request_id': request_id})
                    return
                if any(x not in known for x in answer.order_ids) or (answer.selected_order_id and answer.selected_order_id not in known):
                    yield event('error', {'code': 'INVALID_MODEL_REFERENCE', 'message': 'The model returned an unknown order. Please retry.', 'request_id': request_id})
                    return
                payload = answer.model_dump()
                payload.update(order_ids=list(dict.fromkeys(answer.order_ids))[:10], model=result.model, request_id=request_id, business_date='2026-04-01', usage=None)
                if result.usage:
                    payload['usage'] = {k: getattr(result.usage, k) for k in ('input_tokens', 'output_tokens', 'total_tokens')}
                yield event('done', payload)
    except (APITimeoutError, TimeoutError):
        yield event('error', {'code': 'MODEL_TIMEOUT', 'message': 'Generation timed out. Please retry.', 'request_id': request_id})
    except RateLimitError:
        yield event('error', {'code': 'MODEL_RATE_LIMITED', 'message': 'OpenAI quota or rate limit reached. Try later.', 'request_id': request_id})
    except APIConnectionError:
        yield event('error', {'code': 'MODEL_CONNECTION_ERROR', 'message': 'Connection to OpenAI was interrupted.', 'request_id': request_id})
    except APIStatusError:
        yield event('error', {'code': 'MODEL_API_ERROR', 'message': 'OpenAI rejected the request. Check server configuration.', 'request_id': request_id})
    except APIError as error:
        # Providers can report quota errors inside an already-open HTTP 200 stream.
        quota = getattr(error, 'code', None) == 'insufficient_quota' or 'no credits remaining' in str(error).lower()
        yield event('error', {'code': 'MODEL_QUOTA_EXCEEDED' if quota else 'MODEL_API_ERROR', 'message': 'OpenAI API credits are exhausted. Check API billing and add credits before retrying.' if quota else 'OpenAI reported an error during generation. Check server configuration.', 'request_id': request_id})
    except Exception:
        yield event('error', {'code': 'MODEL_RESPONSE_ERROR', 'message': 'Generation could not be completed. Please retry.', 'request_id': request_id})
