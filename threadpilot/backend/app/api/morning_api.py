import asyncio
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from openai import OpenAIError
from ..services.morning_service import MorningService, MorningConflict
from ..services.scheduling_service import current_snapshot, fingerprint
from ..workflow_api import business_now

router=APIRouter(tags=['Morning briefing'])


async def generate_morning(app, scheduled=False):
    if not hasattr(app.state,'morning_lock'): app.state.morning_lock=asyncio.Lock()
    async with app.state.morning_lock:
        return await MorningService(app.state.database).generate(business_now().date().isoformat(),
                    app.state.client, app.state.settings, now=business_now(), scheduled=scheduled)


@router.get('/briefing', include_in_schema=False)
@router.get('/demo/briefing_demo.html', include_in_schema=False)
def briefing_page():
    return RedirectResponse('/briefing.html', status_code=307)


@router.get('/api/morning')
def morning_list(request: Request, response: Response):
    response.headers['Cache-Control']='no-store'
    today=business_now().date().isoformat()
    return {'business_date':today,'reports':MorningService(request.app.state.database).list(),
            'current_fingerprint':fingerprint(current_snapshot(request.app.state.database,today)),
            'model_configured':request.app.state.client is not None}


@router.get('/api/morning/reports/{report_id}')
def morning_report(report_id: str, request: Request, response: Response):
    response.headers['Cache-Control']='no-store'
    try: return MorningService(request.app.state.database).get(report_id)
    except KeyError: raise HTTPException(404,'Report not found.')


@router.post('/api/morning/generate')
async def morning_generate(request: Request, response: Response):
    response.headers['Cache-Control']='no-store'
    try: return await generate_morning(request.app)
    except MorningConflict as error: raise HTTPException(409,str(error))
    except ValueError as error: raise HTTPException(422,str(error))
    except OpenAIError: raise HTTPException(502,'Model service unavailable. No simulated report was generated; retry later.')
