export type InlineToken =
  | { type: "text"; text: string }
  | { type: "strong"; text: string }
  | { type: "code"; text: string }
  | { type: "link"; text: string; href: string };

export type MarkdownBlock =
  | { type: "heading"; level: number; content: InlineToken[] }
  | { type: "paragraph"; content: InlineToken[] }
  | { type: "blockquote"; content: InlineToken[] }
  | { type: "list"; ordered: boolean; items: InlineToken[][] }
  | { type: "table"; headers: InlineToken[][]; rows: InlineToken[][][] }
  | { type: "code_block"; text: string }
  | { type: "rule" };

const headingRe = /^(#{1,6})\s+(.+)$/;
const unorderedListRe = /^\s*[-*+]\s+(.+)$/;
const orderedListRe = /^\s*\d+[.)]\s+(.+)$/;
const fenceRe = /^\s*```/;

export function parseMarkdown(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (fenceRe.test(line)) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !fenceRe.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "code_block", text: codeLines.join("\n") });
      index += index < lines.length ? 1 : 0;
      continue;
    }

    const headingMatch = line.match(headingRe);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        content: parseInlineMarkdown(headingMatch[2].trim()),
      });
      index += 1;
      continue;
    }

    if (isRule(line)) {
      blocks.push({ type: "rule" });
      index += 1;
      continue;
    }

    if (isTableStart(lines, index)) {
      const parsedTable = parseTable(lines, index);
      blocks.push(parsedTable.block);
      index = parsedTable.nextIndex;
      continue;
    }

    if (unorderedListRe.test(line) || orderedListRe.test(line)) {
      const ordered = orderedListRe.test(line);
      const items: InlineToken[][] = [];
      while (index < lines.length) {
        const itemMatch = lines[index].match(ordered ? orderedListRe : unorderedListRe);
        if (!itemMatch) break;
        items.push(parseInlineMarkdown(itemMatch[1].trim()));
        index += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    if (line.trim().startsWith(">")) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({
        type: "blockquote",
        content: parseInlineMarkdown(quoteLines.join(" ").trim()),
      });
      continue;
    }

    const paragraphLines: string[] = [line.trim()];
    index += 1;
    while (index < lines.length && shouldContinueParagraph(lines, index)) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push({
      type: "paragraph",
      content: parseInlineMarkdown(paragraphLines.join(" ")),
    });
  }

  return blocks;
}

export function parseInlineMarkdown(markdown: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  let remaining = markdown;

  while (remaining) {
    const match = findNextInlineMatch(remaining);
    if (!match) {
      pushText(tokens, remaining);
      break;
    }

    pushText(tokens, remaining.slice(0, match.index));
    const value = match.value;
    if (value.type === "link") {
      const href = sanitizeHref(value.href);
      if (href) {
        tokens.push({ type: "link", text: value.text, href });
      } else {
        pushText(tokens, value.text);
      }
    } else {
      tokens.push(value);
    }
    remaining = remaining.slice(match.index + match.raw.length);
  }

  return tokens;
}

function findNextInlineMatch(markdown: string):
  | {
      index: number;
      raw: string;
      value:
        | { type: "strong"; text: string }
        | { type: "code"; text: string }
        | { type: "link"; text: string; href: string };
    }
  | null {
  const patterns = [
    {
      regex: /\[([^\]]+)\]\(((?:[^()]|\([^)]*\))+)\)/,
      build: (match: RegExpMatchArray) => ({
        type: "link" as const,
        text: match[1],
        href: match[2],
      }),
    },
    {
      regex: /\*\*([^*]+)\*\*/,
      build: (match: RegExpMatchArray) => ({
        type: "strong" as const,
        text: match[1],
      }),
    },
    {
      regex: /`([^`]+)`/,
      build: (match: RegExpMatchArray) => ({
        type: "code" as const,
        text: match[1],
      }),
    },
  ];

  let next:
    | {
        index: number;
        raw: string;
        value:
          | { type: "strong"; text: string }
          | { type: "code"; text: string }
          | { type: "link"; text: string; href: string };
      }
    | null = null;

  for (const pattern of patterns) {
    const match = markdown.match(pattern.regex);
    if (!match || match.index === undefined) continue;
    if (next === null || match.index < next.index) {
      next = {
        index: match.index,
        raw: match[0],
        value: pattern.build(match),
      };
    }
  }

  return next;
}

function parseTable(
  lines: string[],
  startIndex: number,
): { block: Extract<MarkdownBlock, { type: "table" }>; nextIndex: number } {
  const headers = splitTableRow(lines[startIndex]).map(parseInlineMarkdown);
  const rows: InlineToken[][][] = [];
  let index = startIndex + 2;

  while (index < lines.length && isTableRow(lines[index])) {
    rows.push(splitTableRow(lines[index]).map(parseInlineMarkdown));
    index += 1;
  }

  return {
    block: { type: "table", headers, rows },
    nextIndex: index,
  };
}

function splitTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableStart(lines: string[], index: number): boolean {
  return (
    index + 1 < lines.length &&
    isTableRow(lines[index]) &&
    splitTableRow(lines[index]).length > 1 &&
    splitTableRow(lines[index + 1]).every((cell) => /^:?-{3,}:?$/.test(cell))
  );
}

function isTableRow(line: string): boolean {
  return line.includes("|") && line.trim().length > 0;
}

function isRule(line: string): boolean {
  return /^-{3,}$/.test(line.trim());
}

function shouldContinueParagraph(lines: string[], index: number): boolean {
  const line = lines[index];
  return (
    Boolean(line.trim()) &&
    !headingRe.test(line) &&
    !fenceRe.test(line) &&
    !isRule(line) &&
    !isTableStart(lines, index) &&
    !unorderedListRe.test(line) &&
    !orderedListRe.test(line) &&
    !line.trim().startsWith(">")
  );
}

function sanitizeHref(href: string): string {
  const trimmed = href.trim();
  if (/^(https?:|mailto:)/i.test(trimmed)) {
    return trimmed;
  }
  return "";
}

function pushText(tokens: InlineToken[], text: string): void {
  if (text) {
    tokens.push({ type: "text", text });
  }
}
