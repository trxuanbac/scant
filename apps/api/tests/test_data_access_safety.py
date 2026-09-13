import pytest
from test_admin_core import ctx, auth
from app.models.entities import Project, UploadedFile
from app.core.config import settings

@pytest.mark.asyncio
async def test_other_users_cannot_use_dataset_id(ctx,tmp_path):
    c,f=ctx
    path=tmp_path/'private.csv';path.write_text('salary\n9500000\n')
    async with f() as db:
        db.add(Project(id='private-project',user_id='admin',name='Private',type='business'))
        await db.flush()
        db.add(UploadedFile(id='private-file',project_id='private-project',filename='private.csv',original_name='private.csv',file_type='excel',mime_type='text/csv',file_size=20,file_path=str(path),file_hash='a'*64))
        await db.commit()
    cases=[('GET','/profile/private-file',None),('POST','/aggregate',{'file_id':'private-file','group_by':'salary','metric_column':'salary'}),('POST','/chart-spec',{'file_id':'private-file','chart_type':'bar','group_by':'salary','metric_column':'salary'})]
    for method,url,body in cases:
        res=await c.request(method,'/api/v1/data'+url,headers=auth('user'),**({'json':body} if body else {}))
        assert res.status_code==404,(url,res.status_code,res.text)
    for endpoint in ['analyze-sheet','workbook-chat','workbook-analysis-action','apply-modifications','cross-file-compare']:
        res=await c.post('/api/v1/data/'+endpoint,headers=auth('user'),data={'file_id':'private-file','file_id_1':'private-file','file_id_2':'private-file','message':'xin chào','prompt':'xin chào','cells':'["A1"]'})
        assert res.status_code==404,(endpoint,res.status_code,res.text)
    res=await c.post('/api/v1/data/analyze-sheet',data={'file_id':'private-file'})
    assert res.status_code==401

@pytest.mark.asyncio
async def test_download_requires_file_bound_signed_token(ctx,tmp_path,monkeypatch):
    from app.services.storage.signed_url_service import signed_url_service
    c,_=ctx;monkeypatch.setattr(settings,'UPLOAD_DIR',tmp_path)
    (tmp_path/'private.xlsx').write_bytes(b'private')
    assert (await c.get('/api/v1/data/download-file?filename=private.xlsx')).status_code==403
    token=signed_url_service.generate_signed_token('data/private.xlsx','user',60)
    assert (await c.get('/api/v1/data/download-file',params={'filename':'private.xlsx','token':token})).status_code==200
    assert (await c.get('/api/v1/data/download-file',params={'filename':'other.xlsx','token':token})).status_code==403

@pytest.mark.asyncio
async def test_modification_rejects_invalid_cells_before_execution(ctx,tmp_path,monkeypatch):
    import io,openpyxl
    c,_=ctx;monkeypatch.setattr(settings,'UPLOAD_DIR',tmp_path)
    wb=openpyxl.Workbook();wb.active['A1']='value';output=io.BytesIO();wb.save(output)
    for cells in ['["A0"]','["XFE1"]','["A1048577"]','{"A1":true}','[1]','["A1",']:
        res=await c.post('/api/v1/data/apply-modifications',files={'file':('test.xlsx',output.getvalue())},data={'cells':cells,'sheet_name':'Sheet'})
        assert res.status_code==422,(cells,res.status_code,res.text)

@pytest.mark.asyncio
async def test_modified_file_download_and_source_preservation(ctx,tmp_path,monkeypatch):
    import io,openpyxl
    c,_=ctx;monkeypatch.setattr(settings,'UPLOAD_DIR',tmp_path)
    wb=openpyxl.Workbook();wb.active.title='Bảng lương';wb.active['A1']='=1+2';out=io.BytesIO();wb.save(out)
    response=await c.post('/api/v1/data/apply-modifications',files={'file':('../../payroll.xlsx',out.getvalue())},data={'cells':'["A1"]','sheet_name':'Bảng lương'})
    assert response.status_code==200,response.text
    downloaded=await c.get(response.json()['download_url'])
    assert downloaded.status_code==200
    result=openpyxl.load_workbook(io.BytesIO(downloaded.content))
    assert result.active['A1'].value=='=1+2'
    assert result.active['A1'].fill.fill_type=='solid'
    original=next(tmp_path.glob('preview_*'))
    assert openpyxl.load_workbook(original).active['A1'].fill.fill_type is None
    rejected=await c.post('/api/v1/data/apply-modifications',files={'file':('payroll.xlsx',out.getvalue())},data={'cells':'["A1"]','sheet_name':'Unknown'})
    assert rejected.status_code==422

@pytest.mark.asyncio
async def test_export_does_not_implicitly_write_google_sheet(ctx,tmp_path,monkeypatch):
    import io,openpyxl
    from unittest.mock import AsyncMock
    from app.services.data.google_sheets_service import google_sheets_service
    c,_=ctx;monkeypatch.setattr(settings,'UPLOAD_DIR',tmp_path)
    write=AsyncMock();monkeypatch.setattr(google_sheets_service,'highlight_cells',write)
    wb=openpyxl.Workbook();wb.active['A1']=42;buffer=io.BytesIO();wb.save(buffer)
    response=await c.post('/api/v1/data/apply-modifications',files={'file':('sheet.xlsx',buffer.getvalue())},data={'cells':'["A1"]','sheet_name':'Sheet','data_source_url':'https://docs.google.com/spreadsheets/d/123456789abcdefghijklmnop/edit'})
    assert response.status_code==200,response.text
    write.assert_not_called()

@pytest.mark.asyncio
async def test_chat_context_is_scoped_to_authenticated_user(ctx,tmp_path,monkeypatch):
    from unittest.mock import AsyncMock
    from app.services.data.workbook_chat_service import workbook_chat_service
    c,_=ctx;monkeypatch.setattr(settings,'UPLOAD_DIR',tmp_path)
    chat=AsyncMock(return_value={'answer':'Hello','actions':[],'pending_actions':[]})
    monkeypatch.setattr(workbook_chat_service,'chat',chat)
    for uid in ['user','admin']:
        response=await c.post('/api/v1/data/workbook-chat',headers=auth(uid),files={'file':('data.csv',b'Name,Value\nA,1')},data={'message':'xin chào','conversation_id':'same-client-id'})
        assert response.status_code==200,response.text
    ids=[call.kwargs['conversation_id'] for call in chat.await_args_list]
    assert ids[0]!=ids[1]
    assert ids[0].startswith('user:') and ids[1].startswith('admin:')
