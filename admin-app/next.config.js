/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    serverComponentsExternalPackages: ['sqlite3']
  },
  env: {
    DATABASE_PATH: process.env.DATABASE_PATH || '../databases/group_connections.db'
  },
  // Отключаем линтинг в продакшене для экономии памяти
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Отключаем проверку типов в продакшене
  typescript: {
    ignoreBuildErrors: true,
  }
}

module.exports = nextConfig
