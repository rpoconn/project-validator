// Budgets have no currency on the API; the app assumes USD.
const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

const date = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' })
const dateTime = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' })
// Due dates are picked as calendar days and stored as midnight UTC, so show them in UTC too.
const dueDate = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeZone: 'UTC' })

export function formatBudgetRange(min: number, max: number): string {
  return min === max ? currency.format(min) : `${currency.format(min)} – ${currency.format(max)}`
}

export const formatDate = (iso: string): string => date.format(new Date(iso))
export const formatDateTime = (iso: string): string => dateTime.format(new Date(iso))
export const formatDueDate = (iso: string): string => dueDate.format(new Date(iso))
