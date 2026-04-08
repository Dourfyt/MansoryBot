/**
 * Реестр чувствительности полей (ПДн) для аудита и будущего шифрования колонок.
 * Таблицы: support_messages.body, support_tickets.telegram_username, crm_users.email, crm_users.telegram_user_id
 */
export const PII_FIELDS = [
  { table: 'support_messages', column: 'body', sensitivity: 'pii_message' as const },
  { table: 'support_tickets', column: 'telegram_username', sensitivity: 'pii_identifier' as const },
  { table: 'crm_users', column: 'email', sensitivity: 'pii_contact' as const },
  { table: 'crm_users', column: 'telegram_user_id', sensitivity: 'pii_identifier' as const },
];
