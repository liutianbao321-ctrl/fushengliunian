const APP_BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export function assetPath(path: string): string {
  return `${APP_BASE_PATH}${path.startsWith("/") ? path : `/${path}`}`;
}
