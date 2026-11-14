export type RouteName = 'dashboard' | 'workout' | 'history' | 'leaderboard' | 'profile' | 'result'
export type Route = { name: RouteName; sessionId?: number }

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#?\/?/, '').replace(/\/+$/, '')
  if (path === 'workout' || path === 'history' || path === 'leaderboard' || path === 'profile') {
    return { name: path }
  }
  const result = /^result\/(\d+)$/.exec(path)
  if (result && Number(result[1]) > 0) return { name: 'result', sessionId: Number(result[1]) }
  return { name: 'dashboard' }
}

export function routeHash(route: Route): string {
  return route.name === 'result' ? `#/result/${route.sessionId}` : `#/${route.name}`
}
