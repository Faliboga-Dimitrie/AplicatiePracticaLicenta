export function todayIsoDate(): string {
  const now = new Date()
  const localMidnightSafe = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return localMidnightSafe.toISOString().slice(0, 10)
}
