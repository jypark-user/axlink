/**
 * 뽑아 낸 본문을 읽을 수 있는 마크다운으로 편다.
 * 문서에서 긁어 온 글은 쪽 하나가 통째로 한 줄이거나, 목차 점선과 쪽 번호가 글자 사이에 섞여 있다.
 * 글자는 고치지 않는다 — 끊긴 데를 잇고, 채움 문자를 걷어 내고, 제목과 번호만 제자리에 놓는다.
 */

const PAGE_ONLY = /^[-–—\s]*\d{1,4}[-–—\s]*$/;
const BULLET = /^(?:[•·‧∙ㆍ▪▫◦○●■□❍∘⦁▶▷◈◆※*+]|[-–—](?=[\s「『【[]))\s*/;
/** 글머리표·번호 — 한 줄에 붙어 나오면 여기서 항목이 새로 시작한다. */
const BULLET_BREAK =
  /\s+(?=(?:[•‧∙▪▫◦○●■□❍∘⦁▶▷◈◆※]|\(?\d{1,2}\)|[가-핳]\.|[①-⑮㉮-㉻])\s*\S|[-–—]\s*[가-힣A-Za-z「『｢【]|\[(?=[^\]]{1,20}\]))/g;
/** 쪽 표시가 글 사이에 끼어 든 자리 — `… 한다. - 53 - 다.` */
const PAGE_INLINE = /\s*[-–—]\s?\d{1,4}\s?[-–—]\s*/g;
/** 번호 항목 — `1.` `2)` `(3)` 은 번호를 살리고, `가.` `①` 은 글머리표로 둔다. */
const ORDERED = /^\(?(\d{1,2})[.)]\s*(\D.*)$/;
const LETTERED = /^(?:[가-핳]\.(?=\s)|[①-⑮㉮-㉻])\s*/;
const CHAPTER = /^제\s*\d+\s*[장편부절](?![가-힣])/;
const ROMAN = /^(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]{1,5})\s*[.)]\s*\S/;
const BRACKET = /^[[<【〔]\s*[^\]>】〕]{1,40}\s*[\]>】]$/;
// 번호는 점이 있어야 번호다 — `5 적용기술` 처럼 표에서 떨어져 나온 숫자는 제목이 아니다.
const NUMBERED = /^(\d+(?:\.\d+)*\.|\d+(?:\.\d+)+)\s+(\S.*)$/;
const ENDS_SENTENCE = /[.!?:;。？！]["'”’)\]】]?$/;
const HYPHEN_WRAP = /[A-Za-z]-$/;

/** 자간을 벌려 놓은 제목 — `제 안 요 청 서` 처럼 한 글자씩 떨어져 나온다. */
const SPACED_OUT = /(?:[가-힣A-Za-z] ){3,}[가-힣A-Za-z](?![가-힣A-Za-z])/g;
/** 채움 문자 — 목차 점선, 밑줄, 칸 채우기용 반복 글자는 뜻이 없다. */
const FILLER = /[.·‧⋯…∙ㆍ]{3,}|[_=~*]{3,}|[-–—]{4,}/g;
/** 목차 한 줄: `1.1 추진배경 ……… 12`. 점선을 걷어 내면 번호와 제목만 남는다. */
const LEADER = /\s*(?:[.·‧⋯…∙ㆍ]{3,}|\s{4,})\s*(\d{1,4})(?=\s|$)/g;
const TOC_ENTRY = /^(?:(.*)\s)?((?:\d+(?:\.\d+)*|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]{1,5})\.?\s+\S.{0,59})$/;
/** 목차 항목의 끝 표시. 점선을 지운 자리에 남겨 두고, 줄을 다듬을 때 걷어 낸다. */
const TOC_MARK = '\u0001';
/** 문장 끝. 글자 뒤 마침표만 문장으로 본다 — `2025. 2.` 같은 숫자는 아니다. */
// 글자 두 자 이상 뒤의 마침표만 문장 끝이다 — `가.` `나.` 같은 항목 기호는 문장이 아니다.
const SENTENCE_BREAK = /(?<=[가-힣]{2}[.!?]|[a-z]{2}[.!?])\s+(?=\S)/g;
// 장·절은 문장 안에 인용되는 일이 잦아 여기서 끊지 않는다 — 줄 첫머리에 오면 제목으로 잡힌다.
const HEADING_BREAK = /\s+(?=[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s*[.)]|[IVX]{1,5}\.(?=\s)|목\s*차(?![가-힣]))/g;

/**
 * 요구사항 정의서의 칸 이름. 제안요청서는 요구사항을 표로 적는데, 표가 뭉개져 나오면
 * 이 이름들이 글 사이에 그대로 끼어 있다 — 이름 앞에서 끊으면 칸이 다시 줄로 선다.
 * ponytail: 제안요청서 서식에 맞춘 이름표다. 서식이 바뀌면 여기 이름을 늘린다.
 */
const FIELD_NAMES =
  '요구\\s*사항\\s*고유\\s*번호|요구\\s*사항\\s*명칭|요구\\s*사항\\s*분류' +
  '|요구\\s*사항\\s*상세\\s*설명|세부\\s*내용|산출\\s*정보';
const FIELD_BREAK = new RegExp(`\\s+(?=(?:${FIELD_NAMES})\\s)`, 'g');
const FIELD = new RegExp(`^(${FIELD_NAMES})\\s*(.*)$`);
/** 요구사항 번호 — `SER-002` 처럼 붙어 나오면 항목이 새로 시작한다. */
const CODE_BREAK = /\s+(?=[A-Z]{2,4}-\d{2,4}\s)/g;
const CODE_ONLY = /^[A-Z]{2,4}-\d{2,4}$/;
/** 한 덩이가 이만큼 길어지면 더 잇지 않는다 — 끝이 없는 줄글로 뭉치는 것을 막는다. */
const RUN_MAX = 2000;
/** 서식 목록 — `[별지 3호 서식] 입찰참가신청서` 는 본문이 아니라 첨부 서식 이름이다. */
const FORM_ENTRY = /^\[?별지\s*\d*\s*호?\s*서식\]?/;

/**
 * 화면에 글자로 보이지 않는 것들 — 제어 문자, 폭 없는 공백, 깨진 글자,
 * 그리고 PDF 가 글꼴 안쪽 자리(사용자 영역)에 넣어 둔 글머리표 조각.
 */
const INVISIBLE =
  // eslint-disable-next-line no-control-regex -- 제어문자를 걷어내는 것이 이 정규식의 목적이다.
  /[\u0000-\u0008\u000B-\u001F\u007F\u00AD\u200B-\u200F\u2028\u2029\uE000-\uF8FF\uFEFF\uFFFC\uFFFD]/g;

/** 칸 구분 — 표에서 뽑은 줄은 칸 사이가 탭이거나 공백 두 칸 이상이다. */
const CELL_GAP = /\t+| {2,}|\u3000+/;

/** 표 한 줄로 볼 수 있으면 칸으로 나눠 주고, 아니면 null. */
function cellsOf(line: string): string[] | null {
  if (line.endsWith(TOC_MARK)) return null;
  // 요구사항 표의 칸 이름은 표가 아니라 카드로 편다.
  if (FIELD.test(line.trim())) return null;
  const cells = line
    .trim()
    .split(CELL_GAP)
    .map((c) => c.trim());
  return cells.length >= 2 && cells.every(Boolean) ? cells : null;
}

/** 칸으로 나눈 줄들을 마크다운 표로 짠다 — 첫 줄이 머리글이다. */
function tableBlock(rows: string[][]): string {
  const width = Math.max(...rows.map((r) => r.length));
  const row = (cells: string[]) =>
    `| ${Array.from({ length: width }, (_, i) => cells[i] ?? '').join(' | ')} |`;
  return [
    row(rows[0]),
    `| ${Array.from({ length: width }, () => '---').join(' | ')} |`,
    ...rows.slice(1).map(row),
  ].join('\n');
}

type Kind = 'h' | 'li' | 'p' | 'table';

/** 제목이면 마크다운 제목으로, 아니면 null. */
function heading(line: string): string | null {
  if (/^목\s*차$/.test(line)) return '## 목차';
  // 장 표시가 문장 안에 인용된 것일 수 있다 — 제목은 짧고, 서술어로 끝나지 않는다.
  if (CHAPTER.test(line))
    return line.length <= 40 && !/[함음임다]$/.test(line) ? `## ${line}` : null;
  if (ROMAN.test(line) || BRACKET.test(line)) return `## ${line}`;
  const numbered = NUMBERED.exec(line);
  if (numbered) {
    const number = numbered[1].replace(/\.$/, '');
    const title = numbered[2];
    // 문장은 제목이 아니다 — 짧고 마침표로 끝나지 않는 것만 제목으로 본다.
    if (title.length <= 60 && !ENDS_SENTENCE.test(title)) {
      return `${'#'.repeat(Math.min(number.split('.').length + 1, 5))} ${number} ${title}`;
    }
  }
  return null;
}

/**
 * 목차 항목을 깊이에 맞춘 번호 목록으로 바꾼다.
 * `2.1 상세요구사항` 은 2번 아래 1번이다 — 마크다운이 알아서 번호를 매기도록 들여쓰기만 준다.
 */
function tocItem(entry: string): string {
  const numbered = NUMBERED.exec(entry);
  if (!numbered) return `- ${entry}`;
  const number = numbered[1].replace(/\.$/, '');
  const title = numbered[2];
  const depth = number.split('.').length - 1;
  return `${'   '.repeat(depth)}${number.split('.').pop()}. ${title}`;
}

/** 한 줄에 붙어 나온 문장·제목·목차를 다시 줄로 나눈다. */
function explode(line: string): string[] {
  // 점선 뒤 쪽 번호까지가 목차 한 항목이다 — 표시를 남겨 두고 항목마다 끊는다.
  return line
    .replace(PAGE_INLINE, '\n')
    .replace(LEADER, `${TOC_MARK}\n`)
    .split('\n')
    .flatMap((part) =>
      part
        .replace(HEADING_BREAK, '\n')
        .replace(FIELD_BREAK, '\n')
        .replace(CODE_BREAK, '\n')
        .replace(BULLET_BREAK, '\n')
        .replace(SENTENCE_BREAK, '\n')
        .split('\n'),
    );
}

/** 구조가 시작되는 줄인지 — 이런 줄은 앞줄에 붙이지 않는다. */
function startsStructure(line: string): boolean {
  return (
    BULLET.test(line) ||
    LETTERED.test(line) ||
    ORDERED.test(line) ||
    CHAPTER.test(line) ||
    ROMAN.test(line) ||
    FIELD.test(line) ||
    CODE_ONLY.test(line) ||
    FORM_ENTRY.test(line) ||
    cellsOf(line) !== null
  );
}

/**
 * 쪽 넓이에서 끊긴 줄을 먼저 잇는다.
 * 문서에서 뽑은 글은 `요구 / 사항 / 상세 / 설명` 처럼 이름표마저 줄로 쪼개져 나온다 —
 * 이어 붙인 다음에야 어디가 이름표이고 어디가 항목인지 보인다.
 */
function joinWrapped(lines: string[]): string[] {
  const runs: string[] = [];
  for (const line of lines) {
    // 칸 사이 빈틈은 그대로 둔다 — 표를 알아보는 단서다.
    const text = line.replace(/[^\S\t ]+/g, ' ').trim();
    if (text === '') continue;
    const prev = runs[runs.length - 1];
    if (
      prev !== undefined &&
      prev.length < RUN_MAX &&
      !ENDS_SENTENCE.test(prev) &&
      !startsStructure(text) &&
      !FORM_ENTRY.test(prev) &&
      cellsOf(prev) === null
    ) {
      runs[runs.length - 1] = HYPHEN_WRAP.test(prev) ? prev.slice(0, -1) + text : `${prev} ${text}`;
      continue;
    }
    runs.push(text);
  }
  return runs;
}

export function tidyMarkdown(raw: string): string {
  const out: string[] = [];
  const kinds: Kind[] = [];

  let code: string | null = null; // 방금 읽은 요구사항 번호 — 이름과 묶어 제목으로 세운다

  const push = (kind: Kind, text: string) => {
    const last = kinds[kinds.length - 1];
    if (last && !(last === 'li' && kind === 'li')) out.push('');
    out.push(text);
    kinds.push(kind);
  };

  // 잇고 나서 나눈다 — 순서가 바뀌면 이름표가 쪼개진 채로 다시 뭉친다.
  const lines = joinWrapped(raw.replace(/\r\n?/g, '\n').replace(INVISIBLE, '').split('\n')).flatMap(
    explode,
  );

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];

    // 칸이 나뉜 줄이 잇달아 나오면 표다 — 한 줄짜리는 그냥 문장으로 둔다.
    const cells = cellsOf(line);
    if (cells) {
      const rows = [cells];
      while (i + 1 < lines.length) {
        const next = cellsOf(lines[i + 1]);
        if (!next) break;
        rows.push(next);
        i += 1;
      }
      if (rows.length >= 2) {
        push('table', tableBlock(rows));
        continue;
      }
    }

    const marked = line.endsWith(TOC_MARK);
    const text = (marked ? line.slice(0, -1) : line).replace(/\s+/g, ' ').trim();
    if (text === '' || PAGE_ONLY.test(text)) {
      continue;
    }

    // 목차는 제목이 아니라 번호 목록이다. 항목 앞에 붙어 온 글은 따로 떼어 낸다.
    const toc = marked ? TOC_ENTRY.exec(text) : null;
    if (toc) {
      const [, before, entry] = toc;
      if (before) {
        const title = heading(before) ?? before;
        push(title.startsWith('#') ? 'h' : 'p', title);
      }
      push('li', tocItem(entry.trim()));
      continue;
    }

    const clean = text
      .replace(FILLER, ' ')
      .replace(SPACED_OUT, (run) => run.replace(/ /g, ''))
      .replace(/\s+/g, ' ')
      .trim();
    if (clean === '') {
      continue;
    }

    // 첨부 서식 이름은 본문이 아니다 — 목록으로만 길게 늘어져 읽는 데 방해가 된다.
    if (FORM_ENTRY.test(clean)) {
      continue;
    }

    // 번호만 있는 줄은 바로 뒤 이름과 묶는다.
    if (CODE_ONLY.test(clean)) {
      code = clean;
      continue;
    }

    // 요구사항 표의 칸 — 번호와 이름은 제목으로 묶고, 나머지는 이름표를 굵게 세운다.
    const field = FIELD.exec(clean);
    if (field) {
      const name = field[1].replace(/\s+/g, '');
      const value = field[2].trim();
      if (name === '요구사항고유번호') {
        code = value;
        continue;
      }
      if (name === '요구사항명칭') {
        push('h', `### ${[code, value].filter(Boolean).join(' ')}`);
        code = null;
        continue;
      }
      push('p', value ? `**${field[1]}** ${value}` : `**${field[1]}**`);
      continue;
    }

    const title = heading(clean);
    if (title) {
      push('h', title);
      continue;
    }

    const bullet = BULLET.exec(clean) ?? LETTERED.exec(clean);
    if (bullet) {
      // 글머리표는 떼고, `가.` `①` 같은 항목 기호는 글에 남긴다.
      const body = BULLET.test(clean) ? clean.slice(bullet[0].length).trim() : clean;
      push('li', `- ${body}`);
      continue;
    }

    // 제목이 아닌 번호줄은 번호를 살린다 — 마크다운이 순서 있는 목록으로 그린다.
    const ordered = ORDERED.exec(clean);
    if (ordered) {
      push('li', `${ordered[1]}. ${ordered[2]}`);
      continue;
    }

    push('p', clean);
  }

  return out.join('\n');
}
