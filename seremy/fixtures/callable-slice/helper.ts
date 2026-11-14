export function leaf() { return 1 }
export const make = () => leaf()
export const named = function recur(n: number): number { return n ? recur(n - 1) : leaf() }
