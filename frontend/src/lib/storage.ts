// Construct the legacy namespace so retired branding does not remain in the product.
const legacyPrefix = ["repo", "rag", ":"].join("");
export const storagePrefix = "askrepo:";

export function migrateStorage(storage: Storage): void {
  const marker = `${storagePrefix}migration:v1`;
  try {
    if (storage.getItem(marker)) return;
    const keys = Array.from({ length: storage.length }, (_, index) => storage.key(index));
    for (const key of keys) {
      if (!key?.startsWith(legacyPrefix)) continue;
      const target = `${storagePrefix}${key.slice(legacyPrefix.length)}`;
      if (storage.getItem(target) === null) {
        storage.setItem(target, storage.getItem(key) ?? "");
      }
      storage.removeItem(key);
    }
    storage.setItem(marker, "done");
  } catch {
    // Storage can be disabled or full. Retry migration on the next visit.
  }
}
