import { NextRequest, NextResponse } from 'next/server';
import { jwtVerify } from 'jose';

function getSecret(): Uint8Array {
  const p = process.env.CRM_SESSION_PEPPER?.trim();
  if (!p || p.length < 16) {
    return new TextEncoder().encode('dev-only-unsafe-pepper-change-me');
  }
  return new TextEncoder().encode(p);
}

const supportPaths = ['/support'];
const supportApiPrefix = '/api/support';
/** Страницы только для admin (support перенаправляем на главную). */
const adminOnlyPaths = ['/crm-settings', '/admin'];

function isSupportRoute(pathname: string): boolean {
  return supportPaths.some((p) => pathname === p || pathname.startsWith(p + '/')) || pathname.startsWith(supportApiPrefix);
}

function isAdminOnlyRoute(pathname: string): boolean {
  return adminOnlyPaths.some((p) => pathname === p || pathname.startsWith(p + '/'));
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api/auth') ||
    pathname.startsWith('/api/telegram') ||
    pathname === '/login' ||
    pathname === '/mini' ||
    pathname.startsWith('/favicon')
  ) {
    return NextResponse.next();
  }

  const token = request.cookies.get('sessionToken')?.value;
  if (!token) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  let role: string;
  try {
    const { payload } = await jwtVerify(token, getSecret(), { algorithms: ['HS256'] });
    role = typeof payload.role === 'string' ? payload.role : '';
  } catch {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  const supportArea = isSupportRoute(pathname);

  if (supportArea) {
    if (role === 'admin' || role === 'support') {
      return NextResponse.next();
    }
    return NextResponse.redirect(new URL('/login', request.url));
  }

  if (isAdminOnlyRoute(pathname)) {
    if (role === 'admin') {
      return NextResponse.next();
    }
    if (role === 'support') {
      return NextResponse.redirect(new URL('/', request.url));
    }
    return NextResponse.redirect(new URL('/login', request.url));
  }

  if (role === 'admin' || role === 'support') {
    return NextResponse.next();
  }

  return NextResponse.redirect(new URL('/login', request.url));
}

export const config = {
  matcher: ['/((?!api/auth|_next/static|_next/image|favicon.ico).*)'],
};
