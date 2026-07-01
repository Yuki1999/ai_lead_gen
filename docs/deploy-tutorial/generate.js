/**
 * 海外渠道拓展系统 · 部署教程（完整版）
 * 面向实施工程师，覆盖联网部署 + 离线部署。
 *
 * Cover recipe: R1 (Pure Paragraph) + palette DM-1 (Deep Cyan, tech/AI)
 */

const {
  Document, Packer, Paragraph, TextRun, Header, Footer, PageBreak, PageNumber,
  AlignmentType, HeadingLevel, BorderStyle, ShadingType, WidthType,
  Table, TableRow, TableCell, TableLayoutType, NumberFormat,
  TabStopType, TabStopPosition, LevelFormat, TableOfContents, StyleLevel,
} = require("docx");
const fs = require("fs");

// ─── Palette: DM-1 Deep Cyan ──────────────────────────────────────────────
const P = {
  bg: "162235",
  primary: "0F2A44",     // body heading colour on white pages
  body: "1F2937",
  secondary: "4B5563",
  accent: "1B6B7A",      // darkened accent for white-page tables/borders
  coverAccent: "37DCF2", // bright accent only on dark cover bg
  cover: { titleColor: "FFFFFF", subtitleColor: "B0B8C0", metaColor: "90989F", footerColor: "687078" },
  table: { headerBg: "1B6B7A", headerText: "FFFFFF", innerLine: "C8DDE2", surface: "EDF3F5" },
};

// ─── Border helpers ───────────────────────────────────────────────────────
const NB = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const allNoBorders = {
  top: NB, bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB,
};
const cellNoBorders = { top: NB, bottom: NB, left: NB, right: NB };

// ─── Title layout helpers (from design-system.md, simplified for our title) ──
function splitTitleLines(title, charsPerLine) {
  if (title.length <= charsPerLine) return [title];
  const breakAfter = new Set([
    ..."\u3001\u3002\uff0c\uff1b\uff1a\uff01\uff1f",
    ..."\u7684\u4e0e\u548c\u53ca\u4e4b\u5728\u4e8e\u4e3a",
    ..."-_\u2014\u2013\u00b7/",
    ..." \t",
  ]);
  const lines = [];
  let remaining = title;
  while (remaining.length > charsPerLine) {
    let breakAt = -1;
    for (let i = charsPerLine; i >= Math.floor(charsPerLine * 0.6); i--) {
      if (i < remaining.length && breakAfter.has(remaining[i - 1])) {
        breakAt = i;
        break;
      }
    }
    if (breakAt === -1) {
      const limit = Math.min(remaining.length, Math.ceil(charsPerLine * 1.3));
      for (let i = charsPerLine + 1; i < limit; i++) {
        if (breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
      }
    }
    if (breakAt === -1) breakAt = charsPerLine;
    lines.push(remaining.slice(0, breakAt).trim());
    remaining = remaining.slice(breakAt).trim();
  }
  if (remaining) lines.push(remaining);
  if (lines.length > 1 && lines[lines.length - 1].length <= 2) {
    const last = lines.pop();
    lines[lines.length - 1] += last;
  }
  return lines;
}

function calcTitleLayout(title, maxWidthTwips, preferredPt = 40, minPt = 24) {
  const charWidth = (pt) => pt * 20;
  let titlePt = preferredPt;
  let lines;
  while (titlePt >= minPt) {
    const cpl = Math.floor(maxWidthTwips / charWidth(titlePt));
    if (cpl < 2) { titlePt -= 2; continue; }
    lines = splitTitleLines(title, cpl);
    if (lines.length <= 3) break;
    titlePt -= 2;
  }
  if (!lines || lines.length > 3) {
    const cpl = Math.floor(maxWidthTwips / charWidth(minPt));
    lines = splitTitleLines(title, cpl);
    titlePt = minPt;
  }
  return { titlePt, titleLines: lines };
}

function calcCoverSpacing({ titleLineCount, titlePt, hasSubtitle, hasEnglishLabel, metaLineCount, fixedHeight = 400 }) {
  const pageHeight = 16838;
  const SAFETY = 1200;
  const usable = pageHeight - SAFETY;
  const titleHeight = titleLineCount * (titlePt * 23 + 200);
  const subtitleHeight = hasSubtitle ? (12 * 23 + 600) : 0;
  const englishLabelHeight = hasEnglishLabel ? (9 * 23 + 600) : 0;
  const metaHeight = metaLineCount * (10 * 23 + 100);
  const implicit = 3 * 300;
  const remaining = usable - (titleHeight + subtitleHeight + englishLabelHeight + metaHeight + fixedHeight + implicit);
  const safeRemaining = Math.max(remaining, 400);
  const rawTop = Math.floor(safeRemaining * 0.45);
  const rawBottom = Math.floor(safeRemaining * 0.45);
  const FOOTER_MIN = 800;
  const bottomSpacing = Math.max(rawBottom, FOOTER_MIN);
  const topSpacing = Math.max(rawTop - Math.max(0, FOOTER_MIN - rawBottom), 400);
  return { topSpacing, bottomSpacing };
}

// ─── Cover R1 ────────────────────────────────────────────────────────────
function buildCoverR1(config) {
  const padL = 1200, padR = 800;
  const availableWidth = 11906 - padL - padR - 300;
  const { titlePt, titleLines } = calcTitleLayout(config.title, availableWidth, 40, 24);
  const titleSize = titlePt * 2;
  const spacing = calcCoverSpacing({
    titleLineCount: titleLines.length, titlePt,
    hasSubtitle: !!config.subtitle, hasEnglishLabel: !!config.englishLabel,
    metaLineCount: (config.metaLines || []).length,
    fixedHeight: 400,
  });
  const accentLeft = { style: BorderStyle.SINGLE, size: 8, color: P.coverAccent, space: 12 };
  const children = [];

  children.push(new Paragraph({ spacing: { before: spacing.topSpacing } }));

  if (config.englishLabel) {
    children.push(new Paragraph({
      indent: { left: padL, right: padR }, spacing: { after: 500 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: P.coverAccent, space: 8 } },
      children: [new TextRun({
        text: config.englishLabel.split("").join("  "),
        size: 18, color: P.coverAccent,
        font: { ascii: "Calibri", eastAsia: "SimHei" }, characterSpacing: 40,
      })],
    }));
  }

  for (let i = 0; i < titleLines.length; i++) {
    children.push(new Paragraph({
      indent: { left: padL },
      spacing: {
        after: i < titleLines.length - 1 ? 100 : 300,
        line: Math.ceil(titlePt * 23), lineRule: "atLeast",
      },
      children: [new TextRun({
        text: titleLines[i], size: titleSize, bold: true,
        color: P.cover.titleColor, font: { eastAsia: "SimHei", ascii: "Arial" },
      })],
    }));
  }

  if (config.subtitle) {
    children.push(new Paragraph({
      indent: { left: padL }, spacing: { after: 800 },
      children: [new TextRun({
        text: config.subtitle, size: 24, color: P.cover.subtitleColor,
        font: { eastAsia: "Microsoft YaHei", ascii: "Arial" },
      })],
    }));
  }

  for (const line of (config.metaLines || [])) {
    children.push(new Paragraph({
      indent: { left: padL + 200 }, spacing: { after: 80 },
      border: { left: accentLeft },
      children: [new TextRun({
        text: line, size: 24, color: P.cover.metaColor,
        font: { eastAsia: "Microsoft YaHei", ascii: "Arial" },
      })],
    }));
  }

  children.push(new Paragraph({ spacing: { before: spacing.bottomSpacing } }));

  children.push(new Paragraph({
    indent: { left: padL, right: padR },
    border: { top: { style: BorderStyle.SINGLE, size: 2, color: P.coverAccent, space: 8 } },
    spacing: { before: 200 },
    children: [
      new TextRun({ text: config.footerLeft || "", size: 16, color: P.cover.footerColor, font: { ascii: "Arial" } }),
      new TextRun({ text: "                                        " }),
      new TextRun({ text: config.footerRight || "", size: 16, color: P.cover.footerColor, font: { ascii: "Arial" } }),
    ],
  }));

  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: 16838, rule: "exact" },
      children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: P.bg },
        borders: cellNoBorders,
        children,
      })],
    })],
  })];
}

// ─── Body builders ───────────────────────────────────────────────────────
const c = (hex) => hex.replace("#", "");
const CN_HEAD_FONT = { ascii: "Arial", eastAsia: "SimHei" };
const CN_BODY_FONT = { ascii: "Calibri", eastAsia: "SimSun" };
const MONO_FONT = { ascii: "Courier New", eastAsia: "SimSun" };

function h1(text, opts = {}) {
  const runs = [];
  if (opts.pageBreakBefore) runs.push(new TextRun({ children: [new PageBreak()] }));
  runs.push(new TextRun({ text, bold: true, size: 32, color: P.primary, font: CN_HEAD_FONT }));
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 480, after: 240, line: 480, lineRule: "atLeast" },
    keepNext: true,
    children: runs,
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 320, after: 160, line: 420, lineRule: "atLeast" },
    keepNext: true,
    children: [new TextRun({ text, bold: true, size: 30, color: P.primary, font: CN_HEAD_FONT })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 240, after: 120, line: 380, lineRule: "atLeast" },
    keepNext: true,
    children: [new TextRun({ text, bold: true, size: 26, color: P.primary, font: CN_HEAD_FONT })],
  });
}
function body(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 312, after: 80 },
    children: [new TextRun({ text, size: 24, color: P.body, font: CN_BODY_FONT })],
  });
}
function note(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { left: 200, right: 200, firstLine: 0 },
    spacing: { line: 312, before: 80, after: 80 },
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: P.accent, space: 8 } },
    children: [
      new TextRun({ text: "\u63d0\u793a\uff1a", bold: true, size: 22, color: P.accent, font: CN_BODY_FONT }),
      new TextRun({ text, size: 22, color: P.body, font: CN_BODY_FONT }),
    ],
  });
}
function warn(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { left: 200, right: 200, firstLine: 0 },
    spacing: { line: 312, before: 80, after: 80 },
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: "C0392B", space: 8 } },
    shading: { type: ShadingType.CLEAR, fill: "FBEDEC" },
    children: [
      new TextRun({ text: "\u26a0 \u6ce8\u610f\uff1a", bold: true, size: 22, color: "C0392B", font: CN_BODY_FONT }),
      new TextRun({ text, size: 22, color: P.body, font: CN_BODY_FONT }),
    ],
  });
}

// Bullet list as plain paragraphs with leading bullet (avoids list numbering quirks)
function bullet(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { left: 480, hanging: 240 },
    spacing: { line: 312, after: 60 },
    children: [
      new TextRun({ text: "\u2022  ", size: 24, color: P.accent, bold: true }),
      new TextRun({ text, size: 24, color: P.body, font: CN_BODY_FONT }),
    ],
  });
}

// Code block paragraph
function code(line) {
  return new Paragraph({
    alignment: AlignmentType.LEFT,
    spacing: { line: 280, lineRule: "atLeast", after: 0 },
    indent: { firstLine: 0, left: 0 },
    shading: { type: ShadingType.CLEAR, fill: "F4F6F8" },
    border: {
      left: { style: BorderStyle.SINGLE, size: 12, color: P.accent, space: 4 },
      top: { style: BorderStyle.SINGLE, size: 2, color: "DDE3E8", space: 2 },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: "DDE3E8", space: 2 },
      right: { style: BorderStyle.SINGLE, size: 2, color: "DDE3E8", space: 2 },
    },
    children: [new TextRun({ text: line, size: 20, font: MONO_FONT, color: "0F2A44" })],
  });
}
function codeBlock(lines) {
  // Render each line as its own bordered paragraph so wrapping looks like a code block
  return lines.map((l) => code(l));
}

// Table cell helpers
function tcText(text, opts = {}) {
  return new Paragraph({
    alignment: opts.align || AlignmentType.LEFT,
    spacing: { line: 280, after: 0 },
    children: [new TextRun({
      text, size: opts.size || 22, bold: !!opts.bold,
      color: opts.color || P.body, font: opts.mono ? MONO_FONT : CN_BODY_FONT,
    })],
  });
}
function headerCell(text) {
  return new TableCell({
    shading: { type: ShadingType.CLEAR, fill: P.table.headerBg },
    margins: { top: 100, bottom: 100, left: 140, right: 140 },
    children: [tcText(text, { bold: true, color: P.table.headerText, align: AlignmentType.LEFT })],
  });
}
function bodyCell(text, opts = {}) {
  return new TableCell({
    margins: { top: 80, bottom: 80, left: 140, right: 140 },
    children: [tcText(text, opts)],
  });
}
function dataTable(headers, rows, widths) {
  const headerRow = new TableRow({
    tableHeader: true, cantSplit: true,
    children: headers.map((h) => headerCell(h)),
  });
  const dataRows = rows.map((r, idx) => new TableRow({
    cantSplit: true,
    children: r.map((cellText, i) => {
      const tc = new TableCell({
        shading: { type: ShadingType.CLEAR, fill: idx % 2 === 0 ? "FFFFFF" : P.table.surface },
        margins: { top: 80, bottom: 80, left: 140, right: 140 },
        children: [tcText(cellText, { mono: i === 0 })],
      });
      return tc;
    }),
  }));
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    columnWidths: widths,
    rows: [headerRow, ...dataRows],
    borders: {
      top: { style: BorderStyle.SINGLE, size: 8, color: P.accent },
      bottom: { style: BorderStyle.SINGLE, size: 8, color: P.accent },
      left: NB, right: NB,
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: P.table.innerLine },
      insideVertical: NB,
    },
  });
}

// ─── Cover config ────────────────────────────────────────────────────────
const coverConfig = {
  title: "\u6d77\u5916\u6e20\u9053\u62d3\u5c55\u7cfb\u7edf\u90e8\u7f72\u6559\u7a0b",
  subtitle: "\u9762\u5411\u5b9e\u65bd\u5de5\u7a0b\u5e08 \u00b7 \u8054\u7f51\u4e0e\u79bb\u7ebf\u53cc\u573a\u666f",
  englishLabel: "DEPLOYMENT GUIDE",
  metaLines: [
    "\u4ea7\u54c1\uff1aMedbot \u6d77\u5916\u4ee3\u7406\u5546\u62d3\u5ba2\u5e73\u53f0",
    "\u6280\u672f\u6808\uff1aFastAPI + Vue + Vite + Pi Agent Sidecar",
    "\u90e8\u7f72\u65b9\u5f0f\uff1aDocker Compose v2",
    "\u9002\u7528\u7248\u672c\uff1av1.x",
  ],
  footerLeft: "INTERNAL  \u00b7  DEPLOYMENT",
  footerRight: "v1.0  \u00b7  2026",
};

// ─── Body chapters content ───────────────────────────────────────────────
const bodyChildren = [];

// ── Chapter 1 ─────────────────────────────
bodyChildren.push(h1("1. \u7cfb\u7edf\u6982\u8ff0\u4e0e\u67b6\u6784"));

bodyChildren.push(h2("1.1 \u672c\u6587\u9002\u7528\u8303\u56f4"));
bodyChildren.push(body("\u672c\u6559\u7a0b\u9762\u5411\u5b9e\u65bd\u5de5\u7a0b\u5e08\uff0c\u4ecb\u7ecd\u300a\u6d77\u5916\u6e20\u9053\u62d3\u5c55\u7cfb\u7edf\u300b\u5728\u4e24\u79cd\u5178\u578b\u573a\u666f\u4e0b\u7684\u90e8\u7f72\u6d41\u7a0b\uff1a\u670d\u52a1\u5668\u8054\u7f51\u73af\u5883\u4e0b\u7684\u4e00\u952e\u90e8\u7f72\uff0c\u4ee5\u53ca\u5ba2\u6237\u5185\u7f51\u96b6\u7ebf\u73af\u5883\u4e0b\u7684\u4ea4\u4ed8\u5305\u5b89\u88c5\u3002\u4e24\u79cd\u573a\u666f\u4f7f\u7528\u540c\u4e00\u5957\u4ee3\u7801\u4ed3\u5e93\u3001\u540c\u4e00\u5957\u955c\u50cf\uff0c\u90e8\u7f72\u811a\u672c\u5206\u522b\u4f4d\u4e8e scripts/ \u4e0b\u3002"));
bodyChildren.push(body("\u9605\u8bfb\u672c\u6587\u524d\uff0c\u8bfb\u8005\u9700\u638c\u63e1\uff1aLinux \u57fa\u672c\u547d\u4ee4\uff08\u670d\u52a1\u3001\u7528\u6237\u3001\u7aef\u53e3\u3001\u9632\u706b\u5899\uff09\u3001Docker \u4e0e Docker Compose v2 \u7684\u4f7f\u7528\u3001\u4ee5\u53ca .env \u73af\u5883\u53d8\u91cf\u7684\u8bbe\u7f6e\u3002\u672c\u6587\u4e0d\u590d\u8ff0\u8fd9\u4e9b\u57fa\u7840\u6982\u5ff5\u3002"));

bodyChildren.push(h2("1.2 \u4e1a\u52a1\u80fd\u529b\u6982\u8ff0"));
bodyChildren.push(body("\u7cfb\u7edf\u9762\u5411\u533b\u7597\u5668\u68b0\u6d77\u5916\u6e20\u9053\u62d3\u5c55\u573a\u666f\uff0c\u4f9d\u636e\u4ea7\u54c1\u8d44\u6599\u751f\u6210\u4ea7\u54c1\u753b\u50cf\uff0c\u8c03\u7528\u5b9e\u65f6\u7f51\u9875\u641c\u7d22\u5e76\u4ece\u5b98\u7f51/\u8054\u7cfb\u9875\u62bd\u53d6\u516c\u5f00\u90ae\u7bb1\u5165\u5e93\uff1b\u5e73\u53f0\u5185\u7f6e\u53d1\u9001\u961f\u5217\u3001\u9000\u4fe1\u5904\u7406\u3001\u62b5\u5236\u540d\u5355\u4e0e\u9000\u8ba2\u673a\u5236\uff0c\u53d1\u9001\u8d70\u4f01\u4e1a\u90ae\u7bb1\uff08Exchange EWS\uff09\u4ee5\u4fdd\u62a4\u57df\u540d\u58f0\u8a89\uff1bAgent \u4fa7\u53ef\u4e0e\u5546\u4e1a\u5de5\u5177\u7ed1\u5b9a\uff0c\u63d0\u4f9b\u5bf9\u8bdd\u5f0f\u62d3\u5ba2\u3001\u56de\u590d\u7406\u89e3\u4e0e\u590d\u6742\u95ee\u9898\u8f6c\u4eba\u5de5\u3002"));

bodyChildren.push(h2("1.3 \u67b6\u6784\u4e0e\u5bb9\u5668\u6e05\u5355"));
bodyChildren.push(body("Docker Compose \u90e8\u7f72\u540e\u542f\u52a8\u4e09\u4e2a\u670d\u52a1\u5bb9\u5668\uff0c\u53ca\u4e00\u4e2a\u6301\u4e45\u5316\u6570\u636e\u5377\uff1a"));

bodyChildren.push(dataTable(
  ["\u670d\u52a1", "\u955c\u50cf", "\u7aef\u53e3\u6620\u5c04", "\u804c\u8d23"],
  [
    ["frontend", "medbot-frontend", "FRONTEND_PORT \u2192 80", "Nginx \u6258\u7ba1\u9759\u6001\u8d44\u6e90\uff0c\u540c\u6e90 /api/* \u53cd\u4ee3\u5230 backend"],
    ["backend", "medbot-backend", "BACKEND_PORT \u2192 8000", "FastAPI + SQLite\uff0c\u4e1a\u52a1\u63a5\u53e3 + RBAC \u9274\u6743 + Agent \u53cd\u4ee3"],
    ["agent", "medbot-agent", "\u4ec5\u5bb9\u5668\u7f51\u5185 8011", "Pi Coding Agent sidecar\uff0c\u52a0\u8f7d overseas-distributor-prospecting skill"],
    ["medbot-data (volume)", "\u2014", "\u2014", "SQLite \u6570\u636e\u5e93 \u6587\u4ef6\u6301\u4e45\u5316\uff1a/data/medbot.db"],
  ],
  [2200, 2400, 2400, 4906],
));

bodyChildren.push(new Paragraph({ spacing: { after: 120 } }));
bodyChildren.push(body("\u670d\u52a1\u95f4\u8c03\u7528\u5173\u7cfb\uff1a\u6d4f\u89c8\u5668 \u2192 frontend\uff08\u540c\u6e90 /api\uff09\u2192 backend \u2192 agent\uff08\u5bb9\u5668\u7f51\u5185 http://agent:8011\uff09\u3002\u524d\u540e\u7aef\u540c\u6e90\u8bbf\u95ee\u907f\u514d\u4e86\u8de8\u57df\u95ee\u9898\uff0cAgent \u53ea\u5bf9 backend \u5bb9\u5668\u53ef\u89c1\uff0c\u4e0d\u5bf9\u5916\u66b4\u9732\u3002"));

bodyChildren.push(h2("1.4 \u4ee4\u724c\u4e0e\u5bc6\u94a5\u4f53\u7cfb\uff08\u91cd\u8981\uff09"));
bodyChildren.push(body("\u7cfb\u7edf\u91cc\u540c\u65f6\u5b58\u5728\u4e09\u79cd\u4e0d\u540c\u7528\u9014\u7684\u4ee4\u724c/\u5bc6\u94a5\uff0c\u4e0d\u8981\u6df7\u7528\uff1a"));
bodyChildren.push(bullet("AGENT_TOKEN\uff1abackend \u8c03\u7528 agent \u7684\u5185\u90e8 Bearer \u4ee4\u724c\u3002\u90e8\u7f72\u811a\u672c\u4f1a\u81ea\u52a8\u751f\u6210\u5e76\u540c\u65f6\u5199\u5165 .env \u4e0e agent/.env\uff0c\u4e24\u8fb9\u5fc5\u987b\u4e00\u81f4\u3002"));
bodyChildren.push(bullet("MEDBOT_SERVICE_TOKEN \uff08\u5f00\u542f\u9274\u6743\u540e\u7684 backend\uff09\u3001BACKEND_SERVICE_TOKEN\uff08agent \u7aef\uff09\uff1aagent \u8c03\u7528\u53d7 RBAC \u4fdd\u62a4\u7684 backend \u4e1a\u52a1\u63a5\u53e3\u65f6\u643a\u5e26\u7684\u670d\u52a1\u4ee4\u724c\uff0c\u90e8\u7f72\u811a\u672c\u540c\u6837\u4f1a\u81ea\u52a8\u751f\u6210\u5e76\u540c\u6b65\u3002"));
bodyChildren.push(bullet("\u5927\u6a21\u578b API Key\uff1aOPENAI_API_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY\uff0c\u5b58\u4e8e agent/.env\uff0c\u9700\u5b9e\u65bd\u5de5\u7a0b\u5e08\u624b\u5de5\u586b\u5199\u3002"));
bodyChildren.push(bullet("MEDBOT_AUTH_SECRET\uff08\u53ef\u9009\uff09\uff1aJWT \u7b7e\u540d\u5bc6\u94a5\uff0c\u4e0d\u8bbe\u7f6e\u65f6\u540e\u7aef\u9996\u6b21\u542f\u52a8\u4f1a\u81ea\u52a8\u751f\u6210\u5e76\u6301\u4e45\u5316\u5230 settings \u8868\u3002"));

// ── Chapter 2 ─────────────────────────────
bodyChildren.push(h1("2. \u90e8\u7f72\u524d\u7f6e\u6761\u4ef6", { pageBreakBefore: true }));

bodyChildren.push(h2("2.1 \u786c\u4ef6\u4e0e\u64cd\u4f5c\u7cfb\u7edf"));
bodyChildren.push(body("\u751f\u4ea7\u73af\u5883\u63a8\u8350 Linux \u670d\u52a1\u5668\uff08Ubuntu 22.04+ \u6216 RHEL/CentOS 8+\uff09\u3002\u672c\u5730\u5f00\u53d1\u4e0e\u6f14\u793a\u53ef\u4f7f\u7528 macOS \u4f5c\u4e3a\u4e34\u65f6\u73af\u5883\u3002"));

bodyChildren.push(dataTable(
  ["\u8d44\u6e90", "\u6700\u4f4e", "\u63a8\u8350", "\u8bf4\u660e"],
  [
    ["CPU", "2 \u6838", "4 \u6838", "agent \u8d70\u5927\u6a21\u578b\u5728\u4e91\u4fa7\uff0c\u672c\u673a CPU \u538b\u529b\u4e0d\u5927"],
    ["\u5185\u5b58", "2 GB", "4 GB", "backend + agent + frontend \u4e09\u5bb9\u5668\u603b\u5360\u7528\u7ea6 600 MB"],
    ["\u78c1\u76d8", "5 GB", "20 GB", "\u955c\u50cf\u7ea6 1\u20132 GB\uff0c\u4f59\u91cf\u7559\u7ed9 SQLite \u4e0e\u65e5\u5fd7"],
    ["\u67b6\u6784", "x86_64 / amd64", "x86_64", "ARM/\u4fe1\u521b\u73af\u5883\u9700\u4ea4\u4ed8\u5bf9\u5e94\u67b6\u6784\u955c\u50cf"],
  ],
  [1800, 2000, 2000, 4106],
));

bodyChildren.push(new Paragraph({ spacing: { after: 120 } }));
bodyChildren.push(warn("ARM \u4e0e\u4fe1\u521b\u73af\u5883\uff08\u9e32\u9e4f\u3001\u98de\u817e\u7b49\uff09\u9700\u8981\u5728\u540c\u67b6\u6784\u7684\u6784\u5efa\u673a\u4e0a\u91cd\u65b0\u8fd0\u884c make-offline-package.sh \u751f\u6210 arm64 \u955c\u50cf\uff0cx86 \u955c\u50cf\u4e0d\u80fd\u76f4\u63a5\u8df3\u67b6\u6784\u8fd0\u884c\u3002"));

bodyChildren.push(h2("2.2 \u8f6f\u4ef6\u4f9d\u8d56"));
bodyChildren.push(body("\u4e24\u79cd\u573a\u666f\u90fd\u4ec5\u4f9d\u8d56 Docker Engine \u4e0e Docker Compose v2\uff0c\u4e0d\u4f9d\u8d56\u5bbf\u4e3b\u673a\u7684 Python / Node \u73af\u5883\u3002"));
bodyChildren.push(bullet("Docker Engine 24+ \u6216 Docker Desktop\uff08macOS / Windows \u5f00\u53d1\u673a\uff09"));
bodyChildren.push(bullet("Docker Compose v2 \u63d2\u4ef6\uff08docker compose\uff0c\u975e docker-compose v1\uff09"));
bodyChildren.push(bullet("\u4ec5\u79bb\u7ebf\u4ea4\u4ed8\u9700\u8981\uff1atar \u3001gzip\u3001shasum\uff08\u4e3b\u6d41 Linux \u9ed8\u8ba4\u81ea\u5e26\uff09"));

bodyChildren.push(h2("2.3 \u7aef\u53e3\u4e0e\u7f51\u7edc"));
bodyChildren.push(body("\u9ed8\u8ba4\u7aef\u53e3\u5982\u4e0b\u3002\u82e5\u4e0e\u73b0\u6709\u670d\u52a1\u51b2\u7a81\uff0c\u53ef\u5728 .env \u4e2d\u8c03\u6574 FRONTEND_PORT \u4e0e BACKEND_PORT \u540e\u91cd\u88c5\u3002"));
bodyChildren.push(dataTable(
  ["\u7aef\u53e3", "\u670d\u52a1", "\u5bf9\u8c01\u5f00\u653e", "\u8bf4\u660e"],
  [
    ["5173", "frontend (Nginx)", "\u7528\u6237\u6d4f\u89c8\u5668", "Web \u7ba1\u7406\u540e\u53f0\u5165\u53e3\uff0c\u5305\u542b /api \u53cd\u4ee3"],
    ["8000", "backend (FastAPI)", "\u53ef\u53ea\u5bf9\u5185\u7f51\u5f00\u653e", "\u5982\u679c\u5b8c\u5168\u8d70\u524d\u7aef\u4ee3\u7406\u53ef\u4e0d\u66b4\u9732"],
    ["8011", "agent sidecar", "\u4ec5\u5bb9\u5668\u7f51\u5185", "\u4e0d\u9700\u5bf9\u5916\u66b4\u9732\uff0c\u9ed8\u8ba4\u4e0d\u6620\u5c04\u4e3b\u673a\u7aef\u53e3"],
  ],
  [1300, 2200, 2300, 4106],
));

bodyChildren.push(new Paragraph({ spacing: { after: 120 } }));
bodyChildren.push(body("\u51fa\u7ad9\u7f51\u7edc\u9700\u6c42\uff1abackend \u8fd0\u884c\u65f6\u4f1a\u5bf9\u516c\u5171\u641c\u7d22\u5f15\u64ce\u4e0e\u76ee\u6807\u516c\u53f8\u5b98\u7f51\u53d1\u8d77 HTTPS \u8bf7\u6c42\u62bd\u53d6\u90ae\u7bb1\uff1bagent \u4f1a\u8bbf\u95ee\u9009\u5b9a\u7684\u5927\u6a21\u578b\u670d\u52a1\u5546\uff08api.openai.com\u3001api.deepseek.com\u3001dashscope.aliyuncs.com \u7b49\uff09\u3002\u96b6\u7ebf\u73af\u5883\u8bf7\u4f7f\u7528\u4f01\u4e1a\u53cd\u5411\u4ee3\u7406\u6216 LLM \u7f51\u5173\u7edf\u4e00\u51fa\u7f51\u3002"));

bodyChildren.push(h2("2.4 \u9884\u68c0\u811a\u672c"));
bodyChildren.push(body("\u4ed3\u5e93\u63d0\u4f9b scripts/preflight.sh \u4f5c\u4e3a\u90e8\u7f72\u524d\u7684\u73af\u5883\u68c0\u67e5\u3002\u5728\u4efb\u4f55\u573a\u666f\u4e0b\uff0c\u90fd\u5efa\u8bae\u5148\u8dd1\u4e00\u904d\uff1a"));
bodyChildren.push(...codeBlock([
  "$ ./scripts/preflight.sh 5173 8000",
  "[\u7cfb\u7edf] \u64cd\u4f5c\u7cfb\u7edf\uff1aUbuntu 22.04.4 LTS    \u67b6\u6784\uff1ax86_64",
  "[Docker] \u5df2\u5b89\u88c5 docker: Docker version 27.x  \u5b88\u62a4\u8fdb\u7a0b\u8fd0\u884c\u4e2d",
  "[Compose] \u5df2\u5b89\u88c5 Docker Compose v2: v2.30.x",
  "[\u7aef\u53e3] \u524d\u7aef\u7aef\u53e3 5173 \u7a7a\u95f2  \u540e\u7aef\u7aef\u53e3 8000 \u7a7a\u95f2",
  "[\u8d44\u6e90] \u53ef\u7528\u78c1\u76d8: 42G   \u5185\u5b58: 8G",
  "\u2705 \u9884\u68c0\u5168\u90e8\u901a\u8fc7\uff0c\u53ef\u4ee5\u5b89\u88c5",
]));
bodyChildren.push(new Paragraph({ spacing: { after: 120 } }));
bodyChildren.push(body("\u8f93\u51fa\u4e2d\u4efb\u4f55\u4e00\u9879 \u2717\uff08\u786c\u6027\u4e0d\u8db3\uff09\u4f1a\u4ee4\u811a\u672c\u9000\u51fa\u7801\u975e 0\uff1b\u51fa\u73b0 \uff01\uff08\u63d0\u9192\u9879\uff09\u9700\u786e\u8ba4\u540e\u624d\u53ef\u7ee7\u7eed\u3002\u8bf7\u52ff\u8df3\u8fc7\u9884\u68c0\u76f4\u63a5\u90e8\u7f72\u3002"));

// ── Chapter 3 ─────────────────────────────
bodyChildren.push(h1("3. \u8054\u7f51\u73af\u5883\u90e8\u7f72", { pageBreakBefore: true }));

bodyChildren.push(h2("3.1 \u9002\u7528\u573a\u666f"));
bodyChildren.push(body("\u9002\u7528\u4e8e\u5185\u90e8\u6f14\u793a\u670d\u52a1\u5668\u3001\u4e91\u4e0a POC \u73af\u5883\u3001\u5f00\u53d1\u8c03\u8bd5\u3001\u4ee5\u53ca\u5ba2\u6237\u6307\u5b9a\u5141\u8bb8\u7ed5\u6cd5\u62c9\u53d6\u516c\u6709\u955c\u50cf\u7684\u4f01\u4e1a\u73af\u5883\u3002\u8054\u7f51\u90e8\u7f72\u542b deploy.sh \u811a\u672c\uff0c\u4e00\u6761\u547d\u4ee4\u5b8c\u6210\u751f\u6210\u4ee4\u724c \u00b7 \u62c9\u53d6\u4f9d\u8d56 \u00b7 \u6784\u5efa\u955c\u50cf \u00b7 \u542f\u52a8\u5bb9\u5668\u7684\u6240\u6709\u52a8\u4f5c\u3002"));

bodyChildren.push(h2("3.2 \u90e8\u7f72\u6b65\u9aa4"));

bodyChildren.push(h3("3.2.1 \u62c9\u53d6\u4ee3\u7801"));
bodyChildren.push(...codeBlock([
  "$ git clone <\u4ed3\u5e93\u5730\u5740> ai_lead_gen",
  "$ cd ai_lead_gen",
]));

bodyChildren.push(h3("3.2.2 \u521b\u5efa\u73af\u5883\u53d8\u91cf"));
bodyChildren.push(body("deploy.sh \u4f1a\u81ea\u52a8\u62f7\u8d1d\u6a21\u677f\uff0c\u4f60\u4e5f\u53ef\u4ee5\u624b\u52a8\u62f7\u8d1d\u540e\u63d0\u524d\u586b\u5199\u3002\u53ea\u6709 agent/.env \u91cc\u7684\u5927\u6a21\u578b API Key \u9700\u8981\u624b\u5de5\u586b\u5165\uff1b\u5176\u4f59\u4ee4\u724c\u3001\u670d\u52a1\u95f4\u5730\u5740\u3001\u7aef\u53e3\u90fd\u4f1a\u88ab\u811a\u672c\u8986\u76d6\u4e3a\u751f\u4ea7\u9ed8\u8ba4\u503c\u3002"));
bodyChildren.push(...codeBlock([
  "$ cp .env.deploy.example .env",
  "$ cp agent/.env.example agent/.env",
  "$ $EDITOR agent/.env   # \u586b\u5199 OPENAI_API_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY \u4e4b\u4e00",
]));

bodyChildren.push(h3("3.2.3 \u8fd0\u884c\u90e8\u7f72\u811a\u672c"));
bodyChildren.push(...codeBlock([
  "$ ./scripts/deploy.sh",
]));
bodyChildren.push(body("\u811a\u672c\u4f1a\u4f9d\u6b21\u6267\u884c\u4ee5\u4e0b\u52a8\u4f5c\uff1a"));
bodyChildren.push(bullet("\u68c0\u67e5 Docker \u4e0e Docker Compose v2 \u662f\u5426\u5b89\u88c5"));
bodyChildren.push(bullet("\u82e5\u4e24\u4e2a .env \u6587\u4ef6\u4e0d\u5b58\u5728\u5219\u4ece\u6a21\u677f\u751f\u6210"));
bodyChildren.push(bullet("\u751f\u6210 AGENT_TOKEN\uff0c\u540c\u6b65\u5199\u5165 .env \u4e0e agent/.env"));
bodyChildren.push(bullet("\u751f\u6210 MEDBOT_SERVICE_TOKEN\uff0c\u540c\u6b65\u5199\u5165 .env \u4e0e agent/.env \u7684 BACKEND_SERVICE_TOKEN"));
bodyChildren.push(bullet("\u5c06 agent/.env \u7684 BACKEND_BASE_URL\u3001AGENT_HOST\u3001AGENT_PORT\u3001AGENT_CORS_ORIGIN \u8c03\u6574\u4e3a\u5bb9\u5668\u9ed8\u8ba4\u503c"));
bodyChildren.push(bullet("\u68c0\u67e5 agent/.env \u662f\u5426\u586b\u4e86 LLM API Key\uff08\u672a\u586b\u53ea\u8b66\u544a\uff0c\u4e0d\u4e2d\u65ad\uff09"));
bodyChildren.push(bullet("\u6267\u884c docker compose up -d --build\uff0c\u968f\u540e docker compose ps"));

bodyChildren.push(h3("3.2.4 \u9a8c\u8bc1\u542f\u52a8\u72b6\u6001"));
bodyChildren.push(body("\u811a\u672c\u7ed3\u675f\u540e\u4f1a\u8f93\u51fa\u8bbf\u95ee\u5730\u5740\u3002\u7ea66\u5230 30 \u79d2\u540e\u4e09\u4e2a\u5bb9\u5668\u90fd\u5e94\u8fbe\u5230 healthy\uff1a"));
bodyChildren.push(...codeBlock([
  "$ docker compose ps",
  "NAME                IMAGE              STATUS                   PORTS",
  "ai_lead_gen-agent     medbot-agent       Up (healthy)             8011/tcp",
  "ai_lead_gen-backend   medbot-backend     Up (healthy)             0.0.0.0:8000->8000/tcp",
  "ai_lead_gen-frontend  medbot-frontend    Up (healthy)             0.0.0.0:5173->80/tcp",
]));
bodyChildren.push(note("\u9996\u6b21\u542f\u52a8\u9700\u8981\u62c9\u53d6\u57fa\u7840\u955c\u50cf\u5e76\u6784\u5efa\u4e09\u4e2a\u5bb9\u5668\u955c\u50cf\uff0c\u8017\u65f6\u53d6\u51b3\u4e8e\u51fa\u7ad9\u5e26\u5bbd\uff0c\u901a\u5e38 3\u201310 \u5206\u949f\u3002"));

bodyChildren.push(h2("3.3 \u9996\u6b21\u8bbf\u95ee"));
bodyChildren.push(body("\u90e8\u7f72\u5b8c\u6210\u540e\uff0c\u6253\u5f00\u6d4f\u89c8\u5668\u8bbf\u95ee\u524d\u7aef\u5730\u5740\u3002\u9ed8\u8ba4\u7ba1\u7406\u5458\u8d26\u53f7\uff1a"));
bodyChildren.push(dataTable(
  ["\u9879", "\u503c"],
  [
    ["\u524d\u7aef\u5730\u5740", "http://<\u670d\u52a1\u5668IP>:5173"],
    ["\u540e\u7aef\u5065\u5eb7\u68c0\u67e5", "http://<\u670d\u52a1\u5668IP>:8000/health"],
    ["\u9ed8\u8ba4\u7ba1\u7406\u5458\u7528\u6237\u540d", "admin"],
    ["\u9ed8\u8ba4\u7ba1\u7406\u5458\u5bc6\u7801", "admin123"],
  ],
  [3500, 6606],
));
bodyChildren.push(new Paragraph({ spacing: { after: 120 } }));
bodyChildren.push(warn("\u9996\u6b21\u767b\u5f55\u540e\u524d\u7aef\u4f1a\u5f3a\u5236\u5f39\u51fa\u4fee\u6539\u5bc6\u7801\u5bf9\u8bdd\u6846\uff0c\u4e0d\u53ef\u8df3\u8fc7\u3002\u8bf7\u5728\u4ea4\u4ed8\u7ed9\u5ba2\u6237\u524d\u4fee\u6539\u4e3a\u4e1a\u52a1\u65b9\u63a5\u7ba1\u7684\u5bc6\u7801\u3002"));

bodyChildren.push(h2("3.4 \u751f\u4ea7\u57df\u540d\u4e0e HTTPS"));
bodyChildren.push(body("\u90e8\u7f72\u5230\u751f\u4ea7\u73af\u5883\u4f7f\u7528\u57df\u540d\u65f6\uff0c\u9700\u8981\u4fee\u6539\u4ee5\u4e0b\u9879\uff0c\u4ee5\u514d\u9000\u8ba2\u94fe\u63a5\u3001\u8de8\u57df\u3001\u90ae\u4ef6\u91cc\u6307\u5411\u672c\u5730\u8fd4\u56de\u9519\u8bef\u5730\u5740\uff1a"));
bodyChildren.push(bullet(".env \u7684 PUBLIC_ORIGIN \u6539\u4e3a\u771f\u5b9e\u8bbf\u95ee URL\uff0c\u4f8b\u5982 https://leads.example.com"));
bodyChildren.push(bullet(".env \u7684 MEDBOT_PUBLIC_URL \u6539\u4e3a\u540c\u4e00\u4e2a URL\uff08\u9000\u8ba2\u94fe\u63a5\u4f1a\u62fc\u63a5\u5230\u90ae\u4ef6\u6b63\u6587\uff09"));
bodyChildren.push(bullet("HTTPS \u7ec8\u7ed3\u63a8\u8350\u7531\u4e0a\u6e38\u53cd\u5411\u4ee3\u7406\uff08Nginx / Caddy / \u8d1f\u8f7d\u5747\u8861\uff09\u63d0\u4f9b\uff0c\u8bc1\u4e66\u4e0d\u653e\u5728\u5bb9\u5668\u91cc\u4ee5\u4fbf\u8f6e\u6362"));

// ── Chapter 4 ─────────────────────────────
bodyChildren.push(h1("4. \u79bb\u7ebf\u73af\u5883\u90e8\u7f72", { pageBreakBefore: true }));

bodyChildren.push(h2("4.1 \u9002\u7528\u573a\u666f"));
bodyChildren.push(body("\u9762\u5411\u5ba2\u6237\u5185\u7f51\u4e0d\u53ef\u8bbf\u95ee\u516c\u5171\u955c\u50cf\u4ed3\u5e93\u4e0e npm/PyPI \u7684\u5b9e\u65bd\u573a\u666f\u3002\u6574\u4f53\u601d\u8def\uff1a\u5728\u6709\u7f51\u7684\u6784\u5efa\u673a\u4e0a\u5236\u4f5c\u4ea4\u4ed8\u5305\uff08tar.gz\uff09\u2192 \u62f7\u8d1d\u5230\u5ba2\u6237\u670d\u52a1\u5668\u2192 \u8fd0\u884c\u4e00\u952e\u5b89\u88c5\u811a\u672c\u3002"));

bodyChildren.push(h2("4.2 \u6784\u5efa\u4ea4\u4ed8\u5305\uff08\u6784\u5efa\u673a\u4e0a\uff09"));
bodyChildren.push(body("\u5728\u4e00\u53f0\u8054\u7f51\u3001\u80fd\u8bbf\u95ee Docker Hub \u7684\u673a\u5668\u4e0a\uff08\u5f80\u5f80\u662f CI \u670d\u52a1\u5668\u6216\u5b9e\u65bd\u5de5\u7a0b\u5e08\u672c\u673a\uff09\u8fd0\u884c\uff1a"));
bodyChildren.push(...codeBlock([
  "$ ./scripts/make-offline-package.sh 1.0.0",
  "==> \u6784\u5efa\u7248\u672c: 1.0.0",
  "==> [1/4] \u6784\u5efa\u955c\u50cf",
  "==> [2/4] \u7ec4\u7ec7\u4ea4\u4ed8\u76ee\u5f55: dist/ai_lead_gen-offline-1.0.0",
  "==> [3/4] \u5bfc\u51fa\u955c\u50cf (docker save) + gzip",
  "==> [4/4] \u8ba1\u7b97 SHA256 \u4e0e MANIFEST",
  "\u751f\u6210\u4ea4\u4ed8\u5305: dist/ai_lead_gen-offline-1.0.0.tar.gz",
]));
bodyChildren.push(body("\u4ea4\u4ed8\u5305\u542b\u6709\uff1a"));
bodyChildren.push(bullet("\u4e09\u4e2a\u670d\u52a1\u955c\u50cf\uff08docker save \u5bfc\u51fa\u540e gzip \u6253\u5305\u4e3a images.tar.gz\uff09"));
bodyChildren.push(bullet("docker-compose.deploy.yml\uff08\u96b6\u7ebf\u7248 compose\uff0c\u4e0d\u53d1\u8d77\u955c\u50cf\u62c9\u53d6\uff09"));
bodyChildren.push(bullet(".env \u6a21\u677f\uff08IMAGE_TAG \u5df2\u586b\u5165\uff0c\u5bc6\u94a5\u7559\u7a7a\u4f9b\u73b0\u573a\u586b\u5199\uff09"));
bodyChildren.push(bullet("preflight.sh\u3001smoke-test.sh\u3001install-offline.sh \u811a\u672c"));
bodyChildren.push(bullet("MANIFEST.txt \u4ea4\u4ed8\u6e05\u5355\u3001SHA256SUMS \u6821\u9a8c\u548c"));
bodyChildren.push(bullet("\u5b89\u88c5\u624b\u518c.md\uff08\u672c\u6587\u6863\u7684\u6c89\u6dc0\u7248\u672c\uff09"));

bodyChildren.push(note("\u4ea4\u4ed8\u5305\u4e0d\u542b\u4efb\u4f55\u5927\u6a21\u578b API Key\u3001\u4f01\u4e1a\u90ae\u7bb1\u5bc6\u7801\uff0c\u8fd9\u4e9b\u90fd\u9700\u8981\u73b0\u573a\u5b9e\u65bd\u8005\u5728\u5ba2\u6237\u73af\u5883\u4e2d\u586b\u5165\u3002"));

bodyChildren.push(h2("4.3 \u62f7\u8d1d\u5230\u5ba2\u6237\u670d\u52a1\u5668"));
bodyChildren.push(body("\u63a8\u8350\u7684\u62f7\u8d1d\u65b9\u5f0f\uff08\u4ece\u4e25\u5230\u5bbd\uff09\uff1a"));
bodyChildren.push(bullet("\u8131\u673a\u5e73\u53f0\uff0f\u8de8\u7f51\u95f8\u4f20\u8f93\u5e73\u53f0\uff08\u91d1\u878d\u3001\u519b\u5de5\u3001\u91cd\u8981\u533b\u9662\uff09"));
bodyChildren.push(bullet("\u52a0\u5bc6 U \u76d8\u73b0\u573a\u62f7\u8d1d\uff08\u591a\u6570\u533b\u9662\u4e0e\u4f01\u4e1a IT\uff09"));
bodyChildren.push(bullet("\u4e34\u65f6\u4f01\u4e1a\u4e91\u76d8\u4e0b\u8f7d\uff08\u4ec5\u9650\u5141\u8bb8\u8bbf\u95ee\u4f01\u4e1a\u4e91\u7684\u73af\u5883\uff09"));
bodyChildren.push(body("\u590d\u5236\u540e\u5fc5\u987b\u4f7f\u7528 SHA256 \u6838\u5bf9\u4ea4\u4ed8\u5305\uff1a"));
bodyChildren.push(...codeBlock([
  "$ shasum -a 256 ai_lead_gen-offline-1.0.0.tar.gz",
  "<\u8f93\u51fa\u7684 hash> \u9700\u4e0e\u6784\u5efa\u65b9\u63d0\u4f9b\u7684 SHA256 \u4e00\u81f4",
]));

bodyChildren.push(h2("4.4 \u73b0\u573a\u5b89\u88c5"));
bodyChildren.push(...codeBlock([
  "$ tar xzf ai_lead_gen-offline-1.0.0.tar.gz",
  "$ cd ai_lead_gen-offline-1.0.0",
  "$ ./install-offline.sh",
]));
bodyChildren.push(body("install-offline.sh \u7684\u5b8c\u6574\u6d41\u7a0b\uff08\u5171 6 \u6b65\uff09\uff1a"));
bodyChildren.push(bullet("\u7b2c 1 \u6b65\uff1a\u8c03\u7528 preflight.sh \u6267\u884c\u73af\u5883\u9884\u68c0"));
bodyChildren.push(bullet("\u7b2c 2 \u6b65\uff1ashasum -c SHA256SUMS \u6838\u9a8c\u4ea4\u4ed8\u5305\u5b8c\u6574\u6027"));
bodyChildren.push(bullet("\u7b2c 3 \u6b65\uff1agzip -dc images.tar.gz | docker load \u5bfc\u5165\u955c\u50cf"));
bodyChildren.push(bullet("\u7b2c 4 \u6b65\uff1a\u751f\u6210\u6216\u8bfb\u53d6 agent/.env\uff1bautogen MEDBOT_SERVICE_TOKEN \u4e0e AGENT_TOKEN"));
bodyChildren.push(bullet("\u7b2c 5 \u6b65\uff1adocker compose -f docker-compose.deploy.yml up -d \u542f\u52a8"));
bodyChildren.push(bullet("\u7b2c 6 \u6b65\uff1a\u8c03\u7528 smoke-test.sh \u9a8c\u8bc1\u5173\u952e\u94fe\u8def"));

bodyChildren.push(h2("4.5 \u73b0\u573a\u586b\u5199\u5bc6\u94a5"));
bodyChildren.push(body("\u811a\u672c\u8dd1\u5b8c\u540e\uff0c\u4ecd\u9700\u624b\u52a8\u8865\u9f50\u4e09\u7c7b\u4fe1\u606f\uff0c\u4ee5\u4fbf AI \u4e0e\u90ae\u4ef6\u529f\u80fd\u53ef\u7528\uff1a"));
bodyChildren.push(dataTable(
  ["\u7c7b\u522b", "\u6587\u4ef6", "\u5b57\u6bb5", "\u8bf4\u660e"],
  [
    ["\u5927\u6a21\u578b", "agent/.env", "OPENAI_API_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY", "\u4e09\u8005\u9009\u5176\u4e00\uff0c\u540c\u65f6\u8bbe\u7f6e PI_PROVIDER \u4e0e PI_MODEL"],
    ["\u90ae\u7bb1", ".env", "MEDBOT_EMAIL_USER / MEDBOT_EMAIL_PASSWORD", "\u4f01\u4e1a Exchange EWS \u8d26\u53f7\u4e0e\u5bc6\u7801"],
    ["\u516c\u7f51\u57df\u540d", ".env", "PUBLIC_ORIGIN / MEDBOT_PUBLIC_URL", "\u9000\u8ba2\u94fe\u63a5\u9700\u8981\uff0c\u672a\u8bbe\u7f6e\u65f6\u9000\u8ba2\u4f1a\u6307\u5411 localhost"],
  ],
  [1800, 1500, 3300, 3506],
));

bodyChildren.push(new Paragraph({ spacing: { after: 120 } }));
bodyChildren.push(body("\u4fee\u6539\u540e\uff0c\u91cd\u542f\u5bf9\u5e94\u5bb9\u5668\uff1a"));
bodyChildren.push(...codeBlock([
  "$ docker compose -f docker-compose.deploy.yml restart agent backend",
]));

// ── Chapter 5 ─────────────────────────────
bodyChildren.push(h1("5. \u914d\u7f6e\u8bf4\u660e", { pageBreakBefore: true }));

bodyChildren.push(h2("5.1 .env\uff08\u540e\u7aef\u4e0e\u90e8\u7f72\u4e3b\u63a7\uff09"));
bodyChildren.push(dataTable(
  ["\u5b57\u6bb5", "\u9ed8\u8ba4\u503c", "\u8bf4\u660e"],
  [
    ["FRONTEND_PORT", "5173", "\u4e3b\u673a\u5916\u66b4\u9732\u7684\u524d\u7aef\u7aef\u53e3"],
    ["BACKEND_PORT", "8000", "\u4e3b\u673a\u5916\u66b4\u9732\u7684\u540e\u7aef\u7aef\u53e3"],
    ["PUBLIC_ORIGIN", "http://localhost:5173", "\u524d\u7aef\u516c\u7f51\u8bbf\u95ee\u5730\u5740\uff0c\u4f5c\u4e3a CORS \u6e90"],
    ["MEDBOT_DB_PATH", "/data/medbot.db", "\u5bb9\u5668\u5185 SQLite \u8def\u5f84\uff08\u6620\u5c04\u5230 medbot-data \u5377\uff09"],
    ["AGENT_BASE_URL", "http://agent:8011", "backend \u8c03\u7528 agent \u7684\u5185\u90e8\u5730\u5740"],
    ["AGENT_ENV_PATH", "/app/agent/.env", "Web \u7aef\u4fdd\u5b58 Agent \u914d\u7f6e\u65f6\u5199\u5165\u7684\u8def\u5f84"],
    ["AGENT_TOKEN", "(\u81ea\u52a8\u751f\u6210)", "backend \u2194 agent \u5185\u90e8 Bearer \u4ee4\u724c\uff0c\u4e24\u8fb9\u5fc5\u987b\u4e00\u81f4"],
    ["MEDBOT_SERVICE_TOKEN", "(\u81ea\u52a8\u751f\u6210)", "agent \u8bbf\u95ee\u7984\u540e\u7aef\u7684\u670d\u52a1\u4ee4\u724c\uff0c\u540c\u6b65\u5230 agent/.env"],
    ["MEDBOT_PUBLIC_URL", "(\u7a7a)", "\u9000\u8ba2\u94fe\u63a5\u4f7f\u7528\u7684\u516c\u7f51\u5730\u5740"],
    ["MEDBOT_EMAIL_SERVER", "mail.microport.com.cn", "Exchange EWS \u670d\u52a1\u5668"],
    ["MEDBOT_EMAIL_USER", "(\u7a7a)", "EWS \u8d26\u53f7"],
    ["MEDBOT_EMAIL_PASSWORD", "(\u7a7a)", "EWS \u5bc6\u7801\uff0c\u52a0\u5bc6\u540e\u5165\u5e93"],
    ["VITE_API_BASE_URL", "/api", "\u524d\u7aef\u6784\u5efa\u65f6\u70d8\u5165\u7684 API \u524d\u7f00\uff0c\u9ed8\u8ba4\u540c\u6e90\u53cd\u4ee3"],
  ],
  [3000, 2400, 4706],
));

bodyChildren.push(h2("5.2 agent/.env\uff08Pi Sidecar\uff09"));
bodyChildren.push(dataTable(
  ["\u5b57\u6bb5", "\u9ed8\u8ba4\u503c", "\u8bf4\u660e"],
  [
    ["PI_PROVIDER", "openai", "openai / deepseek / bailian \u4e09\u9009\u4e00"],
    ["PI_MODEL", "gpt-5-mini", "\u6a21\u578b id\uff0c\u9700\u4e0e provider \u5339\u914d"],
    ["OPENAI_API_KEY", "(\u7a7a)", "OpenAI \u6a21\u578b key\uff0cPI_PROVIDER=openai \u65f6\u5fc5\u586b"],
    ["DEEPSEEK_API_KEY", "(\u7a7a)", "DeepSeek key\uff0cPI_PROVIDER=deepseek \u65f6\u5fc5\u586b"],
    ["DASHSCOPE_API_KEY", "(\u7a7a)", "\u963f\u91cc\u4e91\u767e\u70bc / DashScope key\uff0cPI_PROVIDER=bailian \u65f6\u5fc5\u586b"],
    ["BACKEND_BASE_URL", "http://backend:8000", "agent \u8c03\u7528 backend \u7684\u5730\u5740"],
    ["BACKEND_SERVICE_TOKEN", "(\u540c MEDBOT_SERVICE_TOKEN)", "X-Service-Token \u8bf7\u6c42\u5934\u4f7f\u7528"],
    ["AGENT_HOST", "0.0.0.0", "sidecar \u76d1\u542c\u5730\u5740\uff08\u5bb9\u5668\u5185\uff09"],
    ["AGENT_PORT", "8011", "sidecar \u76d1\u542c\u7aef\u53e3"],
    ["AGENT_CORS_ORIGIN", "http://localhost:5173", "\u5141\u8bb8\u8bbf\u95ee sidecar \u7684\u6e90\uff0c\u751f\u4ea7\u73af\u5883\u540c PUBLIC_ORIGIN"],
    ["AGENT_TOKEN", "(\u540c\u4e3b .env)", "backend \u8c03\u7528 sidecar \u7684 Bearer \u4ee4\u724c"],
    ["AGENT_MAX_SESSIONS", "20", "\u7f13\u5b58\u7684\u4f1a\u8bdd\u4e0a\u9650"],
    ["AGENT_SESSION_IDLE_MS", "1800000", "\u4f1a\u8bdd\u7a7a\u95f2\u8d85\u65f6\uff0c\u9ed8\u8ba4 30 \u5206\u949f"],
  ],
  [3000, 2800, 4306],
));

bodyChildren.push(note("Sidecar \u4ec5\u5728\u542f\u52a8\u65f6\u8bfb\u53d6 .env\uff0c\u4e0d\u70ed\u91cd\u8f7d\u3002\u4fee\u6539 agent/.env \u540e\u52a1\u5fc5\u91cd\u542f agent \u5bb9\u5668\u3002Web \u9762\u677f\u4e0a\u5728\u300cAgent \u8bbe\u7f6e\u300d\u4fdd\u5b58\u540e\u540c\u6837\u9700\u8981\u91cd\u542f\uff0c\u5219\u65b0\u914d\u7f6e\u624d\u4f1a\u751f\u6548\u3002"));

bodyChildren.push(h2("5.3 \u4e09\u79cd LLM Provider \u9009\u62e9\u5efa\u8bae"));
bodyChildren.push(dataTable(
  ["Provider", "\u5e94\u7528\u573a\u666f", "\u4f18\u52bf", "\u9650\u5236"],
  [
    ["openai", "\u9ed8\u8ba4\u3001\u6f14\u793a\u3001\u6d77\u5916\u90e8\u7f72", "\u751f\u6001\u6210\u719f\u3001\u80fd\u529b\u5168\u9762", "\u56fd\u5185\u76f4\u8054\u9700\u8d70\u4ee3\u7406"],
    ["deepseek", "\u6027\u4ef7\u6bd4\u4f18\u5148", "\u4ef7\u683c\u4f4e\u3001\u4e2d\u6587\u8868\u73b0\u597d", "\u591a\u6b65\u9aa4 tool use \u7a33\u5b9a\u6027\u9700\u9a8c\u8bc1"],
    ["bailian", "\u56fd\u5185\u4f01\u4e1a\u3001\u5408\u89c4\u90e8\u7f72", "\u963f\u91cc\u4e91\u767e\u70bc\u3001\u56fd\u5185\u673a\u623f\u53ef\u8054", "\u9700\u5728\u63a7\u5236\u53f0\u5f00\u901a\u5bf9\u5e94\u6a21\u578b"],
  ],
  [1800, 2500, 2700, 3106],
));

// ── Chapter 6 ─────────────────────────────
bodyChildren.push(h1("6. \u90e8\u7f72\u540e\u9a8c\u8bc1\u4e0e\u70df\u96fe\u6d4b\u8bd5", { pageBreakBefore: true }));

bodyChildren.push(h2("6.1 \u70df\u96fe\u811a\u672c"));
bodyChildren.push(body("\u4ed3\u5e93\u63d0\u4f9b scripts/smoke-test.sh \u4f5c\u4e3a\u4ea4\u4ed8\u524d\u7684\u5173\u952e\u94fe\u8def\u9a8c\u8bc1\u3002\u8054\u7f51\u3001\u79bb\u7ebf\u4e24\u79cd\u573a\u666f\u90fd\u5e94\u8be5\u8dd1\u3002"));
bodyChildren.push(...codeBlock([
  "$ ./scripts/smoke-test.sh 5173 8000",
  "[\u7b49\u5f85\u670d\u52a1\u5c31\u7eea]",
  "[\u5173\u952e\u94fe\u8def\u68c0\u67e5]",
  "  \u2713 \u540e\u7aef /health \u6b63\u5e38",
  "  \u2713 \u524d\u7aef\u9996\u9875\u53ef\u8bbf\u95ee (HTTP 200)",
  "  \u2713 \u524d\u7aef /api \u53cd\u4ee3\u5230\u540e\u7aef\u6b63\u5e38",
  "  \u2713 \u9ed8\u8ba4\u7ba1\u7406\u5458\u80fd\u767b\u5f55 (HTTP 200)",
  "\u2705 \u70df\u96fe\u6d4b\u8bd5\u5168\u90e8\u901a\u8fc7",
]));

bodyChildren.push(h2("6.2 \u624b\u52a8\u9a8c\u8bc1\u6e05\u5355"));
bodyChildren.push(body("\u70df\u96fe\u811a\u672c\u53ea\u68c0\u67e5\u8054\u8c03\u4e0e\u9274\u6743\u3002\u4ea4\u4ed8\u524d\u8fd8\u5e94\u624b\u52a8\u8dd1\u4e00\u8f6e\u4e1a\u52a1\u9a8c\u8bc1\uff1a"));
bodyChildren.push(bullet("\u767b\u5f55 admin/admin123 \u540e\u80fd\u8fdb\u5165\u4fee\u6539\u5bc6\u7801\u9875\uff0c\u4fee\u6539\u540e\u80fd\u91cd\u65b0\u767b\u5f55"));
bodyChildren.push(bullet("\u300c\u4ea7\u54c1\u753b\u50cf\u300d\u9875\u80fd\u8bfb\u51fa SkyWalker TKA \u7684\u5b9a\u4f4d\u5173\u952e\u8bcd"));
bodyChildren.push(bullet("\u300c\u5b9e\u65f6\u641c\u7d22\u300d\u586b\u5165\u67d0\u4e2a\u5177\u4f53\u56fd\u5bb6\uff0c\u80fd\u8fd4\u56de\u5e26\u90ae\u7bb1\u7684\u4e0d\u5c11\u4e8e 1 \u6761\u7684\u7ebf\u7d22"));
bodyChildren.push(bullet("\u300cAgent \u9762\u677f\u300d\u8f93\u5165\u4efb\u4e00\u95ee\u9898\uff0c\u80fd\u770b\u5230\u6a21\u578b\u589e\u91cf\u8f93\u51fa\uff0c\u4e14\u4e0d\u62a5\u300c\u672a\u914d\u7f6e API Key\u300d"));
bodyChildren.push(bullet("\u300c\u8bbe\u7f6e \u2192 \u540c\u6b65\u300d\u53ef\u770b\u5230\u53d1\u9001\u961f\u5217\u72b6\u6001\uff08\u6392\u961f\u4e2d / \u4eca\u65e5\u5df2\u53d1 / \u4e0a\u9650\uff09"));
bodyChildren.push(bullet("\u300c\u7528\u6237\u4e0e\u6743\u9650 \u2192 \u5ba1\u8ba1\u65e5\u5fd7\u300d\u80fd\u770b\u5230\u521a\u624d\u767b\u5f55\u4e8b\u4ef6"));

bodyChildren.push(h2("6.3 \u6839\u636e\u72b6\u6001\u5224\u65ad\u5176\u96be\u70b9"));
bodyChildren.push(dataTable(
  ["\u73b0\u8c61", "\u53ef\u80fd\u539f\u56e0", "\u5904\u7406"],
  [
    ["frontend \u4e0d\u4e3a healthy", "Nginx \u672a\u80fd\u8bbf\u95ee backend \u53cd\u4ee3", "\u68c0\u67e5 backend \u662f\u5426 healthy\uff0c\u67e5 frontend \u5bb9\u5668\u65e5\u5fd7"],
    ["backend healthy \u4f46 /api 404", "VITE_API_BASE_URL \u4e0d\u662f /api", "\u91cd\u65b0\u6784\u5efa frontend \u5e76\u4f20\u9012 VITE_API_BASE_URL=/api"],
    ["agent healthy \u4f46\u5bf9\u8bdd\u62a5\u672a\u914d\u7f6e", "agent/.env \u672a\u586b key \u6216\u672a\u91cd\u542f", "\u586b\u5b8c key \u540e docker compose restart agent"],
    ["agent \u5bf9\u8bdd 401", "AGENT_TOKEN \u4e24\u8fb9\u4e0d\u4e00\u81f4", "\u91cd\u8dd1 deploy.sh \u6216\u624b\u52a8\u540c\u6b65\u4e24\u4e2a .env"],
    ["agent \u5bf9\u540e\u7aef 401", "MEDBOT_SERVICE_TOKEN \u4e0e BACKEND_SERVICE_TOKEN \u4e0d\u4e00\u81f4", "\u540c\u4e0a\uff0c\u91cd\u8dd1\u811a\u672c\u540c\u6b65"],
  ],
  [2500, 3000, 4606],
));

// ── Chapter 7 ─────────────────────────────
bodyChildren.push(h1("7. \u5347\u7ea7\u4e0e\u56de\u6eda", { pageBreakBefore: true }));

bodyChildren.push(h2("7.1 \u5347\u7ea7\u524d\u5907\u4efd\uff08\u5fc5\u9009\uff09"));
bodyChildren.push(body("SQLite \u6570\u636e\u5e93\u662f\u552f\u4e00\u7684\u72b6\u6001\u4ee3\u7406\u3002\u5347\u7ea7\u524d\u52a1\u5fc5\u5907\u4efd medbot-data \u5377\uff1a"));
bodyChildren.push(...codeBlock([
  "$ docker run --rm \\",
  "    -v medbot-data:/data -v \"$PWD\":/backup alpine \\",
  "    tar czf /backup/medbot-data-$(date +%F).tar.gz -C /data .",
]));
bodyChildren.push(body("\u5907\u4efd\u6587\u4ef6\u4f1a\u751f\u6210\u5728\u5f53\u524d\u76ee\u5f55\uff0c\u5efa\u8bae\u8f6c\u5b58\u5230\u4e0e\u670d\u52a1\u5668\u5206\u79bb\u7684\u4f4d\u7f6e\u3002"));

bodyChildren.push(h2("7.2 \u8054\u7f51\u5347\u7ea7"));
bodyChildren.push(...codeBlock([
  "$ cd ai_lead_gen",
  "$ git pull",
  "$ ./scripts/deploy.sh   # \u590d\u7528\u73b0\u6709 .env\uff0c\u4ec5\u91cd\u65b0\u6784\u5efa\u955c\u50cf",
]));
bodyChildren.push(body("deploy.sh \u4f1a\u5728\u68c0\u6d4b\u5230 .env \u4e0e agent/.env \u5b58\u5728\u65f6\u8df3\u8fc7\u521b\u5efa\u3001\u4ec5\u8865\u5168\u7f3a\u5931\u5b57\u6bb5\uff0c\u4fdd\u62a4\u73b0\u6709\u5bc6\u94a5\u4e0d\u88ab\u8986\u76d6\u3002"));

bodyChildren.push(h2("7.3 \u79bb\u7ebf\u5347\u7ea7"));
bodyChildren.push(...codeBlock([
  "$ tar xzf ai_lead_gen-offline-1.1.0.tar.gz",
  "$ cd ai_lead_gen-offline-1.1.0",
  "# \u590d\u7528\u65e7\u7248\u672c\u7684 .env \u4e0e agent/.env",
  "$ cp ../ai_lead_gen-offline-1.0.0/.env .",
  "$ cp ../ai_lead_gen-offline-1.0.0/agent/.env agent/.env",
  "$ ./install-offline.sh",
]));
bodyChildren.push(body("\u540e\u7aef\u542f\u52a8\u65f6\u4f1a\u81ea\u52a8\u6267\u884c\u6570\u636e\u5e93\u8fc1\u79fb\uff08\u5411\u540e\u517c\u5bb9\uff09\u3002\u5347\u7ea7\u540e\u52a1\u5fc5\u8dd1\u4e00\u904d smoke-test.sh \u786e\u8ba4\u6b63\u5e38\u3002"));

bodyChildren.push(h2("7.4 \u56de\u6eda"));
bodyChildren.push(body("\u4e24\u79cd\u573a\u666f\u7684\u56de\u6eda\u8def\u5f84\u4e0d\u540c\u3002\u5347\u7ea7\u540e\u53d1\u73b0\u4e25\u91cd\u95ee\u9898\u65f6\uff1a"));
bodyChildren.push(bullet("\u8054\u7f51\u573a\u666f\uff1agit checkout <\u4e0a\u4e00\u4e2a tag> \u540e\u91cd\u8dd1 deploy.sh\u3002\u82e5 schema \u53d8\u52a8\u4e0d\u517c\u5bb9\uff0c\u5148\u7528\u5907\u4efd\u8986\u76d6 medbot-data \u5377\u3002"));
bodyChildren.push(bullet("\u79bb\u7ebf\u573a\u666f\uff1a\u4fdd\u7559\u4e0a\u4e00\u4e2a\u7248\u672c\u7684\u955c\u50cf\u672c\u5730\u4e0d\u8981\u522a\uff0c\u4fee\u6539 .env \u7684 IMAGE_TAG \u540e\u8df3\u8fc7 docker load \u76f4\u63a5 docker compose -f docker-compose.deploy.yml up -d\u3002"));

bodyChildren.push(warn("\u4e25\u7981\u5728\u6ca1\u6709\u6570\u636e\u5907\u4efd\u7684\u60c5\u51b5\u4e0b\u6267\u884c docker compose down -v \u6216\u624b\u52a8\u5220\u9664 medbot-data \u5377 \u2014\u2014 \u6240\u6709\u7ebf\u7d22\u3001\u7528\u6237\u3001\u5ba1\u8ba1\u65e5\u5fd7\u4f1a\u5168\u90e8\u4e22\u5931\u3002"));

// ── Chapter 8 ─────────────────────────────
bodyChildren.push(h1("8. \u65e5\u5e38\u8fd0\u7ef4", { pageBreakBefore: true }));

bodyChildren.push(h2("8.1 \u5e38\u7528\u547d\u4ee4"));
bodyChildren.push(dataTable(
  ["\u573a\u666f", "\u547d\u4ee4"],
  [
    ["\u67e5\u770b\u72b6\u6001", "docker compose ps"],
    ["\u5b9e\u65f6\u65e5\u5fd7", "docker compose logs -f backend agent frontend"],
    ["\u67e5\u770b\u5355\u5bb9\u5668\u8fd1 200 \u884c", "docker compose logs --tail=200 backend"],
    ["\u91cd\u542f agent", "docker compose restart agent"],
    ["\u91cd\u542f\u6240\u6709", "docker compose restart"],
    ["\u505c\u6b62\uff08\u4fdd\u7559\u6570\u636e\u5377\uff09", "docker compose down"],
    ["\u91cd\u65b0\u6784\u5efa\u4e0d\u542f\u52a8", "docker compose build --no-cache"],
    ["\u91cd\u65b0\u542f\u52a8\u5305\u542b\u65b0\u955c\u50cf", "docker compose up -d --build"],
    ["\u8fdb\u5165\u540e\u7aef\u5bb9\u5668", "docker compose exec backend bash"],
    ["\u67e5\u770b\u955c\u50cf\u5360\u7528", "docker system df"],
  ],
  [3500, 6606],
));

bodyChildren.push(h2("8.2 \u65e5\u5fd7\u4e0e\u76d1\u63a7"));
bodyChildren.push(body("\u4e09\u4e2a\u5bb9\u5668\u90fd\u4f7f\u7528\u6807\u51c6\u8f93\u51fa\uff0cdocker compose logs \u53ef\u4ee5\u76f4\u63a5\u67e5\u770b\uff1b\u5982\u9700\u96c6\u4e2d\u8d70\u5ba2\u6237 ELK / Loki\uff0c\u53ef\u5728 docker-compose \u91cc\u52a0\u5165 logging driver\u3002\u5173\u952e\u544a\u8b66\u70b9\uff1a"));
bodyChildren.push(bullet("backend \u6301\u7eed\u51fa\u73b0 500\uff1a\u770b stderr\uff0c\u591a\u4e3a\u6570\u636e\u5e93\u9501\u5b9a\u6216\u5916\u90e8\u4f9d\u8d56\u5931\u8d25"));
bodyChildren.push(bullet("agent \u6301\u7eed\u51fa\u73b0 401/429\uff1a\u68c0\u67e5 LLM Key \u989d\u5ea6\u4e0e\u4ee4\u724c\u4e00\u81f4\u6027"));
bodyChildren.push(bullet("\u90ae\u4ef6\u53d1\u9001 worker \u5805\u7965\u72b6\u6001\uff1a\u67e5\u770b GET /campaigns/queue \u8fd4\u56de\u7684\u961f\u5217\u662f\u5426\u88ab\u8282\u6d41\u9501\u6b7b"));

bodyChildren.push(h2("8.3 \u6570\u636e\u5907\u4efd\u4e0e\u8f6e\u8f6c"));
bodyChildren.push(body("\u5efa\u8bae\u9519\u5f00\u4e1a\u52a1\u9ad8\u5cf0\u6bcf\u65e5\u5b9a\u65f6\u5907\u4efd medbot-data \u5377\uff1a"));
bodyChildren.push(...codeBlock([
  "# /etc/cron.daily/medbot-backup",
  "#!/usr/bin/env bash",
  "set -e",
  "BACKUP_DIR=/var/backups/medbot",
  "mkdir -p \"$BACKUP_DIR\"",
  "docker run --rm \\",
  "  -v medbot-data:/data -v \"$BACKUP_DIR\":/backup alpine \\",
  "  tar czf /backup/medbot-data-$(date +%F).tar.gz -C /data .",
  "find \"$BACKUP_DIR\" -name 'medbot-data-*.tar.gz' -mtime +30 -delete",
]));

bodyChildren.push(h2("8.4 \u5bc6\u7801\u4e0e\u4ee4\u724c\u8f6e\u6362"));
bodyChildren.push(bullet("\u7ba1\u7406\u5458\u5bc6\u7801\uff1a\u4ee5 admin \u767b\u5f55 \u2192 \u7528\u6237\u83dc\u5355 \u2192 \u4fee\u6539\u5bc6\u7801"));
bodyChildren.push(bullet("MEDBOT_AUTH_SECRET\uff1a\u9ed8\u8ba4\u81ea\u52a8\u751f\u6210\u3002\u624b\u52a8\u8f6e\u6362\u4f1a\u4f7f\u6240\u6709\u7528\u6237\u5e26\u9274\u6743\u73b0\u6709 token \u5931\u6548\uff0c\u9700\u91cd\u65b0\u767b\u5f55"));
bodyChildren.push(bullet("AGENT_TOKEN / MEDBOT_SERVICE_TOKEN\uff1a\u5982\u9700\u8f6e\u6362\uff0c\u624b\u5de5\u91cd\u65b0\u751f\u6210\u540c\u4e00\u4e32\u5e76\u540c\u6b65\u5230\u4e24\u4e2a .env \u540e\u91cd\u542f\u4e24\u4e2a\u5bb9\u5668"));
bodyChildren.push(bullet("LLM Key\uff1a\u4ec5\u4fee\u6539 agent/.env \u540e\u91cd\u542f agent\uff1bWeb \u9762\u677f\u4e5f\u53ef\u4ee5\u4fdd\u5b58\uff0c\u4f46\u4ecd\u9700\u91cd\u542f"));

// ── Chapter 9 ─────────────────────────────
bodyChildren.push(h1("9. \u5e38\u89c1\u95ee\u9898\u6392\u67e5", { pageBreakBefore: true }));

bodyChildren.push(h2("9.1 \u542f\u52a8\u9636\u6bb5"));
bodyChildren.push(dataTable(
  ["\u8868\u73b0", "\u53ef\u80fd\u539f\u56e0", "\u5904\u7406"],
  [
    ["deploy.sh \u62a5 docker compose \u7248\u672c\u4e0d\u591f", "\u4ec5\u5b89\u88c5\u4e86 docker-compose v1", "\u5347\u7ea7\u5230 v2 \u63d2\u4ef6\uff0capt install docker-compose-plugin"],
    ["\u63d0\u793a\u7aef\u53e3\u88ab\u5360\u7528", "\u672c\u673a\u5df2\u6709 Nginx / \u5176\u4ed6\u670d\u52a1", "\u4fee\u6539 .env \u7684 FRONTEND_PORT/BACKEND_PORT \u540e\u91cd\u88c5"],
    ["frontend healthcheck \u8d85\u65f6", "Nginx \u542f\u52a8\u4e2d\u4f46 backend \u672a\u5c31\u7eea", "\u7b49 30\u201360 \u79d2 backend healthy \u540e\u4f1a\u81ea\u4fee\u590d"],
    ["docker load \u62a5 no space left", "\u78c1\u76d8\u4e0d\u8db3", "\u6e05\u7406 /var/lib/docker\uff0cdocker system prune -a"],
    ["\u670d\u52a1\u62c9\u4e0d\u8d77\u53c8\u770b\u4e0d\u5230\u65e5\u5fd7", "docker daemon \u672a\u8fd0\u884c", "systemctl status docker\uff1bDocker Desktop \u9700\u624b\u52a8 open"],
  ],
  [3500, 3000, 3606],
));

bodyChildren.push(h2("9.2 \u4f7f\u7528\u9636\u6bb5"));
bodyChildren.push(dataTable(
  ["\u8868\u73b0", "\u53ef\u80fd\u539f\u56e0", "\u5904\u7406"],
  [
    ["Agent \u63d0\u793a\u300c\u672a\u914d\u7f6e API Key\u300d", "agent/.env \u672a\u586b key \u6216\u586b\u540e\u672a\u91cd\u542f", "\u586b\u5165 key \u540e docker compose restart agent"],
    ["Agent \u62a5 model not found", "PI_MODEL \u4e0e provider \u4e0d\u5339\u914d", "\u6309 5.2 \u8868\u8c03\u6574 PI_PROVIDER \u4e0e PI_MODEL"],
    ["\u5b9e\u65f6\u641c\u7d22\u603b\u8fd4\u56de 0 \u6761", "\u51fa\u7ad9\u88ab\u62e6\u6216\u76ee\u6807\u592a\u5bbd\u6cdb", "\u68c0\u67e5 backend \u51fa\u7ad9\u4ee3\u7406\uff0c\u6216\u6307\u5b9a\u66f4\u5177\u4f53\u7684\u56fd\u5bb6\u5173\u952e\u8bcd"],
    ["\u90ae\u4ef6\u53d1\u4e0d\u51fa\u53bb", "EWS \u8d26\u5bc6\u9519\u8bef / \u4f01\u4e1a\u90ae\u7bb1\u62d2\u5916\u8054", "\u68c0\u67e5\u300c\u8bbe\u7f6e \u2192 \u90ae\u7bb1\u300d\u8fde\u63a5\u72b6\u6001\uff0c\u67e5\u4f01\u4e1a IT \u662f\u5426\u5141\u8bb8 EWS"],
    ["\u53d1\u9001\u961f\u5217\u4e00\u76f4\u6392\u961f", "\u53d1\u9001\u8282\u6d41\u9501\u6b7b\u6216\u5168\u90e8\u547d\u4e2d\u62b5\u5236\u540d\u5355", "\u300c\u8bbe\u7f6e \u2192 \u540c\u6b65\u300d\u67e5\u770b\u53d1\u9001\u53c2\u6570\u4e0e\u88ab\u8df3\u8fc7\u539f\u56e0"],
    ["\u9000\u8ba2\u94fe\u63a5 404", "MEDBOT_PUBLIC_URL \u672a\u8bbe\u7f6e", "\u8bbe\u7f6e\u4e3a\u5916\u90e8\u53ef\u8bbf\u95ee\u7684 backend \u516c\u7f51\u5730\u5740"],
    ["\u767b\u5f55\u88ab\u62d2 (HTTP 429)", "15 \u5206\u949f\u5185\u5931\u8d25 5 \u6b21\u88ab\u9501\u5b9a", "\u7b49 15 \u5206\u949f\u6216\u6e05 backend \u5185\u5b58\u4e2d\u7684\u9501\u5b9a\u8868"],
  ],
  [3500, 3000, 3606],
));

bodyChildren.push(h2("9.3 \u6027\u80fd\u4e0e\u8d44\u6e90"));
bodyChildren.push(dataTable(
  ["\u8868\u73b0", "\u53ef\u80fd\u539f\u56e0", "\u5904\u7406"],
  [
    ["backend \u54cd\u5e94\u53d8\u6162", "SQLite \u5355\u5199\u9501\u91cd\u8f7d", "\u6253\u5f00\u300c\u8bbe\u7f6e \u2192 \u540c\u6b65\u300d\u51cf\u5c0f\u5e76\u53d1\u91cf\uff1b\u6216\u8003\u8651\u5e94\u7528 PostgreSQL\uff08\u9700\u5b9a\u5236\uff09"],
    ["agent \u5360\u5185\u5b58\u9ad8", "\u4f1a\u8bdd\u4e0a\u9650\u592a\u5927", "\u4e0b\u8c03 AGENT_MAX_SESSIONS \u4e0e AGENT_SESSION_IDLE_MS"],
    ["\u955c\u50cf\u53d8\u5927", "\u4f9d\u8d56\u6dfb\u52a0\u4f46\u672a\u6e05\u7406\u7f13\u5b58", "docker builder prune; \u91cd\u65b0\u6784\u5efa\u65f6\u4f7f\u7528 --no-cache"],
  ],
  [3500, 3000, 3606],
));

bodyChildren.push(h2("9.4 \u83b7\u53d6\u8bca\u65ad\u4fe1\u606f"));
bodyChildren.push(body("\u8054\u7cfb\u4ea7\u54c1\u65b9\u65f6\uff0c\u8bf7\u4e00\u5e76\u63d0\u4f9b\u4ee5\u4e0b\u4e09\u4efd\u8f93\u51fa\uff0c\u51e0\u4e4e\u80fd\u8fd8\u539f 90% \u7684\u95ee\u9898\uff1a"));
bodyChildren.push(...codeBlock([
  "$ docker compose ps",
  "$ docker compose logs --tail=200 backend agent frontend > medbot-logs.txt",
  "$ ./scripts/preflight.sh && ./scripts/smoke-test.sh",
]));

// ── Chapter 10 (Appendix) ─────────────────
bodyChildren.push(h1("10. \u9644\u5f55", { pageBreakBefore: true }));

bodyChildren.push(h2("10.1 \u5b8c\u6574 .env \u53c2\u8003\u6a21\u677f"));
bodyChildren.push(...codeBlock([
  "# .env\uff08\u90e8\u7f72\u4e3b\u63a7\uff09",
  "FRONTEND_PORT=5173",
  "BACKEND_PORT=8000",
  "PUBLIC_ORIGIN=https://leads.example.com",
  "",
  "MEDBOT_DB_PATH=/data/medbot.db",
  "AGENT_BASE_URL=http://agent:8011",
  "AGENT_ENV_PATH=/app/agent/.env",
  "AGENT_TOKEN=<deploy.sh \u751f\u6210>",
  "MEDBOT_SERVICE_TOKEN=<deploy.sh \u751f\u6210>",
  "MEDBOT_PUBLIC_URL=https://leads.example.com",
  "",
  "MEDBOT_EMAIL_SERVER=mail.microport.com.cn",
  "MEDBOT_EMAIL_USER=alice@microport.com.cn",
  "MEDBOT_EMAIL_PASSWORD=<\u53d6\u81ea\u5bc6\u7801\u7ba1\u7406\u5e73\u53f0>",
  "",
  "VITE_API_BASE_URL=/api",
]));

bodyChildren.push(h2("10.2 \u5b8c\u6574 agent/.env \u53c2\u8003\u6a21\u677f"));
bodyChildren.push(...codeBlock([
  "# agent/.env\uff08Pi Sidecar\uff09",
  "PI_PROVIDER=bailian",
  "PI_MODEL=qwen3.7-max",
  "OPENAI_API_KEY=",
  "DEEPSEEK_API_KEY=",
  "DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx",
  "",
  "BACKEND_BASE_URL=http://backend:8000",
  "BACKEND_SERVICE_TOKEN=<\u540c .env \u4e2d MEDBOT_SERVICE_TOKEN>",
  "AGENT_HOST=0.0.0.0",
  "AGENT_PORT=8011",
  "AGENT_CORS_ORIGIN=https://leads.example.com",
  "AGENT_TOKEN=<\u540c .env \u4e2d AGENT_TOKEN>",
  "AGENT_MAX_BODY_BYTES=65536",
  "AGENT_MAX_SESSIONS=20",
  "AGENT_SESSION_IDLE_MS=1800000",
]));

bodyChildren.push(h2("10.3 \u4ea4\u4ed8\u68c0\u67e5\u5355"));
bodyChildren.push(body("\u4ea4\u4ed8\u524d\u9010\u9879\u6253\u52fe\uff0c\u907f\u514d\u201c\u4ea4\u4ed8\u540e\u624d\u53d1\u73b0\u201d\uff1a"));
bodyChildren.push(bullet("preflight.sh \u8f93\u51fa\u201c\u9884\u68c0\u5168\u90e8\u901a\u8fc7\u201d"));
bodyChildren.push(bullet("smoke-test.sh \u8f93\u51fa\u201c\u70df\u96fe\u6d4b\u8bd5\u5168\u90e8\u901a\u8fc7\u201d"));
bodyChildren.push(bullet("\u9ed8\u8ba4\u7ba1\u7406\u5458\u5bc6\u7801\u5df2\u88ab\u4e1a\u52a1\u65b9\u4fee\u6539"));
bodyChildren.push(bullet("agent/.env \u7684 LLM Key \u5df2\u586b\u5199\uff0cWeb \u9762\u677f Agent \u80fd\u8fd4\u56de\u6587\u672c"));
bodyChildren.push(bullet("EWS \u90ae\u7bb1\u8fde\u63a5\u72b6\u6001\u4e3a\u300c\u5df2\u8fde\u63a5\u300d"));
bodyChildren.push(bullet("PUBLIC_ORIGIN \u4e0e MEDBOT_PUBLIC_URL \u4e0e\u5b9e\u9645\u8bbf\u95ee URL \u4e00\u81f4"));
bodyChildren.push(bullet("/var/backups/medbot \u4e0b\u80fd\u770b\u5230\u81f3\u5c11\u4e00\u4efd cron \u5907\u4efd\u6587\u4ef6\uff08\u9996\u6b21\u53ef\u624b\u5de5\u8c03\u5ea6\u4e00\u6b21\uff09"));
bodyChildren.push(bullet("\u53d1\u9001\u4e00\u5c01\u6d4b\u8bd5\u90ae\u4ef6\u5230\u81ea\u5df1\u4e2a\u4eba\u90ae\u7bb1\uff0c\u80fd\u6536\u5230\u4e14\u9000\u8ba2\u94fe\u63a5\u53ef\u8bbf\u95ee"));
bodyChildren.push(bullet("\u4ea4\u4ed8\u624b\u518c\u3001\u8d26\u53f7\u5bc6\u7801\u4e0b\u53d1\u3001\u90ae\u7bb1\u53ef\u4ea4\u4ed8\u4e1a\u52a1\u65b9\u8d39\u7528"));

bodyChildren.push(h2("10.4 \u53c2\u8003\u8d44\u6599"));
bodyChildren.push(bullet("\u672c\u9879\u76ee README.md\uff1a\u67b6\u6784\u4e0e\u63a5\u53e3\u6982\u8ff0"));
bodyChildren.push(bullet("docs/DEPLOY.md\uff1a\u79bb\u7ebf\u4ea4\u4ed8\u624b\u518c\u539f\u6587"));
bodyChildren.push(bullet("scripts/deploy.sh / install-offline.sh\uff1a\u90e8\u7f72\u811a\u672c\u6e90\u7801\uff0c\u9047\u5230\u6280\u672f\u7ec6\u8282\u95ee\u9898\u5e94\u4ee5\u811a\u672c\u4e3a\u51c6"));
bodyChildren.push(bullet("docker-compose.yml / docker-compose.deploy.yml\uff1a\u670d\u52a1\u7f16\u6392\u539f\u6587"));

// ─── Footer with page number ────────────────────────────────────────────
function makeFooter() {
  return new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({ children: [PageNumber.CURRENT], size: 18, color: P.secondary }),
      ],
    })],
  });
}
function makeHeader(text) {
  return new Header({
    children: [new Paragraph({
      alignment: AlignmentType.RIGHT,
      border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: P.accent, space: 4 } },
      children: [new TextRun({ text, size: 18, color: P.secondary, font: CN_BODY_FONT })],
    })],
  });
}

// ─── TOC section children ──────────────────
const tocChildren = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 480, after: 360, line: 600, lineRule: "atLeast" },
    children: [new TextRun({
      text: "\u76ee \u3000\u5f55", bold: true, size: 44,
      color: P.primary, font: CN_HEAD_FONT, characterSpacing: 60,
    })],
  }),
  new TableOfContents("Table of Contents", {
    hyperlink: true,
    headingStyleRange: "1-3",
    stylesWithLevels: [
      new StyleLevel("Heading1", 1),
      new StyleLevel("Heading2", 2),
      new StyleLevel("Heading3", 3),
    ],
  }),
  // Refresh hint
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 240, after: 120 },
    children: [new TextRun({
      text: "\u63d0\u793a\uff1a\u6253\u5f00\u6587\u6863\u540e\u53f3\u952e\u76ee\u5f55 \u2192 \u300c\u66f4\u65b0\u57df\u300d\u53ef\u5237\u65b0\u9875\u7801",
      italics: true, size: 18, color: P.secondary, font: CN_BODY_FONT,
    })],
  }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ─── Document assembly ─────────────────────
const doc = new Document({
  creator: "Medbot Deployment Team",
  title: "\u6d77\u5916\u6e20\u9053\u62d3\u5c55\u7cfb\u7edf\u90e8\u7f72\u6559\u7a0b",
  description: "Deployment guide for the overseas distributor prospecting platform",
  styles: {
    default: {
      document: {
        run: { font: { ascii: "Calibri", eastAsia: "SimSun" }, size: 24, color: P.body },
        paragraph: { spacing: { line: 312 } },
      },
      heading1: {
        run: { font: CN_HEAD_FONT, size: 32, bold: true, color: P.primary },
        paragraph: { spacing: { before: 480, after: 240 }, keepNext: true },
      },
      heading2: {
        run: { font: CN_HEAD_FONT, size: 30, bold: true, color: P.primary },
        paragraph: { spacing: { before: 320, after: 160 }, keepNext: true },
      },
      heading3: {
        run: { font: CN_HEAD_FONT, size: 26, bold: true, color: P.primary },
        paragraph: { spacing: { before: 240, after: 120 }, keepNext: true },
      },
    },
  },
  sections: [
    // Section 1: Cover (no header/footer)
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 0, bottom: 0, left: 0, right: 0 },
        },
      },
      children: buildCoverR1(coverConfig),
    },
    // Section 2: TOC — front matter with Roman page numbers
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, bottom: 1440, left: 1701, right: 1417 },
          pageNumbers: { start: 1, formatType: NumberFormat.UPPER_ROMAN },
        },
      },
      headers: { default: makeHeader("\u6d77\u5916\u6e20\u9053\u62d3\u5c55\u7cfb\u7edf\u90e8\u7f72\u6559\u7a0b") },
      footers: { default: makeFooter() },
      children: tocChildren,
    },
    // Section 3: Body — Arabic page numbers, reset to 1
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, bottom: 1440, left: 1701, right: 1417 },
          pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL },
        },
      },
      headers: { default: makeHeader("\u6d77\u5916\u6e20\u9053\u62d3\u5c55\u7cfb\u7edf\u90e8\u7f72\u6559\u7a0b") },
      footers: { default: makeFooter() },
      children: bodyChildren,
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  const out = "/Users/qqr/ai_lead_gen/docs/deploy-tutorial/\u6d77\u5916\u6e20\u9053\u62d3\u5c55\u7cfb\u7edf\u90e8\u7f72\u6559\u7a0b.docx";
  fs.writeFileSync(out, buf);
  console.log("Wrote", out, "(" + buf.length + " bytes)");
});
