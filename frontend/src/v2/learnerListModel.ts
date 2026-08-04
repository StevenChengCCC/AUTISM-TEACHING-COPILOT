export const LEARNER_PAGE_SIZE = 6;

export function paginateLearners<T>(
  items: T[],
  requestedPage: number,
  pageSize = LEARNER_PAGE_SIZE,
): { items: T[]; page: number; pageCount: number; total: number } {
  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const page = Math.min(pageCount, Math.max(1, requestedPage));
  const start = (page - 1) * pageSize;
  return { items: items.slice(start, start + pageSize), page, pageCount, total };
}
