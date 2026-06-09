export const businessTableSticky = { offsetHeader: 0 };

export const businessTableScrollX = { x: "max-content" };

export function businessTableClassName(...classNames: Array<string | false | null | undefined>): string {
  return ["business-table", ...classNames.filter(Boolean)].join(" ");
}
