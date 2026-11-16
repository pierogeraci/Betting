import { DownloadWorkbookQueryParams } from "@workspace/api-zod";

export function parseExportQuery(query: unknown) {
  if (!query || typeof query !== "object" || Array.isArray(query)) {
    return DownloadWorkbookQueryParams.safeParse(query);
  }

  const params = query as Record<string, unknown>;
  const rawIncludeRestricted = params.includeRestricted;
  if (
    rawIncludeRestricted !== undefined &&
    rawIncludeRestricted !== true &&
    rawIncludeRestricted !== false &&
    rawIncludeRestricted !== "true" &&
    rawIncludeRestricted !== "false"
  ) {
    return DownloadWorkbookQueryParams.safeParse({
      ...params,
      scope: "invalid",
    });
  }

  return DownloadWorkbookQueryParams.safeParse({
    ...params,
    includeRestricted:
      rawIncludeRestricted === undefined
        ? undefined
        : rawIncludeRestricted === true || rawIncludeRestricted === "true",
  });
}
