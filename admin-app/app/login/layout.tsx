import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Вход в админ-панель',
  description: 'Авторизация в панели управления',
  viewport: 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no',
}

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
