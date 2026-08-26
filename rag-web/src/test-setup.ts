/* eslint-disable */
// vitest node 环境无浏览器存储，用内存替身覆盖（sessionStorage/localStorage）。
class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  clear(): void {
    this.store.clear();
  }
  key(i: number): string | null {
    return Array.from(this.store.keys())[i] ?? null;
  }
  get length(): number {
    return this.store.size;
  }
}

(globalThis as unknown as Record<string, unknown>).sessionStorage = new MemoryStorage();
(globalThis as unknown as Record<string, unknown>).localStorage = new MemoryStorage();
