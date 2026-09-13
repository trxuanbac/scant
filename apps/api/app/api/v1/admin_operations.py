from app.models.admin_configuration import AdminConfiguration
from datetime import datetime
from typing import Optional, Literal
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field, ConfigDict
from app.core.admin_access import require_admin, require_super_admin
from app.core.database import get_db
from app.models.entities import User, Template
from app.services.admin import operations_service as ops
from app.services.admin.audit_service import record_audit
from app.services.admin.query_service import period

router=APIRouter(dependencies=[Depends(require_admin)])

class Action(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    reason:str=Field(min_length=3,max_length=1000)


def filters(search:str=Query('',max_length=200),page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),sort:Optional[str]=None,order:Literal['asc','desc']='desc',status:Optional[str]=None,user_id:Optional[str]=None,project_id:Optional[str]=None,start:Optional[str]=Query(None,alias='from'),end:Optional[str]=Query(None,alias='to')):
    a,b=period(start,end) if start or end else (None,None)
    return {'search':search,'page':page,'page_size':page_size,'sort':sort,'order':order,'status':status,'user_id':user_id,'project_id':project_id,'from_':a,'to':b}

@router.get('/system/health')
async def health(db:AsyncSession=Depends(get_db)):
    return await ops.system_health(db)

@router.get('/integrations')
async def integrations(f:dict=Depends(filters),db:AsyncSession=Depends(get_db)):
    return await ops.integrations(db,f)

@router.get('/providers')
async def providers(f:dict=Depends(filters),user:User=Depends(require_super_admin),db:AsyncSession=Depends(get_db)):
    return await ops.integrations(db,f)

@router.get('/ai-config')
async def ai_config(user:User=Depends(require_super_admin),db:AsyncSession=Depends(get_db)):
    from app.services.admin.configuration_service import read_configuration
    return {**ops.ai_configuration(),'runtime':await read_configuration(db,'ai'),'writable':True}

@router.get('/settings')
async def settings(user:User=Depends(require_super_admin),db:AsyncSession=Depends(get_db)):
    from app.services.admin.configuration_service import read_configuration
    return {**ops.system_settings(),'runtime':await read_configuration(db,'system'),'writable':True}

# Explicit routes, rather than a catch-all that could mask future protected modules.
for resource in ['projects','documents','storage','templates']:
    def create_list(kind):
        async def endpoint(f:dict=Depends(filters),db:AsyncSession=Depends(get_db)):
            return await ops.list_resources(db,kind,f)
        return endpoint
    router.add_api_route('/'+resource,create_list(resource),methods=['GET'])

@router.post('/templates/{template_id}/{action}')
async def template_action(template_id:str,action:Literal['publish','unpublish'],body:Action,request:Request,user:User=Depends(require_admin),db:AsyncSession=Depends(get_db)):
    row=(await db.execute(select(Template).where(Template.id==template_id).with_for_update())).scalar_one_or_none()
    if not row:raise HTTPException(404,'Không tìm thấy mẫu.')
    if action=='publish' and (not user.is_superuser or not row.is_system):raise HTTPException(403,'Chỉ Super Admin được phát hành mẫu hệ thống; không công khai mẫu riêng của người dùng.')
    if row.is_system and not user.is_superuser:raise HTTPException(403,'Mẫu hệ thống yêu cầu Super Admin.')
    if action=='publish':
        validation=await ops.validate_template(db,row)
        if not validation['valid']:raise HTTPException(422,validation)
    before={'is_public':row.is_public,'visibility':row.visibility}
    row.is_public=action=='publish';row.visibility='public' if row.is_public else 'my'
    await record_audit(db,user,'TEMPLATE_PUBLISH' if row.is_public else 'TEMPLATE_UNPUBLISH','template',row.id,before,{'is_public':row.is_public,'visibility':row.visibility},body.reason,request)
    return {'id':row.id,'is_public':row.is_public,'visibility':row.visibility}

class ConfigurationChange(Action):
    revision:int=Field(ge=0)
    values:dict

@router.patch('/settings')
async def update_settings(body:ConfigurationChange,request:Request,user:User=Depends(require_super_admin),db:AsyncSession=Depends(get_db)):
    from app.services.admin.configuration_service import write_configuration
    return await write_configuration(db,'system',body.values,body.revision,user,body.reason,request)

@router.patch('/ai-config')
async def update_ai_config(body:ConfigurationChange,request:Request,user:User=Depends(require_super_admin),db:AsyncSession=Depends(get_db)):
    from app.services.admin.configuration_service import write_configuration
    return await write_configuration(db,'ai',body.values,body.revision,user,body.reason,request)

@router.get('/projects/{project_id}')
async def project_detail(project_id:str,db:AsyncSession=Depends(get_db)):
    return await ops.project_detail(db,project_id)

@router.get('/templates/{template_id}/validation')
async def template_validation(template_id:str,db:AsyncSession=Depends(get_db)):
    row=await db.get(Template,template_id)
    if not row:raise HTTPException(404,'Không tìm thấy mẫu.')
    return await ops.validate_template(db,row)
