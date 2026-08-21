'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** Управление перенесено на главную (`/?tab=anonymous`). */
export default function AnonymousChatsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/auth/session');
        if (!res.ok) {
          router.replace('/');
          return;
        }
        const d = await res.json();
        router.replace(d.features?.anonymousChats ? '/?tab=anonymous' : '/');
      } catch {
        router.replace('/');
      }
    })();
  }, [router]);
  return (
    <div className="min-h-screen bg-background animated-bg text-white flex items-center justify-center p-4">
      <p className="text-gray-400 text-sm">Перенаправление на главную…</p>
    </div>
  );
}
