"""Bounded metadata queries and explicit UTC time windows for the console."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, func, or_, desc, asc
from app.models.entities import User, Project, Document, UploadedFile, Report, Job, AIUsageEvent, UserQuota, AuditLog, AuthAccount
from app.core.admin_access import admin_role
from app.services.admin.audit_service import safe_value


def utc(value):
    if value is None: return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


def period(start=None, end=None):
    def parse(value):
        try:
            parsed=value if isinstance(value,datetime) else datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
        except (ValueError,AttributeError):
            raise HTTPException(422,'Ngày không hợp lệ. Dùng ISO 8601.')
    end=parse(end) if end else datetime.now(timezone.utc)
    start=parse(start) if start else end-timedelta(days=30)
    if start>=end or end-start>timedelta(days=366):
        raise HTTPException(422,'Khoảng ngày phải tăng dần và không quá 366 ngày; ngày kết thúc không được tính vào kỳ.')
    return start,end


def span(column,start,end): return (column>=start,column<end)


def page_result(items,total,page,page_size):
    return {'items':items,'total':total,'page':page,'page_size':page_size}


def user_dict(user):
    return {k:getattr(user,k) for k in ['id','name','email','plan','is_active','is_superuser']} | {'role':admin_role(user),'created_at':utc(user.created_at)}


def job_dict(job):
    # Payload/result/error bodies can contain private documents or provider credentials.
    return {k:getattr(job,k) for k in ['id','project_id','job_type','status','progress_percent']} | {
        'created_at':utc(job.created_at),'updated_at':utc(job.updated_at),
        'error_message': 'Tác vụ thất bại; nội dung lỗi chi tiết bị giới hạn để bảo vệ dữ liệu.' if job.error_message else None,
        'model':None,'tokens':None,'cost_usd':None,'duration_seconds':None,
    }


async def list_users(db,search=None,page=1,page_size=25,role=None,plan=None,status=None,start=None,end=None,sort='created_at',order='desc'):
    usage=select(AIUsageEvent.user_id.label('uid'),func.sum(AIUsageEvent.total_tokens).label('tokens'),func.sum(AIUsageEvent.estimated_cost_usd).label('cost'),func.max(AIUsageEvent.created_at).label('last_active')).group_by(AIUsageEvent.user_id).subquery()
    projects=select(Project.user_id.label('uid'),func.count().label('projects')).group_by(Project.user_id).subquery()
    q=select(User,usage.c.tokens,usage.c.cost,usage.c.last_active,projects.c.projects).outerjoin(usage,usage.c.uid==User.id).outerjoin(projects,projects.c.uid==User.id)
    filters=[]
    if search: filters.append(or_(User.email.ilike(f'%{search}%'),User.name.ilike(f'%{search}%')))
    if role=='super_admin':filters.append(User.is_superuser.is_(True))
    elif role=='admin':filters.extend([User.role=='admin',User.is_superuser.is_(False)])
    elif role=='user':filters.extend([User.role!='admin',User.is_superuser.is_(False)])
    if plan: filters.append(User.plan==plan)
    if status in ['active','locked','suspended']:filters.append(User.is_active.is_(status=='active'))
    if start or end:
        a,b=period(start,end);filters.extend(span(User.created_at,a,b))
    total=await db.scalar(select(func.count()).select_from(User).where(*filters))
    sort_col={'created_at':User.created_at,'name':User.name,'email':User.email,'plan':User.plan,'last_active':usage.c.last_active,'total_tokens':usage.c.tokens}.get(sort,User.created_at)
    rows=(await db.execute(q.where(*filters).order_by((asc if order=='asc' else desc)(sort_col),User.id).offset((page-1)*page_size).limit(page_size))).all()
    return page_result([user_dict(u)|{'total_tokens':tokens or 0,'cost_usd':round(cost or 0,6),'last_active':utc(last),'projects_count':count or 0} for u,tokens,cost,last,count in rows],total,page,page_size)


def usage_filters(start,end,provider=None,model=None,feature=None,user_id=None):
    f=list(span(AIUsageEvent.created_at,start,end))
    for key,value in [(AIUsageEvent.provider,provider),(AIUsageEvent.model,model),(AIUsageEvent.task_type,feature),(AIUsageEvent.user_id,user_id)]:
        if value:f.append(key==value)
    return f


async def usage_summary(db,filters):
    E=AIUsageEvent
    row=(await db.execute(select(func.count(),func.sum(E.input_tokens),func.sum(E.output_tokens),func.sum(E.total_tokens),func.sum(E.estimated_cost_usd),func.avg(E.latency_ms),func.count().filter(E.status=='success')).where(*filters))).one()
    n,i,o,t,c,l,success=row
    return {'requests':n,'input_tokens':i or 0,'output_tokens':o or 0,'total_tokens':t or 0,'estimated_cost_usd':round(c or 0,6),'average_latency_ms':round(l,2) if l is not None else None,'success_rate':round(success/n*100,2) if n else None,'error_rate':round((n-success)/n*100,2) if n else None}


async def usage(db,start=None,end=None,provider=None,model=None,feature=None,user_id=None,page=1,page_size=25):
    a,b=period(start,end);E=AIUsageEvent;f=usage_filters(a,b,provider,model,feature,user_id)
    summary=await usage_summary(db,f)
    trend=(await db.execute(select(func.date(E.created_at).label('date'),func.sum(E.input_tokens).label('input_tokens'),func.sum(E.output_tokens).label('output_tokens'),func.sum(E.total_tokens).label('total_tokens'),func.sum(E.estimated_cost_usd).label('cost_usd'),func.count().label('requests')).where(*f).group_by(func.date(E.created_at)).order_by(func.date(E.created_at)))).mappings().all()
    result={'period':{'from':utc(a),'to':utc(b)},'summary':summary,'trend':[dict(r) for r in trend]}
    for key,col in [('by_model',E.model),('by_feature',E.task_type),('by_provider',E.provider),('by_user',E.user_id)]:
        rows=(await db.execute(select(col.label('name'),func.count().label('requests'),func.sum(E.total_tokens).label('tokens'),func.sum(E.estimated_cost_usd).label('cost_usd'),func.avg(E.latency_ms).label('latency_ms')).where(*f).group_by(col).order_by(func.sum(E.estimated_cost_usd).desc()).limit(25))).mappings().all()
        result[key]=[dict(r) for r in rows]
    rows=(await db.execute(select(E).where(*f).order_by(E.created_at.desc(),E.id).offset((page-1)*page_size).limit(page_size))).scalars().all()
    fields=['id','user_id','project_id','provider','model','task_type','input_tokens','output_tokens','total_tokens','estimated_cost_usd','latency_ms','status']
    result.update(page_result([{k:getattr(e,k) for k in fields}|{'created_at':utc(e.created_at)} for e in rows],summary['requests'],page,page_size))
    return result


async def overview(db,start=None,end=None):
    a,b=period(start,end);prev=a-(b-a)
    async def counts(left,right):
        def count(model,*filters):return select(func.count()).select_from(model).where(*filters).scalar_subquery()
        expressions={
            'total_users':count(User,User.created_at<right),
            'new_users':count(User,*span(User.created_at,left,right)),
            'active_users':select(func.count(func.distinct(AIUsageEvent.user_id))).where(*span(AIUsageEvent.created_at,left,right)).scalar_subquery(),
            'jobs':count(Job,*span(Job.created_at,left,right)),
            'successful_jobs':count(Job,*span(Job.created_at,left,right),Job.status=='completed'),
            'failed_jobs':count(Job,*span(Job.created_at,left,right),Job.status=='failed'),
            'reports':count(Report,*span(Report.created_at,left,right)),
            'documents':count(Document,*span(Document.created_at,left,right)),
        }
        row=(await db.execute(select(*[v.label(k) for k,v in expressions.items()]))).mappings().one()
        return dict(row)
    cur=await counts(a,b);old=await counts(prev,a)
    usage_data=await usage(db,a,b,page_size=10)
    prev_usage=await usage_summary(db,usage_filters(prev,a))
    cur.update(tokens=usage_data['summary']['total_tokens'],cost=usage_data['summary']['estimated_cost_usd'])
    old.update(tokens=prev_usage['total_tokens'],cost=prev_usage['estimated_cost_usd'])
    definitions={
        'total_users':('Tổng người dùng','count','Tài khoản tạo trước thời điểm kết thúc kỳ.','/admin/users'),
        'new_users':('Người dùng mới','count','Tài khoản đăng ký trong kỳ.','/admin/users'),
        'active_users':('Người dùng hoạt động','count','Số tài khoản khác nhau có AI usage event trong kỳ; không đại diện mọi lần đăng nhập.','/admin/usage'),
        'jobs':('Tác vụ AI','count','Job được ghi trong DB, tạo trong kỳ.','/admin/ai-jobs'),
        'successful_jobs':('Tác vụ thành công','count','Job tạo trong kỳ, trạng thái hiện tại completed.','/admin/ai-jobs?status=completed'),
        'failed_jobs':('Tác vụ thất bại','count','Job tạo trong kỳ, trạng thái hiện tại failed.','/admin/ai-jobs?status=failed'),
        'reports':('Báo cáo','count','Bản ghi báo cáo tạo trong kỳ; không khẳng định đã xuất thành công.','/admin/documents'),
        'documents':('Tài liệu xử lý','count','Bản ghi Document tạo trong kỳ.','/admin/documents'),
        'tokens':('Token đã dùng','tokens','Tổng token trong AI usage event của kỳ.','/admin/usage'),
        'cost':('Chi phí AI ước tính','USD','Tổng estimated_cost_usd ghi nhận tại thời điểm gọi AI trong kỳ.','/admin/usage'),
    }
    metrics=[{'key':k,'label':label,'value':cur[k],'previous':old[k],'change_pct':round((cur[k]-old[k])/old[k]*100,2) if old[k] else None,'unit':unit,'definition':definition,'href':href} for k,(label,unit,definition,href) in definitions.items()]
    storage=await db.scalar(select(func.sum(UploadedFile.file_size))) or 0
    metrics.extend([
        {'key':'storage','label':'Dung lượng file đăng ký','value':storage,'unit':'bytes','previous':None,'change_pct':None,'definition':'Tổng file_size trong UploadedFile hiện tại, không phải đo dung lượng vật lý.','href':'/admin/documents'},
    ])
    user_trend=(await db.execute(select(func.date(User.created_at).label('date'),func.count().label('value')).where(*span(User.created_at,a,b)).group_by(func.date(User.created_at)).order_by(func.date(User.created_at)))).mappings().all()
    jobs=(await db.execute(select(Job.status.label('name'),func.count().label('value')).where(*span(Job.created_at,a,b)).group_by(Job.status))).mappings().all()
    return {'period':{'from':utc(a),'to':utc(b),'previous_from':utc(prev),'previous_to':utc(a),'timezone':'UTC','end_exclusive':True},'metrics':metrics,'trends':{'users':[dict(r) for r in user_trend],'tokens':usage_data['trend'],'cost':[{'date':r['date'],'value':r['cost_usd']} for r in usage_data['trend']]},'breakdowns':{'jobs':[dict(r) for r in jobs],'features':usage_data['by_feature'],'models':usage_data['by_model']},'unavailable':['Lịch sử dung lượng vật lý chưa được thu thập.','Usage chỉ bao gồm các tác vụ đã ghi AIUsageEvent.']}


async def list_jobs(db,search=None,page=1,page_size=25,status=None,job_type=None,user_id=None,start=None,end=None,sort='created_at',order='desc'):
    q=select(Job,Project.name.label('project_name'),User.email.label('user_email')).outerjoin(Project,Job.project_id==Project.id).outerjoin(User,Project.user_id==User.id)
    f=[]
    if search:f.append(or_(Job.id.ilike(f'%{search}%'),Project.name.ilike(f'%{search}%'),User.email.ilike(f'%{search}%')))
    if status:f.append(Job.status==status)
    if job_type:f.append(Job.job_type==job_type)
    if user_id:f.append(Project.user_id==user_id)
    if start or end:
        a,b=period(start,end);f.extend(span(Job.created_at,a,b))
    total=await db.scalar(select(func.count()).select_from(q.where(*f).subquery()))
    col={'created_at':Job.created_at,'status':Job.status,'job_type':Job.job_type,'progress_percent':Job.progress_percent}.get(sort,Job.created_at)
    rows=(await db.execute(q.where(*f).order_by((asc if order=='asc' else desc)(col),Job.id).offset((page-1)*page_size).limit(page_size))).all()
    return page_result([job_dict(j)|{'project_name':p,'user_email':u} for j,p,u in rows],total,page,page_size)


async def list_audit(db,search=None,page=1,page_size=25,action=None,actor=None,target=None,start=None,end=None):
    q=select(AuditLog,User.name).outerjoin(User,AuditLog.user_id==User.id);f=[]
    if action:f.append(AuditLog.action==action)
    if actor:f.append(AuditLog.user_id==actor)
    if target:f.append(AuditLog.resource_id==target)
    if search:f.append(or_(AuditLog.action.ilike(f'%{search}%'),AuditLog.resource_id.ilike(f'%{search}%'),User.name.ilike(f'%{search}%')))
    if start or end:
        a,b=period(start,end);f.extend(span(AuditLog.created_at,a,b))
    total=await db.scalar(select(func.count()).select_from(q.where(*f).subquery()))
    rows=(await db.execute(q.where(*f).order_by(AuditLog.created_at.desc(),AuditLog.id).offset((page-1)*page_size).limit(page_size))).all()
    return page_result([{'id':e.id,'user_id':e.user_id,'actor_name':name,'action':e.action,'resource_type':e.resource_type,'resource_id':e.resource_id,'created_at':utc(e.created_at),'details_json':safe_value(e.details_json)} for e,name in rows],total,page,page_size)
