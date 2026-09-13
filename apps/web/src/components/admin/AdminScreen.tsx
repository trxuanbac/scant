'use client';

import { useState } from 'react';
import { ConfigurationEditor } from './ConfigurationEditor';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { adminApi, AdminRecord, AdminOverview } from '@/lib/adminApi';
import { ApiError } from '@/lib/api';
import { useAdminSession } from './AdminShell';
import { DataTable, RecordView, Filters, Pagination, Trend, ActionDialog, ActionSpec, Column, display, labels } from './AdminPrimitives';

interface Module { title: string; endpoint: string; columns: string[]; filters?: string[]; dates?: boolean; sorts?: string[]; note?: string }
const modules: Record<string, Module> = {
  users:{title:'Người dùng',endpoint:'users',columns:['name','email','role','plan','is_active','total_tokens','cost_usd','projects_count','last_active','created_at'],filters:['role','plan','status'],dates:true,sorts:['created_at','name','email','plan','last_active','total_tokens']},
  'ai-jobs':{title:'Tác vụ AI',endpoint:'jobs',columns:['id','job_type','user_email','project_name','status','progress_percent','created_at'],filters:['status','job_type','user_id'],dates:true,sorts:['created_at','status','job_type','progress_percent'],note:'Chỉ bao gồm tác vụ đã ghi vào bảng Job. Không suy đoán model hoặc chi phí khi chưa liên kết được usage.'},
  quotas:{title:'Hạn mức sử dụng',endpoint:'quotas',columns:['user_name','email','plan','tokens_used_this_month','monthly_token_limit','cost_usd_this_month','monthly_cost_limit_usd','remaining_tokens','reset_at','status'],filters:['plan','status'],note:'Hạn mức token và ngân sách đang được hệ thống thực thi. Các loại quota khác chưa có bộ đếm độc lập.'},
  projects:{title:'Dự án',endpoint:'projects',columns:['name','owner_email','type','documents_count','reports_count','jobs_count','storage_bytes','created_at'],filters:['user_id'],dates:true,sorts:['created_at','name','storage_bytes']},
  documents:{title:'Tài liệu',endpoint:'documents',columns:['title','owner_email','project_id','document_type','file_type','file_size','is_parsed','created_at'],filters:['user_id','project_id'],dates:true,sorts:['created_at','title','file_size'],note:'Metadata vận hành. Nội dung tài liệu và đường dẫn tải file không được cung cấp cho quản trị viên mặc định.'},
  storage:{title:'Lưu trữ',endpoint:'storage',columns:['original_name','owner_email','file_type','file_size','is_parsed','created_at'],filters:['user_id','project_id'],dates:true,sorts:['created_at','file_size']},
  templates:{title:'Mẫu báo cáo',endpoint:'templates',columns:['name','category','owner_email','version','visibility','is_system','usage_count','updated_at'],filters:['user_id'],dates:true,sorts:['created_at','name','usage_count']},
  integrations:{title:'Tích hợp',endpoint:'integrations',columns:['name','category','status','requests','failures','average_latency_ms','last_observed_at'],dates:true,sorts:['name','category','status','requests'],note:'Đã cấu hình không đồng nghĩa đang kết nối tốt. Không trả về API key hoặc token OAuth.'},
  providers:{title:'Nhà cung cấp',endpoint:'providers',columns:['name','category','configured','supported','health','requests','failures','average_latency_ms'],dates:true,sorts:['name','category','status','requests']},
  payments:{title:'Thanh toán',endpoint:'payments',columns:['id','user_id','plan','amount','currency','provider','status','created_at','paid_at'],filters:['status','plan','user_id'],dates:true,sorts:['created_at','status','plan']},
  billing:{title:'Đăng ký dịch vụ',endpoint:'billing',columns:['id','user_id','plan','status','provider','payment_id','started_at','ended_at'],filters:['status','plan','user_id'],dates:true,sorts:['started_at','status','plan']},
  'billing/plans':{title:'Gói dịch vụ',endpoint:'plans',columns:['name','plan_tier','checkout_amount','checkout_currency','monthly_tokens_limit','monthly_ai_budget_usd','storage_limit_mb']},
  'audit-logs':{title:'Nhật ký quản trị',endpoint:'audit-logs',columns:['created_at','actor_name','action','resource_type','resource_id','details_json'],filters:['action','actor','target'],dates:true},
};
const superPages=['providers','ai-config','settings'];
function rows(value: unknown): AdminRecord[] { return Array.isArray(value) ? value.filter((v):v is AdminRecord => !!v && typeof v==='object' && !Array.isArray(v)) : []; }
function record(value: unknown): AdminRecord { return value && typeof value==='object' && !Array.isArray(value) ? value as AdminRecord : {}; }

function Overview({data}:{data:AdminOverview}) {
  return <><p className="admin-muted text-xs">Kỳ UTC: {display(data.period.from)} → {display(data.period.to)} (không gồm thời điểm kết thúc). So sánh với kỳ liền trước cùng độ dài.</p>
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{data.metrics.map(metric=><Link key={metric.key} href={metric.href} className="admin-panel p-4" title={metric.definition}><div className="admin-muted text-xs">{metric.label}</div><div className="mt-2 text-2xl font-semibold tracking-tight">{display(metric.value)} <span className="text-xs font-normal">{metric.unit==='count'?'':metric.unit}</span></div><p className="admin-muted mt-2 text-xs">{metric.change_pct===null?'Chưa có kỳ so sánh':`${metric.change_pct>0?'+':''}${display(metric.change_pct)}% so với kỳ trước`}</p><p className="admin-muted mt-2 text-[11px]">{metric.definition}</p></Link>)}</div>
    <div className="grid gap-4 xl:grid-cols-2"><Trend title="Người dùng mới" rows={data.trends.users} series={[{key:'value',label:'Đăng ký'}]}/><Trend title="Token theo ngày" rows={data.trends.tokens} series={[{key:'input_tokens',label:'Input'},{key:'output_tokens',label:'Output'}]}/><Trend title="Chi phí AI ước tính (USD)" rows={data.trends.cost} series={[{key:'value',label:'USD'}]}/><section className="space-y-3"><h2 className="font-medium">Trạng thái tác vụ trong kỳ</h2><DataTable rows={data.breakdowns.jobs || []} columns={[{key:'name',label:'Trạng thái',link:r=>`/admin/ai-jobs?status=${encodeURIComponent(String(r.name))}`},{key:'value',label:'Số tác vụ'}]}/></section></div>
    <div className="grid gap-4 xl:grid-cols-2"><section className="space-y-3"><h2 className="font-medium">Theo chức năng</h2><DataTable rows={data.breakdowns.features || []} columns={[{key:'name',label:'Chức năng',link:r=>`/admin/usage?feature=${encodeURIComponent(String(r.name))}`},{key:'requests'},{key:'tokens'},{key:'cost_usd'}]}/></section><section className="space-y-3"><h2 className="font-medium">Model đã sử dụng</h2><DataTable rows={data.breakdowns.models || []} columns={[{key:'name',label:'Model',link:r=>`/admin/usage?model=${encodeURIComponent(String(r.name))}`},{key:'requests'},{key:'tokens'},{key:'cost_usd'}]}/></section></div>
    <aside className="admin-muted text-xs"><RecordView data={data.unavailable}/></aside></>;
}

function Usage({data}:{data:AdminRecord}) {
  const summary=record(data.summary);
  return <><p className="admin-muted text-xs">Usage đã ghi nhận bởi AI Gateway. Token/chi phí của lần gọi thất bại và các luồng gọi provider trực tiếp chưa được đo đầy đủ.</p><div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{Object.entries(summary).map(([key,value])=><div className="admin-panel p-3" key={key}><p className="admin-muted text-xs">{labels[key] || key}</p><p className="mt-1 text-xl font-semibold">{display(value)}</p></div>)}</div><div className="grid gap-4 lg:grid-cols-2"><Trend title="Token theo ngày" rows={rows(data.trend)} series={[{key:'input_tokens',label:'Input'},{key:'output_tokens',label:'Output'}]}/><Trend title="Chi phí AI (USD)" rows={rows(data.trend)} series={[{key:'cost_usd',label:'USD'}]}/></div>{[['by_model','Theo model'],['by_feature','Theo chức năng'],['by_provider','Theo nhà cung cấp'],['by_user','Người dùng sử dụng nhiều nhất']].map(([key,title])=><section key={key} className="space-y-3"><h2 className="font-medium">{title}</h2><DataTable rows={rows(data[key])} columns={[{key:'name',label:'Đối tượng'},{key:'requests'},{key:'tokens',label:'Token'},{key:'cost_usd'},{key:'latency_ms'}]}/></section>)}<h2 className="font-medium">Lịch sử yêu cầu</h2><DataTable rows={rows(data.items)} columns={['created_at','user_id','provider','model','task_type','total_tokens','estimated_cost_usd','status'].map(key=>({key}))}/><Pagination total={Number(data.total)} page={Number(data.page)} size={Number(data.page_size)}/></>;
}

export function AdminScreen({path}:{path:string[]}) {
  const session=useAdminSession();const params=useSearchParams() ?? new URLSearchParams();const queryClient=useQueryClient();
  const [action,setAction]=useState<ActionSpec|null>(null);const [notice,setNotice]=useState('');
  const section=path.join('/');const base=path[0] || '';const id=path[1];const detail=!!id && !(base==='billing');
  const pageConfig=modules[section] || modules[base];
  const allowed=!superPages.includes(base) || !!session?.is_superuser;
  let endpoint=section===''?'overview':base==='usage'?'usage':base==='system'?'system/health':base==='search'?'search':base==='ai-config'?'ai-config':base==='settings'?'settings':pageConfig?.endpoint || '';
  if(detail && base==='projects')endpoint=`projects/${id}`;
  if(detail && base==='templates')endpoint=`templates/${id}/validation`;
  if(detail && base==='users')endpoint=`users/${id}`;
  if(detail && base==='ai-jobs')endpoint=`jobs/${id}`;
  if(detail && base==='payments')endpoint=`payments/${id}`;
  const q=new URLSearchParams(params.toString());q.delete('tab');
  if(!q.has('page_size') && !['overview','system/health','ai-config','settings','search'].includes(endpoint))q.set('page_size','25');
  const query=q.toString();
  const result=useQuery({queryKey:['admin-data',session?.id,endpoint,query],queryFn:()=>adminApi.get(endpoint,query),enabled:allowed && !!endpoint && !!session && (base!=='search' || (q.get('q')||'').length>=2),retry:false});
  const mutate=(title:string,description:string,url:string,values:AdminRecord={},method:'POST'|'PATCH'='POST',fields:ActionSpec['fields']=[])=>setAction({title,description,fields,run:inputs=>adminApi.mutate(url,{...values,...inputs},method)});
  const userActions=(row:AdminRecord)=><>
    <Link href={`/admin/users/${row.id}`} className="underline">Chi tiết</Link>
    {(session?.is_superuser || row.role==='user') && <><button onClick={()=>mutate(row.is_active?'Khóa tài khoản':'Mở khóa tài khoản','Thay đổi có hiệu lực ngay trên API. Lý do được ghi vào nhật ký.',`users/${row.id}`,{is_active:!row.is_active},'PATCH')}>{row.is_active?'Khóa':'Mở khóa'}</button><button onClick={()=>mutate('Đổi gói dịch vụ','Hạn mức theo gói mới được áp dụng; lượng đã dùng được giữ nguyên.',`users/${row.id}`,{},'PATCH',[{key:'plan',label:'Gói',options:['free','pro','team','enterprise'],value:String(row.plan)}])}>Đổi gói</button><Link className="underline" href={`/admin/quotas?search=${encodeURIComponent(String(row.email))}`}>Quota</Link></>}
    {session?.is_superuser && <button onClick={()=>mutate('Đổi quyền truy cập','Quyền được xác minh từ dữ liệu máy chủ; không thể tự hạ quyền tài khoản đang đăng nhập.',`users/${row.id}`,{},'PATCH',[{key:'role',label:'Vai trò',options:['user','admin','super_admin'],value:String(row.role)}])}>Phân quyền</button>}
  </>;
  const tableActions=(row:AdminRecord)=>{
    if(base==='users')return userActions(row);
    if(base==='ai-jobs')return <Link className="underline" href={`/admin/ai-jobs/${row.id}`}>Chi tiết</Link>;
    if(base==='projects')return <Link className="underline" href={`/admin/projects/${row.id}`}>Chi tiết</Link>;
    if(base==='payments')return <Link className="underline" href={`/admin/payments/${row.id}`}>Chi tiết</Link>;
    if(base==='quotas')return <><button onClick={()=>mutate('Điều chỉnh hạn mức','Đây là hạn mức riêng cho tài khoản, được lưu cùng lý do và giá trị trước/sau.',`quotas/${row.user_id}`,{},'PATCH',[{key:'monthly_token_limit',label:'Giới hạn token/tháng',type:'number',value:String(row.monthly_token_limit)},{key:'monthly_cost_limit_usd',label:'Ngân sách USD/tháng',type:'number',value:String(row.monthly_cost_limit_usd)}])}>Điều chỉnh</button><button onClick={()=>mutate('Đặt lại bộ đếm quota','Lượng sử dụng trong bộ đếm được đặt về 0; lịch sử usage vẫn được giữ để truy vết.',`quotas/${row.user_id}`,{reset:true},'PATCH')}>Đặt lại</button></>;
    if(base==='templates')return <><Link className="underline" href={`/admin/templates/${row.id}`}>Kiểm tra mẫu</Link>{row.is_public && (!row.is_system || session?.is_superuser) && <button onClick={()=>mutate('Ẩn mẫu','Ngừng công khai mẫu này.',`templates/${row.id}/unpublish`)}>Ẩn mẫu</button>}{!row.is_public && row.is_system && session?.is_superuser && <button onClick={()=>mutate('Phát hành mẫu hệ thống','Mẫu hệ thống sẽ được công khai. Không áp dụng cho mẫu riêng của người dùng.',`templates/${row.id}/publish`)}>Phát hành</button>}</>;
    return null;
  };
  const title=section===''?'Tổng quan vận hành':base==='usage'?'Sử dụng AI':base==='system'?'Tình trạng hệ thống':base==='ai-config'?'Cấu hình AI':base==='settings'?'Cài đặt hệ thống':base==='search'?'Kết quả tìm kiếm':pageConfig?.title || 'Không tìm thấy trang';
  const data=result.data || {};
  const columns:Column[]=(pageConfig?.columns || []).map(key=>({key,...(key==='details_json'?{render:(row:AdminRecord)=><details><summary className="cursor-pointer">Xem thay đổi</summary><RecordView data={row.details_json}/></details>}:{})}));
  const tab=params.get('tab') || 'user';
  return <div className="space-y-5"><header className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-semibold tracking-tight">{title}{detail?' · Chi tiết':''}</h1><p className="admin-muted mt-1 text-sm">{pageConfig?.note || 'Dữ liệu thực từ hệ thống. Các mục chưa thu thập được sẽ được ghi rõ.'}</p></div><button onClick={()=>result.refetch()} disabled={result.isFetching}>Làm mới</button></header>
    {!allowed?<p role="alert">403 · Mục này chỉ dành cho Super Admin.</p>:!endpoint?<p>Không có mục này.</p>:<>
    {!detail && !['system','settings','ai-config','search'].includes(base) && <Filters search={section!=='' && !['usage','billing/plans'].includes(section)} order={section!=='' && !['usage','quotas','audit-logs','billing/plans'].includes(section)} key={`${section}:${params.toString()}`} fields={base==='usage'?['provider','model','feature','user_id']:pageConfig?.filters || []} dates={section==='' || base==='usage' || pageConfig?.dates}/>} 
    {notice && <p role="status" className="rounded-md border border-emerald-300 p-3 text-sm">{notice}</p>}
    {base==='search' && (q.get('q')||'').length<2?<p>Nhập ít nhất 2 ký tự vào ô tìm kiếm ở header.</p>:result.isPending?<div role="status" className="grid animate-pulse gap-3"><span className="sr-only">Đang tải dữ liệu quản trị</span>{[1,2,3,4].map(i=><div key={i} className="h-16 rounded-md bg-muted"/>)}</div>:result.error?<div role="alert" className="admin-panel space-y-3 p-5"><h2 className="font-medium">Không tải được {title.toLowerCase()}</h2><p>{result.error instanceof ApiError && result.error.status===403?'Bạn không có quyền thực hiện yêu cầu này.':result.error.message}</p><button onClick={()=>result.refetch()}>Thử lại</button></div>:section===''?<Overview data={data as unknown as AdminOverview}/>:base==='usage'?<Usage data={data}/>:base==='users' && detail?<>
      <div className="admin-panel space-y-3 p-4"><RecordView data={data.user}/><div className="flex flex-wrap gap-2">{userActions(record(data.user))}</div></div>
      <nav aria-label="Chi tiết người dùng" className="flex flex-wrap gap-2">{[['user','Tổng quan'],['usage','Sử dụng AI'],['projects','Dự án'],['documents','Tài liệu'],['jobs','Tác vụ'],['payments','Thanh toán'],['audit_logs','Nhật ký']].map(([key,label])=><Link key={key} className={`rounded-md border px-3 py-2 ${tab===key?'bg-muted font-medium':''}`} href={`/admin/users/${id}?tab=${key}`} aria-current={tab===key?'page':undefined}>{label}</Link>)}</nav>
      {tab==='user'?<RecordView data={data.quota}/>:tab==='usage'?<Usage data={record(data.usage)}/>:<RecordView data={data[tab]}/>}
      <p className="admin-muted text-xs">Các danh sách gần đây giới hạn 25 bản ghi. <Link className="underline" href={String(data.billing_href || '/admin/payments')}>Xem toàn bộ thanh toán</Link></p>
    </>:base==='ai-jobs' && detail?<><RecordView data={data}/><div className="flex gap-2">{['cancel','retry'].map(key=><button key={key} disabled={!record(data.actions)[key]} onClick={()=>mutate(key==='cancel'?'Hủy tác vụ':'Chạy lại tác vụ',display(record(data.actions).cancellation),`jobs/${id}/${key}`)}>{key==='cancel'?'Hủy tác vụ':'Chạy lại'}</button>)}</div><p className="admin-muted text-xs">{display(record(data.actions).reason)}</p></>:detail && ['payments','projects','templates'].includes(base)?<RecordView data={data}/>:base==='search'?<>{[['users','Người dùng','users'],['projects','Dự án','projects'],['jobs','Tác vụ','ai-jobs'],['payments','Thanh toán','payments']].map(([key,label,route])=><section key={key} className="space-y-3"><h2 className="font-medium">{label}</h2><DataTable rows={rows(data[key])} columns={[{key:'id',link:row=>`/admin/${route}/${row.id}`},...(key==='users'?[{key:'name'},{key:'email'}]:key==='projects'?[{key:'name'}]:[{key:'status'}])]}/></section>)}</>:['system','settings','ai-config'].includes(base)?<>{(base==='settings' || base==='ai-config') && data.runtime && <ConfigurationEditor key={`${base}:${record(data.runtime).revision}`} kind={base} data={data} confirm={setAction}/>}<RecordView data={Object.fromEntries(Object.entries(data).filter(([key])=>key!=='runtime'))}/></>:<>
      {data.provider_status && <p role="status" className="admin-panel p-3 text-sm">Nhà cung cấp thanh toán: {display(data.provider_status)}. {display(data.read_only_reason)}</p>}
      {data.summary && <RecordView data={data.summary}/>}
      {data.limitations && <RecordView data={data.limitations}/>}
      <DataTable rows={rows(data.items)} columns={columns} actions={!detail && ['users','ai-jobs','quotas','payments','projects','templates'].includes(base)?tableActions:undefined}/>
      <Pagination total={Number(data.total || 0)} page={Number(data.page || 1)} size={Number(data.page_size || 25)} sorts={!detail?pageConfig?.sorts:undefined}/>
    </>}
    </>}
    <ActionDialog key={action?.title || "closed"} action={action} close={()=>setAction(null)} done={()=>{setNotice('Đã lưu thay đổi và ghi nhật ký quản trị.');queryClient.invalidateQueries({queryKey:['admin-data']});}}/>
  </div>;
}
