'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** Управление перенесено на главную (`/?tab=anonymous`). */
export default function AnonymousChatsRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/?tab=anonymous');
  }, [router]);
  return (
    <div className="min-h-screen bg-background animated-bg text-white flex items-center justify-center p-4">
      <p className="text-gray-400 text-sm">Перенаправление на главную…</p>
    </div>
  );
}
