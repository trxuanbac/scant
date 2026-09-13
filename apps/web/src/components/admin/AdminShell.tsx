'use client';
import { createContext, useContext, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Menu, Shield, ArrowLeft } from 'lucide-react';
import { adminApi, AdminSession } from '@/lib/adminApi';
import { ApiError } from '@/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';
import { DarkModeToggle } from '@/components/DarkModeToggle';

const SessionContext = createContext<AdminSession | null>(null);
export const useAdminSession = () => useContext(SessionContext);
export const adminNav = [
  ['Tổng quan', '', ''], ['Người dùng', 'users', 'Quản lý'], ['AI Jobs', 'ai-jobs', 'Quản lý'], ['Dự án', 'projects', 'Quản lý'], ['Tài liệu', 'documents', 'Quản lý'], ['Lưu trữ', 'storage', 'Quản lý'], ['Mẫu báo cáo', 'templates', 'Quản lý'],
  ['Sử dụng AI', 'usage', 'Sử dụng & thanh toán'], ['Quota', 'quotas', 'Sử dụng & thanh toán'], ['Gói dịch vụ', 'billing/plans', 'Sử dụng & thanh toán'], ['Thanh toán', 'payments', 'Sử dụng & thanh toán'], ['Đăng ký dịch vụ', 'billing', 'Sử dụng & thanh toán'],
  ['Tích hợp', 'integrations', 'Vận hành'], ['Hệ thống', 'system', 'Vận hành'], ['Nhật ký', 'audit-logs', 'Vận hành'],
  ['Cấu hình AI', 'ai-config', 'Cấu hình'], ['Nhà cung cấp', 'providers', 'Cấu hình'], ['Cài đặt', 'settings', 'Cấu hình'],
];
export function AdminShell({ children }: { children: React.ReactNode }) {
  const token = useAuthStore(s => s.token);
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const session = useQuery({ queryKey: ['admin-session', token, pathname], queryFn: adminApi.session, retry: false, staleTime: 0, refetchOnWindowFocus: true });
  if (session.isPending) return <div className="admin-console p-8" role="status">Đang xác minh quyền quản trị…</div>;
  if (session.error || !session.data) {
    const status = session.error instanceof ApiError ? session.error.status : 0;
    return <div className="admin-console grid place-content-center gap-4 p-8"><h1 className="text-xl font-semibold">{status === 403 ? '403 · Bạn không có quyền quản trị' : status === 401 ? 'Phiên đăng nhập đã hết hạn' : 'Không thể xác minh phiên quản trị'}</h1><p>{session.error?.message}</p><div className="flex gap-3"><Link href={status === 401 ? '/login' : '/'}>Trở về {status === 401 ? 'đăng nhập' : 'ứng dụng'}</Link><button onClick={() => session.refetch()}>Thử lại</button></div></div>;
  }
  return <SessionContext.Provider value={session.data}><div className="admin-console flex">
    <aside className={`${mobileOpen ? 'block' : 'hidden'} ${collapsed ? 'lg:hidden' : 'lg:block'} fixed inset-y-0 left-0 z-30 w-60 overflow-y-auto border-r bg-card p-3 lg:sticky lg:top-0 lg:h-screen lg:shrink-0`}>
      <div className="flex items-center justify-between border-b px-2 pb-4 pt-2"><span className="flex items-center gap-2 font-semibold"><Shield size={17}/> Admin Console</span><button onClick={() => { setMobileOpen(false); setCollapsed(true); }} aria-label="Thu gọn menu">×</button></div>
      <nav aria-label="Điều hướng quản trị" className="py-3">{adminNav.filter(n => n[2] !== 'Cấu hình' || session.data.is_superuser).map(([label, path, group], index, entries) => <div key={path}>{group && entries[index-1]?.[2] !== group && <p className="admin-muted px-2 pb-1 pt-4 text-[11px] uppercase tracking-wide">{group}</p>}<Link onClick={() => { setMobileOpen(false); }} href={`/admin${path ? `/${path}` : ''}`} aria-current={pathname === `/admin${path ? `/${path}` : ''}` ? 'page' : undefined} className={`block rounded-md px-3 py-2 ${pathname === `/admin${path ? `/${path}` : ''}` ? 'bg-muted font-medium' : 'admin-muted'}`}>{label}</Link></div>)}</nav>
    </aside>
    {mobileOpen && <button className="fixed inset-0 z-20 !rounded-none !bg-black/30 lg:hidden" aria-label="Đóng menu" onClick={() => setMobileOpen(false)}/>}
    <div className="min-w-0 flex-1"><header className="flex flex-wrap items-center gap-3 border-b bg-card px-4 py-3 lg:px-6"><button aria-label="Mở menu quản trị" onClick={() => { if(window.innerWidth < 1024)setMobileOpen(!mobileOpen);else setCollapsed(!collapsed); }}><Menu size={16}/></button><nav aria-label="Đường dẫn" className="admin-muted text-xs"><Link href="/admin">Admin</Link> / {adminNav.find(n => `/admin/${n[1]}` === pathname)?.[0] || (pathname === '/admin' ? 'Tổng quan' : 'Chi tiết')}</nav><form className="ml-auto" onSubmit={e => {e.preventDefault(); const q = new FormData(e.currentTarget).get('q'); router.push(`/admin/search?q=${encodeURIComponent(String(q || ''))}`);}}><input name="q" aria-label="Tìm kiếm toàn hệ thống" placeholder="Tìm người dùng, dự án, job…" className="w-48" required minLength={2}/></form><Link href="/admin/system" className="text-xs underline">Trạng thái hệ thống</Link><DarkModeToggle/><span className="admin-muted text-xs">{session.data.name || session.data.email} · {session.data.is_superuser ? 'Super Admin' : 'Admin'}</span><Link href="/" title="Về ứng dụng" aria-label="Về ứng dụng"><ArrowLeft size={18}/></Link></header><main className="min-w-0 p-4 lg:p-6">{children}</main></div>
  </div></SessionContext.Provider>;
}
